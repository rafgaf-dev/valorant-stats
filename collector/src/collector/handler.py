"""AWS Lambda entry point, invoked by EventBridge Scheduler.

Environment:
    PLAYERS            JSON array of tracked players (see config/players.example.json)
    TABLE_NAME         DynamoDB table for matches and import runs
    DATA_BUCKET        S3 bucket served under /data/* by CloudFront
    API_KEY_SECRET_ID  Secrets Manager secret holding the HenrikDev API key
"""

import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3

from collector.collect import collect_all
from collector.config import parse_players
from collector.henrikdev import HenrikDevClient
from collector.publish import S3Publisher
from collector.records import RunStatus
from collector.store import DynamoMatchStore
from collector.telemetry import configure_logging, emit_metrics

API_KEY_CACHE_SECONDS = 3600  # picks up a rotated key within an hour on warm containers

_api_key_cache: tuple[str, float] | None = None


class CollectionFailed(RuntimeError):
    """Raised when every player failed, so the Lambda error metric and alarm fire."""


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    configure_logging()
    players = parse_players(os.environ["PLAYERS"])
    result = collect_all(
        players,
        client=HenrikDevClient(_api_key()),
        store=DynamoMatchStore(boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])),
        publisher=S3Publisher(boto3.client("s3"), os.environ["DATA_BUCKET"]),
        clock=lambda: datetime.now(UTC),
    )
    failed = sum(run.status is RunStatus.FAILED for run in result.runs)
    emit_metrics(
        {
            "SuccessfulRuns": int(result.status is not RunStatus.FAILED),
            "MatchesImported": sum(run.matches_imported for run in result.runs),
            "FailedPlayers": failed,
        }
    )
    summary = {
        "status": result.status.value,
        "players": [
            {"id": run.player_id, "status": run.status.value, "errorCode": run.error_code}
            for run in result.runs
        ],
    }
    if result.status is RunStatus.FAILED:
        raise CollectionFailed(summary)
    return summary


def _api_key() -> str:
    global _api_key_cache
    if _api_key_cache is None or time.monotonic() - _api_key_cache[1] > API_KEY_CACHE_SECONDS:
        response = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["API_KEY_SECRET_ID"]
        )
        _api_key_cache = (response["SecretString"].strip(), time.monotonic())
    return _api_key_cache[0]

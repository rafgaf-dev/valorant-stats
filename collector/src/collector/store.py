"""Match and import-run storage (plan section 4).

One DynamoDB table holds everything for a player under `PK = PLAYER#<id>`:

- matches at `SK = MATCH#<matchId>`; writes only replace a missing or `stored`-source item,
  so re-imports are idempotent and a full v4 record supersedes a backfilled one;
- import runs at `SK = RUN#<startedAt>`, expiring after 90 days.

`JsonFileMatchStore` applies the same rules to a local file for `make collect-local`.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from collector.records import ImportRun, MatchRecord, Result, Source

PARSER_VERSION = 1
IMPORT_RUN_RETENTION = timedelta(days=90)


class MatchStore(Protocol):
    def list_matches(self, player_id: str) -> list[MatchRecord]: ...

    def put_match(self, player_id: str, record: MatchRecord) -> bool:
        """Writes the record unless a v4 record already exists; returns whether it wrote."""
        ...

    def put_import_run(self, run: ImportRun) -> None: ...


def _partition_key(player_id: str) -> str:
    return f"PLAYER#{player_id}"


def _match_item(player_id: str, record: MatchRecord) -> dict[str, Any]:
    return {
        "PK": _partition_key(player_id),
        "SK": f"MATCH#{record.match_id}",
        "matchId": record.match_id,
        "playedAt": record.played_at.isoformat(),
        "result": record.result.value,
        "agent": record.agent,
        "kills": record.kills,
        "deaths": record.deaths,
        "assists": record.assists,
        "headshots": record.headshots,
        "bodyshots": record.bodyshots,
        "legshots": record.legshots,
        "source": record.source.value,
        "parserVersion": PARSER_VERSION,
    }


def _match_from_item(item: dict[str, Any]) -> MatchRecord:
    return MatchRecord(
        match_id=item["matchId"],
        played_at=datetime.fromisoformat(item["playedAt"]),
        result=Result(item["result"]),
        agent=item["agent"],
        # DynamoDB returns numbers as Decimal.
        kills=int(item["kills"]),
        deaths=int(item["deaths"]),
        assists=int(item["assists"]),
        headshots=int(item["headshots"]),
        bodyshots=int(item["bodyshots"]),
        legshots=int(item["legshots"]),
        source=Source(item["source"]),
    )


def _import_run_item(run: ImportRun) -> dict[str, Any]:
    item = {
        "PK": _partition_key(run.player_id),
        "SK": f"RUN#{run.started_at.isoformat()}",
        "status": run.status.value,
        "startedAt": run.started_at.isoformat(),
        "finishedAt": run.finished_at.isoformat(),
        "durationMs": run.duration_ms,
        "matchesFound": run.matches_found,
        "matchesImported": run.matches_imported,
        "expiresAt": int((run.started_at + IMPORT_RUN_RETENTION).timestamp()),
    }
    if run.error_code:
        item["errorCode"] = run.error_code
    return item


class DynamoMatchStore:
    def __init__(self, table: Any) -> None:
        """`table` is a boto3 DynamoDB Table resource."""
        self._table = table

    def list_matches(self, player_id: str) -> list[MatchRecord]:
        condition = Key("PK").eq(_partition_key(player_id)) & Key("SK").begins_with("MATCH#")
        query: dict[str, Any] = {"KeyConditionExpression": condition}
        records = []
        while True:
            page = self._table.query(**query)
            records.extend(_match_from_item(item) for item in page["Items"])
            if "LastEvaluatedKey" not in page:
                return records
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def put_match(self, player_id: str, record: MatchRecord) -> bool:
        try:
            self._table.put_item(
                Item=_match_item(player_id, record),
                ConditionExpression="attribute_not_exists(SK) OR #source = :stored",
                ExpressionAttributeNames={"#source": "source"},
                ExpressionAttributeValues={":stored": Source.STORED.value},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def put_import_run(self, run: ImportRun) -> None:
        self._table.put_item(Item=_import_run_item(run))


class JsonFileMatchStore:
    """A single-file stand-in for DynamoDB with the same write rules."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def list_matches(self, player_id: str) -> list[MatchRecord]:
        prefix = f"{_partition_key(player_id)}|MATCH#"
        return [
            _match_from_item(item) for key, item in self._load().items() if key.startswith(prefix)
        ]

    def put_match(self, player_id: str, record: MatchRecord) -> bool:
        items = self._load()
        item = _match_item(player_id, record)
        key = f"{item['PK']}|{item['SK']}"
        existing = items.get(key)
        if existing is not None and existing["source"] != Source.STORED.value:
            return False
        items[key] = item
        self._save(items)
        return True

    def put_import_run(self, run: ImportRun) -> None:
        items = self._load()
        item = _import_run_item(run)
        items[f"{item['PK']}|{item['SK']}"] = item
        self._save(items)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, items: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(items, indent=2, sort_keys=True), encoding="utf-8")

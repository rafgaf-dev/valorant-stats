import copy
import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from collector.config import PlayerConfig

FIXTURES = Path(__file__).parent / "fixtures"
HENRIKDEV = FIXTURES / "henrikdev"
TABLE_NAME = "valorant-stats-test"
DATA_BUCKET = "valorant-stats-data-test"


def _load(name: str) -> Any:
    return json.loads((HENRIKDEV / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def v4_matches() -> list[dict[str, Any]]:
    return _load("matches-v4.json")["data"]


@pytest.fixture(scope="session")
def stored_records() -> list[dict[str, Any]]:
    return _load("stored-matches.json")["data"]


@pytest.fixture(scope="session")
def match_details() -> list[dict[str, Any]]:
    return _load("match-details-v4.json")["data"]


@pytest.fixture
def player() -> PlayerConfig:
    return PlayerConfig("neon-main", "Example", "EUW", "The Neon Menace", "Neon")


class FakeHenrikDev:
    """Serves the captured fixtures and records which endpoints were called."""

    def __init__(self) -> None:
        self.account_data = _load("account.json")["data"]
        self.recent = _load("matches-v4.json")["data"]
        self.stored = _load("stored-matches.json")["data"]
        details = _load("match-details-v4.json")["data"]
        self.details = {match["metadata"]["match_id"]: match for match in details}
        self.calls: Counter[str] = Counter()
        self.errors: dict[str, Exception] = {}

    def _call(self, endpoint: str) -> None:
        self.calls[endpoint] += 1
        if endpoint in self.errors:
            raise self.errors[endpoint]

    def account(self, name: str, tag: str) -> dict[str, Any]:
        self._call("account")
        return copy.deepcopy(self.account_data)

    def recent_matches(self, puuid: str, size: int) -> list[dict[str, Any]]:
        self._call("recent_matches")
        return copy.deepcopy(self.recent[:size])

    def stored_matches(self, puuid: str) -> list[dict[str, Any]]:
        self._call("stored_matches")
        return copy.deepcopy(self.stored)

    def match_details(self, match_id: str) -> dict[str, Any]:
        self._call("match_details")
        return copy.deepcopy(self.details[match_id])


@pytest.fixture
def henrikdev() -> FakeHenrikDev:
    return FakeHenrikDev()


class FakeClock:
    """Starts at a fixed time and advances one second per reading."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@dataclass(frozen=True)
class AwsResources:
    table_name: str = TABLE_NAME
    data_bucket: str = DATA_BUCKET


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[AwsResources]:
    """Mocked DynamoDB, S3, and Secrets Manager with the resources the collector expects."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(name, "testing")
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        boto3.client("s3").create_bucket(
            Bucket=DATA_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        yield AwsResources()


@pytest.fixture
def table(aws: AwsResources) -> Any:
    return boto3.resource("dynamodb").Table(aws.table_name)

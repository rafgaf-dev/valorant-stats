import json
import logging

import boto3
import pytest

from collector import handler as handler_module
from collector.henrikdev import AuthError
from collector.publish import SUMMARY_CACHE_CONTROL

PLAYERS = [
    {
        "id": "neon-main",
        "gameName": "Example",
        "tagLine": "EUW",
        "displayName": "The Neon Menace",
        "agent": "Neon",
    }
]


@pytest.fixture
def lambda_env(aws, monkeypatch, henrikdev):
    # The handler reconfigures the root logger; restore it so later tests are unaffected.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", list(root.handlers))
    monkeypatch.setattr(root, "level", root.level)
    secret = boto3.client("secretsmanager").create_secret(
        Name="henrikdev-key", SecretString="HDEV-from-secrets-manager\n"
    )
    monkeypatch.setenv("PLAYERS", json.dumps(PLAYERS))
    monkeypatch.setenv("TABLE_NAME", aws.table_name)
    monkeypatch.setenv("DATA_BUCKET", aws.data_bucket)
    monkeypatch.setenv("API_KEY_SECRET_ID", secret["ARN"])
    monkeypatch.setattr(handler_module, "_api_key_cache", None)
    keys = []

    def fake_client(api_key):
        keys.append(api_key)
        return henrikdev

    monkeypatch.setattr(handler_module, "HenrikDevClient", fake_client)
    return keys


def test_handler_collects_publishes_and_reports(lambda_env, aws, capsys):
    result = handler_module.handler({}, None)

    assert result == {
        "status": "success",
        "players": [{"id": "neon-main", "status": "success", "errorCode": None}],
    }
    assert lambda_env == ["HDEV-from-secrets-manager"]  # read from the secret, trimmed
    obj = boto3.client("s3").get_object(
        Bucket=aws.data_bucket, Key="data/players/neon-main/summary.json"
    )
    assert obj["ContentType"] == "application/json"
    assert obj["CacheControl"] == SUMMARY_CACHE_CONTROL
    summary = json.loads(obj["Body"].read())
    assert summary["windows"]["sinceTracking"]["matches"] == 20

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    metrics = next(line for line in lines if "_aws" in line)
    assert (metrics["SuccessfulRuns"], metrics["MatchesImported"], metrics["FailedPlayers"]) == (
        1,
        34,
        0,
    )
    events = [line.get("event") for line in lines]
    assert "player_collected" in events


def test_handler_raises_when_every_player_fails(lambda_env, henrikdev, capsys):
    henrikdev.errors["account"] = AuthError(403, "Invalid API Key (code 0)")

    with pytest.raises(handler_module.CollectionFailed):
        handler_module.handler({}, None)

    metrics = next(
        json.loads(line) for line in capsys.readouterr().out.splitlines() if '"_aws"' in line
    )
    assert (metrics["SuccessfulRuns"], metrics["FailedPlayers"]) == (0, 1)


def test_api_key_is_cached_between_invocations(lambda_env, monkeypatch):
    handler_module.handler({}, None)
    calls = []
    original = boto3.client

    def counting_client(service, *args, **kwargs):
        calls.append(service)
        return original(service, *args, **kwargs)

    monkeypatch.setattr(handler_module.boto3, "client", counting_client)

    handler_module.handler({}, None)

    assert "secretsmanager" not in calls

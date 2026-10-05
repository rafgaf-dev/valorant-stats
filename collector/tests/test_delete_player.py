import json
from dataclasses import replace
from datetime import UTC, datetime

import boto3
import pytest

import delete_player as module
from collector.records import ImportRun, MatchRecord, Result, RunStatus, Source
from collector.store import DynamoMatchStore
from delete_player import delete_items, delete_objects, invalidate, main, still_configured

PLAYED_AT = datetime(2026, 9, 20, 18, tzinfo=UTC)
MATCH = MatchRecord("match-1", PLAYED_AT, Result.WIN, "Neon", 10, 5, 3, 4, 15, 1, Source.V4)


class FakeCloudFront:
    def __init__(self):
        self.calls = []

    def create_invalidation(self, **kwargs):
        self.calls.append(kwargs)
        return {"Invalidation": {"Id": f"I{len(self.calls)}"}}


@pytest.fixture
def stored(table):
    """Two players' matches and runs in DynamoDB."""
    store = DynamoMatchStore(table)
    for player in ("neon-main", "neon-main-2"):
        for index in range(3):
            store.put_match(player, replace(MATCH, match_id=f"match-{index}"))
        store.put_import_run(ImportRun(player, PLAYED_AT, PLAYED_AT, RunStatus.SUCCESS))
    return table


@pytest.fixture
def bucket(aws):
    """The data bucket, versioned, with two versions of a summary and a deleted photo."""
    s3 = boto3.client("s3")
    s3.put_bucket_versioning(Bucket=aws.data_bucket, VersioningConfiguration={"Status": "Enabled"})
    for player in ("neon-main", "neon-main-2"):
        for version in (1, 2):
            s3.put_object(
                Bucket=aws.data_bucket,
                Key=f"data/players/{player}/summary.json",
                Body=json.dumps({"version": version}).encode(),
            )
        s3.put_object(Bucket=aws.data_bucket, Key=f"data/players/{player}/photo.webp", Body=b"x")
        s3.delete_object(Bucket=aws.data_bucket, Key=f"data/players/{player}/photo.webp")
    return aws.data_bucket


def remaining_keys(bucket, prefix):
    page = boto3.client("s3").list_object_versions(Bucket=bucket, Prefix=prefix)
    return [v["Key"] for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]


def test_delete_items_removes_matches_and_runs_for_that_player_only(stored):
    assert delete_items(stored, "neon-main") == 4

    store = DynamoMatchStore(stored)
    assert store.list_matches("neon-main") == []
    assert len(store.list_matches("neon-main-2")) == 3
    assert (
        stored.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": "PLAYER#neon-main"},
        )["Items"]
        == []
    )


def test_delete_items_follows_pagination(stored, monkeypatch):
    original_query = stored.query
    monkeypatch.setattr(stored, "query", lambda **kwargs: original_query(Limit=1, **kwargs))

    assert delete_items(stored, "neon-main") == 4


def test_delete_objects_removes_every_version_and_delete_marker(bucket):
    s3 = boto3.client("s3")

    # 2 summary versions, 1 photo version, 1 delete marker.
    assert delete_objects(s3, bucket, "neon-main") == 4

    assert remaining_keys(bucket, "data/players/neon-main/") == []
    assert len(remaining_keys(bucket, "data/players/neon-main-2/")) == 4


def test_invalidate_uses_the_player_prefix_and_a_unique_reference():
    cloudfront = FakeCloudFront()

    invalidate(cloudfront, "E123", "neon-main")
    invalidate(cloudfront, "E123", "neon-main")

    batches = [call["InvalidationBatch"] for call in cloudfront.calls]
    assert batches[0]["Paths"] == {"Quantity": 1, "Items": ["/data/players/neon-main/*"]}
    assert batches[0]["CallerReference"] != batches[1]["CallerReference"]


def test_still_configured(tmp_path):
    players = tmp_path / "players.json"
    assert still_configured("neon-main", players) is False
    players.write_text(json.dumps([{"id": "neon-main"}]))
    assert still_configured("neon-main", players) is True
    assert still_configured("someone-else", players) is False


@pytest.fixture
def cli(stored, bucket, monkeypatch, tmp_path):
    cloudfront = FakeCloudFront()
    real_client = boto3.client
    monkeypatch.setattr(
        module.boto3,
        "client",
        lambda service, *a, **k: cloudfront if service == "cloudfront" else real_client(service),
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    args = ["--player", "neon-main", "--table", stored.name, "--bucket", bucket]
    return cloudfront, [*args, "--distribution", "E123"]


def test_main_deletes_after_typed_confirmation(cli, monkeypatch, capsys):
    cloudfront, args = cli
    monkeypatch.setattr("builtins.input", lambda prompt: "neon-main")

    assert main(args) == 0

    out = capsys.readouterr().out
    assert "Deleted 4 DynamoDB item(s) and 4 S3 object version(s)." in out
    assert len(cloudfront.calls) == 1


def test_main_deletes_nothing_without_confirmation(cli, monkeypatch, stored):
    cloudfront, args = cli
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")

    assert main(args) == 1

    assert len(DynamoMatchStore(stored).list_matches("neon-main")) == 3
    assert cloudfront.calls == []


def test_main_warns_when_the_player_is_still_configured(cli, capsys):
    _, args = cli
    (module.REPO_ROOT / "config").mkdir()
    (module.REPO_ROOT / "config" / "players.json").write_text(json.dumps([{"id": "neon-main"}]))

    assert main([*args, "--yes"]) == 0

    assert "still in config/players.json" in capsys.readouterr().err


def test_main_rejects_invalid_player_ids(cli, capsys):
    _, args = cli
    args[1] = "../neon"

    assert main([*args, "--yes"]) == 2
    assert "Invalid player id" in capsys.readouterr().err

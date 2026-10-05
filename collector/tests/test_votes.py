import base64
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from votes import handler as handler_module
from votes.handler import handle
from votes.store import VoteStore

KEY = b"test-voter-key"
NOON = datetime(2026, 10, 5, 12, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOON

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def call(table, clock):
    store = VoteStore(table)

    def call(method="GET", path="/api/votes/neon-main", body=None, address="203.0.113.7:51234"):
        event = {
            "rawPath": path,
            "requestContext": {"http": {"method": method}},
            "headers": {"cloudfront-viewer-address": address} if address else {},
        }
        if body is not None:
            event["body"] = body if isinstance(body, str) else json.dumps(body)
        response = handle(event, store=store, player_ids={"neon-main"}, voter_key=KEY, clock=clock)
        return response["statusCode"], json.loads(response["body"]), response["headers"]

    return call


def test_counts_start_at_zero(call):
    status, body, headers = call()

    assert status == 200
    assert body == {"fair": 0, "tooGenerous": 0, "yourVote": None}
    assert headers["Cache-Control"] == "no-store"


def test_a_vote_is_counted_and_remembered_for_the_day(call):
    status, body, _ = call("POST", body={"choice": "tooGenerous"})

    assert status == 200
    assert body == {"fair": 0, "tooGenerous": 1, "yourVote": "tooGenerous"}
    assert call()[1] == {"fair": 0, "tooGenerous": 1, "yourVote": "tooGenerous"}


def test_one_vote_per_viewer_per_day(call, clock):
    call("POST", body={"choice": "fair"})

    status, body, _ = call("POST", body={"choice": "tooGenerous"}, address="203.0.113.7:60000")

    assert status == 409
    assert body == {"error": "already_voted", "fair": 1, "tooGenerous": 0, "yourVote": "fair"}

    clock.now += timedelta(days=1)
    assert call()[1]["yourVote"] is None
    assert call("POST", body={"choice": "tooGenerous"})[0] == 200


def test_other_viewers_vote_separately(call):
    call("POST", body={"choice": "fair"})
    call("POST", body={"choice": "fair"}, address="2001:db8::1:443")

    status, body, _ = call("POST", body={"choice": "tooGenerous"}, address="198.51.100.2:443")

    assert status == 200
    assert body == {"fair": 2, "tooGenerous": 1, "yourVote": "tooGenerous"}


def test_voters_are_stored_as_expiring_hashes_without_the_address(call, table):
    call("POST", body={"choice": "fair"})

    items = table.scan()["Items"]
    voter = next(item for item in items if item["SK"].startswith("VOTER#"))
    assert "203.0.113.7" not in json.dumps(items, default=str)
    assert voter["PK"] == "PLAYER#neon-main"
    assert voter["expiresAt"] == int((NOON + timedelta(days=2)).timestamp())


@pytest.mark.parametrize(
    "body",
    [
        {"choice": "great"},
        {"choice": None},
        {},
        ["fair"],
        "not json",
        json.dumps({"choice": "fair", "padding": "x" * 2000}),
    ],
)
def test_invalid_votes_are_rejected(call, body):
    status, response, _ = call("POST", body=body)

    assert (status, response) == (400, {"error": "invalid_choice"})
    assert call()[1]["fair"] == 0


def test_base64_bodies_are_decoded(call, table, clock):
    event = {
        "rawPath": "/api/votes/neon-main",
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"cloudfront-viewer-address": "203.0.113.7:1"},
        "body": base64.b64encode(b'{"choice": "fair"}').decode(),
        "isBase64Encoded": True,
    }
    response = handle(
        event, store=VoteStore(table), player_ids={"neon-main"}, voter_key=KEY, clock=clock
    )

    assert response["statusCode"] == 200


@pytest.mark.parametrize(
    "path", ["/api/votes/someone-else", "/api/votes/", "/api/votes/neon-main/x", "/"]
)
def test_unknown_players_and_paths_are_not_found(call, path):
    assert call(path=path)[:2] == (404, {"error": "not_found"})


def test_other_methods_are_not_allowed(call):
    status, _, headers = call("DELETE")

    assert status == 405
    assert headers["Allow"] == "GET, POST"


@pytest.mark.parametrize("address", [None, "203.0.113.7", ":443"])
def test_requests_without_a_viewer_address_are_refused(call, address):
    assert call(address=address)[0] == 400


def test_handler_reads_its_configuration_from_the_environment(aws, monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", list(root.handlers))
    monkeypatch.setattr(root, "level", root.level)
    monkeypatch.setenv("TABLE_NAME", aws.table_name)
    monkeypatch.setenv("PLAYER_IDS", json.dumps(["neon-main"]))
    monkeypatch.setenv("VOTER_KEY", "from-terraform")

    response = handler_module.handler(
        {
            "rawPath": "/api/votes/neon-main",
            "requestContext": {"http": {"method": "POST"}},
            "headers": {"cloudfront-viewer-address": "203.0.113.7:1"},
            "body": '{"choice": "fair"}',
        },
        None,
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["fair"] == 1

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

from collector.records import ImportRun, MatchRecord, Result, RunStatus, Source
from collector.store import DynamoMatchStore, JsonFileMatchStore

PLAYED_AT = datetime(2026, 9, 20, 18, 39, 5, 470000, tzinfo=UTC)
STORED = MatchRecord(
    match_id="match-1",
    played_at=PLAYED_AT,
    result=Result.WIN,
    agent="Sova",
    kills=14,
    deaths=9,
    assists=9,
    headshots=9,
    bodyshots=32,
    legshots=1,
    source=Source.STORED,
)
V4 = replace(STORED, source=Source.V4, bottom_fragged=True, main_weapon="Odin")


@pytest.fixture(params=["dynamodb", "json-file"])
def store(request, tmp_path):
    if request.param == "dynamodb":
        return DynamoMatchStore(request.getfixturevalue("table"))
    return JsonFileMatchStore(tmp_path / "store.json")


def test_round_trip_preserves_every_field(store):
    assert store.put_match("neon-main", V4) is True

    assert store.list_matches("neon-main") == [V4]


def test_matches_are_per_player(store):
    store.put_match("neon-main", V4)
    store.put_match("someone-else", replace(V4, match_id="match-2"))

    assert [r.match_id for r in store.list_matches("neon-main")] == ["match-1"]
    assert store.list_matches("nobody") == []


def test_v4_record_replaces_a_stored_record(store):
    store.put_match("neon-main", STORED)

    assert store.put_match("neon-main", V4) is True
    assert store.list_matches("neon-main") == [V4]


def test_stored_record_never_replaces_a_v4_record(store):
    store.put_match("neon-main", V4)

    assert store.put_match("neon-main", STORED) is False
    assert store.list_matches("neon-main") == [V4]


def test_rewriting_a_v4_record_is_a_no_op(store):
    store.put_match("neon-main", V4)

    assert store.put_match("neon-main", replace(V4, kills=99)) is False
    assert store.list_matches("neon-main") == [V4]


def test_import_runs_are_not_listed_as_matches(store):
    store.put_match("neon-main", V4)
    store.put_import_run(
        ImportRun("neon-main", PLAYED_AT, PLAYED_AT, RunStatus.FAILED, error_code="api_auth")
    )

    assert store.list_matches("neon-main") == [V4]


def test_dynamodb_items_have_the_documented_keys_and_ttl(table):
    store = DynamoMatchStore(table)
    store.put_match("neon-main", V4)
    started = datetime(2026, 10, 5, 12, tzinfo=UTC)
    finished = datetime(2026, 10, 5, 12, 0, 3, tzinfo=UTC)
    store.put_import_run(ImportRun("neon-main", started, finished, RunStatus.SUCCESS, 10, 2))

    items = {item["SK"]: item for item in table.scan()["Items"]}
    match = items["MATCH#match-1"]
    run = items["RUN#2026-10-05T12:00:00+00:00"]
    assert match["PK"] == run["PK"] == "PLAYER#neon-main"
    assert (match["source"], match["parserVersion"]) == ("v4", 3)
    assert (match["bottomFragged"], match["mainWeapon"]) == (True, "Odin")
    assert (run["status"], run["durationMs"], run["matchesImported"]) == ("success", 3000, 2)
    assert run["expiresAt"] == int(datetime(2027, 1, 3, 12, tzinfo=UTC).timestamp())
    assert "errorCode" not in run


def test_dynamodb_listing_follows_pagination(table, monkeypatch):
    store = DynamoMatchStore(table)
    for index in range(5):
        store.put_match("neon-main", replace(V4, match_id=f"match-{index}"))
    original_query = table.query
    pages = []

    def small_pages(**kwargs):
        page = original_query(Limit=2, **kwargs)
        pages.append(page)
        return page

    monkeypatch.setattr(table, "query", small_pages)

    assert len(store.list_matches("neon-main")) == 5
    assert len(pages) == 3


def test_dynamodb_errors_other_than_the_condition_are_raised(table, monkeypatch):
    def throttled(**kwargs):
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem")

    monkeypatch.setattr(table, "put_item", throttled)

    with pytest.raises(ClientError):
        DynamoMatchStore(table).put_match("neon-main", V4)


def test_account_hash_round_trip_and_is_not_a_match(store):
    assert store.get_account("neon-main") is None

    store.put_account("neon-main", "hash-1")
    store.put_match("neon-main", V4)

    assert store.get_account("neon-main") == "hash-1"
    assert store.get_account("someone-else") is None
    assert store.list_matches("neon-main") == [V4]


def write_legacy_item(store, source):
    """A match item written by parser version 1, before details existed."""
    item = {
        "PK": "PLAYER#neon-main",
        "SK": "MATCH#match-1",
        "matchId": "match-1",
        "playedAt": PLAYED_AT.isoformat(),
        "result": "win",
        "agent": "Sova",
        "kills": 14,
        "deaths": 9,
        "assists": 9,
        "headshots": 9,
        "bodyshots": 32,
        "legshots": 1,
        "source": source,
        "parserVersion": 1,
    }
    if isinstance(store, DynamoMatchStore):
        store._table.put_item(Item=item)
    else:
        store._save({"PLAYER#neon-main|MATCH#match-1": item})


def test_legacy_items_read_back_without_details(store):
    write_legacy_item(store, "v4")

    (record,) = store.list_matches("neon-main")

    assert (record.bottom_fragged, record.main_weapon, record.has_details) == (None, None, False)


def test_a_v4_record_upgrades_one_from_an_older_parser(store):
    write_legacy_item(store, "v4")

    assert store.put_match("neon-main", V4) is True
    assert store.list_matches("neon-main") == [V4]


def test_a_stored_record_never_downgrades_an_older_v4_record(store):
    write_legacy_item(store, "v4")

    assert store.put_match("neon-main", STORED) is False
    assert store.list_matches("neon-main")[0].source is Source.V4


def test_records_read_back_know_their_parser_version_without_affecting_equality(store):
    store.put_match("neon-main", replace(V4, map_name="Sunset"))

    (record,) = store.list_matches("neon-main")

    assert record.map_name == "Sunset"
    assert record.parser_version == 3
    assert record == replace(V4, map_name="Sunset")  # parser_version isn't compared

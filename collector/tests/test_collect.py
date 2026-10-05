import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collector.collect import account_hash, collect_all, collect_player
from collector.henrikdev import AuthError, NotFoundError, RateLimitedError, ServerError
from collector.publish import DirectoryPublisher
from collector.records import MatchRecord, Result, RunStatus, Source
from collector.store import DynamoMatchStore, JsonFileMatchStore

EXPECTED_SUMMARY = Path(__file__).parent / "fixtures" / "summary.expected.json"
STORED_RECORDS = 20  # in stored-matches.json; none is a remake
RECENT_V4 = 5  # in matches-v4.json; all also in the stored records
ENRICHED = 9  # the other recent-window matches, which get full details fetched


@pytest.fixture(params=["json-file", "dynamodb"])
def store(request, tmp_path):
    if request.param == "dynamodb":
        return DynamoMatchStore(request.getfixturevalue("table"))
    return JsonFileMatchStore(tmp_path / "store.json")


@pytest.fixture
def publisher(tmp_path):
    return DirectoryPublisher(tmp_path / "public")


def published(publisher, player_id="neon-main"):
    return json.loads(publisher.path_for(player_id).read_text(encoding="utf-8"))


def test_first_run_backfills_history_and_publishes_the_contract_summary(
    player, henrikdev, store, publisher, clock
):
    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.status is RunStatus.SUCCESS
    assert run.matches_found == STORED_RECORDS + RECENT_V4
    # Every write counts: 20 stored records, then 5 recent and 9 enriched upgrades to v4.
    assert run.matches_imported == STORED_RECORDS + RECENT_V4 + ENRICHED
    assert henrikdev.calls == {
        "account": 1,
        "stored_matches": 1,
        "match_details": 1 + ENRICHED,  # the 3-10 surrender, then the recent window
        "recent_matches": 1,
    }
    records = store.list_matches("neon-main")
    assert len(records) == STORED_RECORDS
    newest = sorted(records, key=lambda record: record.played_at, reverse=True)
    assert all(record.has_details for record in newest[:15])
    assert sum(record.source is Source.V4 for record in records) == RECENT_V4 + 1 + ENRICHED
    expected = json.loads(EXPECTED_SUMMARY.read_text(encoding="utf-8"))
    assert published(publisher) == expected


def test_contract_summary_totals_match_the_raw_fixtures(stored_records):
    """Independent check of summary.expected.json, straight from the stored records."""
    summary = json.loads(EXPECTED_SUMMARY.read_text(encoding="utf-8"))
    window = summary["windows"]["sinceTracking"]

    assert window["matches"] == len(stored_records)
    assert window["kills"] == sum(r["stats"]["kills"] for r in stored_records)
    assert window["deaths"] == sum(r["stats"]["deaths"] for r in stored_records)
    assert window["headshots"] == sum(r["stats"]["shots"]["head"] for r in stored_records)
    assert window["draws"] == 1
    assert window["since"] == min(r["meta"]["started_at"] for r in stored_records)[:19] + "Z"
    assert summary["windows"]["recent"]["matches"] == 15


def test_contract_detail_counts_match_the_raw_match_details(
    stored_records, v4_matches, match_details
):
    """Independent check of the recent window's detail counts, straight from the raw JSON."""
    details = {m["metadata"]["match_id"]: m for m in [*v4_matches, *match_details]}
    newest = sorted(stored_records, key=lambda r: r["meta"]["started_at"], reverse=True)[:15]
    bottom_frags = heavy_mains = 0
    for record in newest:
        match = details[record["meta"]["id"]]
        me = next(p for p in match["players"] if p["puuid"] == "puuid-tracked")
        team = [p["stats"]["score"] for p in match["players"] if p["team_id"] == me["team_id"]]
        bottom_frags += me["stats"]["score"] == min(team)
        weapons = [
            entry["economy"]["weapon"]["name"]
            for round_ in match.get("rounds", [])
            for entry in round_["stats"]
            if entry["player"]["puuid"] == "puuid-tracked" and entry["economy"]["weapon"]["name"]
        ]
        main = max(weapons, key=weapons.count) if weapons else None
        heavy_mains += main in ("Odin", "Operator")

    recent = json.loads(EXPECTED_SUMMARY.read_text(encoding="utf-8"))["windows"]["recent"]
    assert recent["matchesWithDetails"] == 15
    assert recent["bottomFrags"] == bottom_frags
    assert recent["odinOrOperatorMains"] == heavy_mains


def test_later_runs_skip_the_backfill_and_import_nothing_twice(
    player, henrikdev, store, publisher, clock
):
    collect_player(player, henrikdev, store, publisher, clock)
    henrikdev.calls.clear()

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.status is RunStatus.SUCCESS
    assert run.matches_imported == 0
    assert henrikdev.calls == {"account": 1, "recent_matches": 1}
    assert len(store.list_matches("neon-main")) == STORED_RECORDS
    # Always republished, so generatedAt shows the data is current.
    assert published(publisher)["generatedAt"] == "2026-10-05T12:00:04Z"


def test_new_recent_match_is_imported_on_a_later_run(player, henrikdev, store, publisher, clock):
    collect_player(player, henrikdev, store, publisher, clock)
    new_match = json.loads(json.dumps(henrikdev.recent[0]))
    new_match["metadata"]["match_id"] = "match-new"
    new_match["metadata"]["started_at"] = "2026-10-04T20:00:00Z"
    henrikdev.recent = [new_match, *henrikdev.recent]

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.matches_imported == 1
    assert published(publisher)["windows"]["sinceTracking"]["matches"] == STORED_RECORDS + 1


def test_unparseable_match_makes_the_run_partial_but_keeps_the_rest(
    player, henrikdev, store, publisher, clock
):
    del henrikdev.stored[-1]["stats"]["kills"]  # the oldest; not among the recent v4 matches

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.status is RunStatus.PARTIAL
    assert len(store.list_matches("neon-main")) == STORED_RECORDS - 1
    assert published(publisher)["lastImport"]["status"] == "partial"


def test_missing_match_details_skip_only_that_match(player, henrikdev, store, publisher, clock):
    henrikdev.errors["match_details"] = NotFoundError(404, "Match not found (code 26)")

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.status is RunStatus.PARTIAL
    assert len(store.list_matches("neon-main")) == STORED_RECORDS - 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (NotFoundError(404, "Account not found (code 22)"), "not_found"),
        (ServerError(500, "Error while fetching needed resource (code 9)"), "api_unavailable"),
        (KeyError("boom"), "internal_error"),
    ],
)
def test_failed_player_records_the_error_and_publishes_nothing(
    player, henrikdev, store, publisher, clock, error, code
):
    henrikdev.errors["account"] = error

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert (run.status, run.error_code) == (RunStatus.FAILED, code)
    assert not publisher.path_for("neon-main").exists()


def test_failed_run_keeps_the_last_published_summary(player, henrikdev, store, publisher, clock):
    collect_player(player, henrikdev, store, publisher, clock)
    before = published(publisher)
    henrikdev.errors["recent_matches"] = ServerError(503, "unavailable")

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.status is RunStatus.FAILED
    assert published(publisher) == before


def test_one_failing_player_doesnt_stop_the_others(player, henrikdev, store, publisher, clock):
    missing = replace(player, id="missing", game_name="Gone")
    original_account = henrikdev.account

    def account(name, tag):
        if name == "Gone":
            raise NotFoundError(404, "Account not found (code 22)")
        return original_account(name, tag)

    henrikdev.account = account

    result = collect_all([missing, player], henrikdev, store, publisher, clock)

    assert [run.status for run in result.runs] == [RunStatus.FAILED, RunStatus.SUCCESS]
    assert result.status is RunStatus.PARTIAL
    assert publisher.path_for("neon-main").exists()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (AuthError(403, "Invalid API Key"), "api_auth"),
        (RateLimitedError(429, "slow"), "rate_limited"),
    ],
)
def test_key_and_rate_limit_errors_stop_the_whole_run(
    player, henrikdev, store, publisher, clock, error, code
):
    henrikdev.errors["account"] = error
    second = replace(player, id="second")

    result = collect_all([player, second], henrikdev, store, publisher, clock)

    assert henrikdev.calls["account"] == 1  # the second player was never requested
    assert [(run.status, run.error_code) for run in result.runs] == [(RunStatus.FAILED, code)] * 2
    assert result.status is RunStatus.FAILED


def test_all_players_succeeding_is_a_successful_run(player, henrikdev, store, publisher, clock):
    result = collect_all([player], henrikdev, store, publisher, clock)

    assert result.status is RunStatus.SUCCESS


def test_account_without_a_puuid_fails_the_player(player, henrikdev, store, publisher, clock):
    henrikdev.account_data = {"name": "Example"}

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert (run.status, run.error_code) == (RunStatus.FAILED, "internal_error")


def test_first_run_records_a_hash_of_the_account_not_the_puuid(
    player, henrikdev, store, publisher, clock
):
    collect_player(player, henrikdev, store, publisher, clock)

    recorded = store.get_account("neon-main")
    assert recorded == account_hash(henrikdev.account_data["puuid"])
    assert henrikdev.account_data["puuid"] not in recorded


def test_changed_account_fails_without_touching_the_stored_data(
    player, henrikdev, store, publisher, clock
):
    collect_player(player, henrikdev, store, publisher, clock)
    before = published(publisher)
    henrikdev.account_data = {**henrikdev.account_data, "puuid": "puuid-someone-else"}
    henrikdev.calls.clear()

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert (run.status, run.error_code) == (RunStatus.FAILED, "account_changed")
    assert henrikdev.calls == {"account": 1}  # stopped before fetching any matches
    assert len(store.list_matches("neon-main")) == STORED_RECORDS
    assert published(publisher) == before


def test_data_from_before_the_guard_is_adopted(player, henrikdev, store, publisher, clock):
    # Matches stored by a collector that predates the account check, with no account item.
    legacy = MatchRecord(
        "match-legacy",
        datetime(2026, 1, 1, tzinfo=UTC),
        Result.WIN,
        "Neon",
        10,
        5,
        3,
        4,
        15,
        1,
        Source.STORED,
    )
    store.put_match("neon-main", legacy)

    run = collect_player(player, henrikdev, store, publisher, clock)

    assert run.error_code is None
    assert store.get_account("neon-main") == account_hash(henrikdev.account_data["puuid"])


def test_records_from_an_older_parser_in_the_recent_window_are_refreshed(
    player, henrikdev, store, publisher, clock
):
    collect_player(player, henrikdev, store, publisher, clock)
    # Pretend the recent matches were written by parser version 2, before maps were stored.
    newest = sorted(store.list_matches("neon-main"), key=lambda r: r.played_at, reverse=True)
    for record in newest[:15]:
        legacy = replace(record, map_name=None)
        if isinstance(store, DynamoMatchStore):
            item = store._table.get_item(
                Key={"PK": "PLAYER#neon-main", "SK": f"MATCH#{record.match_id}"}
            )["Item"]
            item.pop("mapName", None)
            item["parserVersion"] = 2
            store._table.put_item(Item=item)
        else:
            items = store._load()
            key = f"PLAYER#neon-main|MATCH#{legacy.match_id}"
            items[key].pop("mapName", None)
            items[key]["parserVersion"] = 2
            store._save(items)
    henrikdev.calls.clear()

    collect_player(player, henrikdev, store, publisher, clock)

    assert henrikdev.calls["match_details"] == 15 - RECENT_V4  # the recent v4 response covers 5
    refreshed = sorted(store.list_matches("neon-main"), key=lambda r: r.played_at, reverse=True)
    assert all(record.map_name for record in refreshed[:15])


def test_summary_lists_the_recent_matches_newest_first_without_ids(
    player, henrikdev, store, publisher, clock
):
    collect_player(player, henrikdev, store, publisher, clock)

    matches = published(publisher)["recentMatches"]

    assert len(matches) == 15
    assert [m["playedAt"] for m in matches] == sorted(
        (m["playedAt"] for m in matches), reverse=True
    )
    assert set(matches[0]) == {
        "playedAt",
        "result",
        "map",
        "agent",
        "kills",
        "deaths",
        "assists",
        "bottomFragged",
        "mainWeapon",
    }
    assert not any("match" in json.dumps(m) for m in matches)  # no "match-0001" style IDs

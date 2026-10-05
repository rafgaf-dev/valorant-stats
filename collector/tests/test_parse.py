import copy
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from collector.parse import (
    NeedsDetails,
    ParseError,
    Skipped,
    parse_stored_match,
    parse_v4_match,
    result_from_score,
)
from collector.records import MatchRecord, Result, Source

TRACKED_PUUID = "puuid-tracked"  # placeholder written by scripts/capture_fixtures.py

# From the captured fixtures (see the capture output recorded in PR #7).
EXPECTED_V4 = [
    ("2026-09-20T18:39:05.470000+00:00", Result.WIN, "Sova", (14, 9, 9), (9, 32, 1)),
    ("2026-09-20T18:15:17.811000+00:00", Result.LOSS, "Gekko", (8, 13, 2), (8, 17, 0)),
    ("2026-09-05T21:14:41.674000+00:00", Result.WIN, "Clove", (12, 15, 3), (10, 14, 2)),
    ("2026-08-31T22:56:56.807000+00:00", Result.LOSS, "Sova", (20, 15, 2), (20, 21, 0)),
    ("2026-08-31T22:28:37.830000+00:00", Result.LOSS, "Gekko", (13, 13, 2), (11, 21, 0)),
]
SURRENDER_STARTED_AT = "2026-08-23T15:18:12.934Z"  # 3-10, no team reached 13
DRAW_STARTED_AT = "2026-08-10T19:54:20.721Z"  # 14-14 after overtime


# --- v4 matches -------------------------------------------------------------------------


def test_v4_fixture_matches_parse_to_the_captured_values(v4_matches):
    records = [parse_v4_match(match, TRACKED_PUUID) for match in v4_matches]

    actual = [
        (
            record.played_at.isoformat(),
            record.result,
            record.agent,
            (record.kills, record.deaths, record.assists),
            (record.headshots, record.bodyshots, record.legshots),
        )
        for record in records
    ]
    assert actual == EXPECTED_V4
    assert all(record.source is Source.V4 for record in records)


def test_v4_and_stored_records_agree_for_the_same_matches(v4_matches, stored_records):
    stored_by_id = {record["meta"]["id"]: record for record in stored_records}

    for match in v4_matches:
        from_v4 = parse_v4_match(match, TRACKED_PUUID)
        from_stored = parse_stored_match(stored_by_id[match["metadata"]["match_id"]])
        assert isinstance(from_stored, MatchRecord)
        assert not from_stored.has_details
        # Everything stored records carry agrees; only v4 adds the details.
        details = {"bottom_fragged": from_v4.bottom_fragged, "main_weapon": from_v4.main_weapon}
        assert replace(from_stored, source=Source.V4, **details) == from_v4


@pytest.fixture
def v4_match(v4_matches):
    return copy.deepcopy(v4_matches[0])


def test_v4_incomplete_match_is_skipped(v4_match):
    v4_match["metadata"]["is_completed"] = False

    assert parse_v4_match(v4_match, TRACKED_PUUID) == Skipped(
        v4_match["metadata"]["match_id"], "not completed"
    )


def test_v4_other_queue_is_skipped(v4_match):
    v4_match["metadata"]["queue"]["id"] = "unrated"

    result = parse_v4_match(v4_match, TRACKED_PUUID)

    assert isinstance(result, Skipped)
    assert result.reason == "queue unrated"


def test_v4_remake_is_skipped(v4_match):
    for team in v4_match["teams"]:
        team["rounds"] = {"won": 0, "lost": 1} if team["won"] else {"won": 1, "lost": 0}

    result = parse_v4_match(v4_match, TRACKED_PUUID)

    assert isinstance(result, Skipped)
    assert result.reason == "remake"


def test_v4_draw_when_no_team_won(v4_match):
    for team in v4_match["teams"]:
        team["won"] = False
        team["rounds"] = {"won": 14, "lost": 14}

    assert parse_v4_match(v4_match, TRACKED_PUUID).result is Result.DRAW


def test_v4_surrender_uses_the_won_flag_not_the_score(v4_match):
    own_team = next(p for p in v4_match["players"] if p["puuid"] == TRACKED_PUUID)["team_id"]
    for team in v4_match["teams"]:
        own = team["team_id"] == own_team
        team["won"] = own  # the opponent surrendered while ahead
        team["rounds"] = {"won": 4, "lost": 7} if own else {"won": 7, "lost": 4}

    assert parse_v4_match(v4_match, TRACKED_PUUID).result is Result.WIN


def test_v4_player_missing_is_an_error(v4_match):
    with pytest.raises(ParseError, match="tracked player not in the match"):
        parse_v4_match(v4_match, "puuid-someone-else")


def test_v4_missing_stat_is_an_error_not_zero(v4_match):
    player = next(p for p in v4_match["players"] if p["puuid"] == TRACKED_PUUID)
    del player["stats"]["headshots"]

    with pytest.raises(ParseError, match="'headshots'"):
        parse_v4_match(v4_match, TRACKED_PUUID)


def test_v4_timestamp_without_timezone_is_an_error(v4_match):
    v4_match["metadata"]["started_at"] = "2026-09-20T18:39:05"

    with pytest.raises(ParseError, match="without timezone"):
        parse_v4_match(v4_match, TRACKED_PUUID)


def test_v4_invalid_timestamp_is_an_error(v4_match):
    v4_match["metadata"]["started_at"] = "yesterday"

    with pytest.raises(ParseError, match="invalid timestamp"):
        parse_v4_match(v4_match, TRACKED_PUUID)


def test_v4_missing_team_entry_is_an_error(v4_match):
    v4_match["teams"] = []

    with pytest.raises(ParseError, match="no team entry"):
        parse_v4_match(v4_match, TRACKED_PUUID)


# --- stored records ---------------------------------------------------------------------


def test_stored_fixture_records_split_into_decided_and_surrender(stored_records):
    parsed = {record["meta"]["started_at"]: parse_stored_match(record) for record in stored_records}

    needs_details = [key for key, value in parsed.items() if isinstance(value, NeedsDetails)]
    decided = [value for value in parsed.values() if isinstance(value, MatchRecord)]
    assert needs_details == [SURRENDER_STARTED_AT]
    assert len(decided) == len(stored_records) - 1
    assert parsed[DRAW_STARTED_AT].result is Result.DRAW
    assert all(record.source is Source.STORED for record in decided)
    assert all(record.played_at.tzinfo is not None for record in decided)


def test_surrender_is_decided_by_its_match_details(stored_records, match_details):
    surrender = next(r for r in stored_records if r["meta"]["started_at"] == SURRENDER_STARTED_AT)
    needs_details = parse_stored_match(surrender)
    details = next(m for m in match_details if m["metadata"]["match_id"] == needs_details.match_id)

    record = parse_v4_match(details, TRACKED_PUUID)

    assert record.match_id == needs_details.match_id
    # The opponents surrendered at 3-10; the score alone can't say so, the details can.
    assert record.result is Result.WIN
    assert (record.kills, record.deaths, record.assists) == (19, 5, 2)
    assert (record.headshots, record.bodyshots, record.legshots) == (16, 15, 0)
    assert record.agent == "Fade"
    assert record.source is Source.V4


def stored_record(red: int, blue: int, team: str = "Blue", mode: str = "Competitive") -> dict:
    return {
        "meta": {"id": "match-x", "mode": mode, "started_at": "2026-08-01T20:00:00Z"},
        "stats": {
            "team": team,
            "character": {"name": "Neon"},
            "kills": 20,
            "deaths": 10,
            "assists": 5,
            "shots": {"head": 6, "body": 30, "leg": 2},
        },
        "teams": {"red": red, "blue": blue},
    }


def test_stored_record_fields():
    record = parse_stored_match(stored_record(red=7, blue=13))

    assert record == MatchRecord(
        match_id="match-x",
        played_at=datetime(2026, 8, 1, 20, tzinfo=UTC),
        result=Result.WIN,
        agent="Neon",
        kills=20,
        deaths=10,
        assists=5,
        headshots=6,
        bodyshots=30,
        legshots=2,
        source=Source.STORED,
    )


@pytest.mark.parametrize(("red", "blue"), [(0, 0), (1, 0), (0, 1)])
def test_stored_remake_is_skipped(red, blue):
    assert parse_stored_match(stored_record(red, blue)) == Skipped("match-x", "remake")


def test_stored_surrender_needs_details():
    assert parse_stored_match(stored_record(red=3, blue=10)) == NeedsDetails("match-x")


def test_stored_other_mode_is_skipped():
    result = parse_stored_match(stored_record(red=7, blue=13, mode="Unrated"))

    assert result == Skipped("match-x", "mode Unrated")


def test_stored_unknown_team_is_an_error():
    with pytest.raises(ParseError, match="unknown team"):
        parse_stored_match(stored_record(red=7, blue=13, team="Green"))


# --- score rules ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("own", "opponent", "expected"),
    [
        (13, 0, Result.WIN),
        (13, 11, Result.WIN),
        (11, 13, Result.LOSS),
        (14, 12, Result.WIN),  # overtime
        (13, 15, Result.LOSS),  # overtime
        (20, 18, Result.WIN),  # long overtime
        (13, 13, Result.DRAW),  # draw vote in overtime
        (14, 14, Result.DRAW),
        (3, 10, None),  # surrender: nobody reached 13
        (12, 12, None),  # surrender at the start of overtime
        (13, 12, None),  # surrender during overtime
        (14, 13, None),  # surrender during overtime
        (5, 5, None),  # surrender at a tie
        (16, 12, None),  # impossible natural score
    ],
)
def test_result_from_score(own, opponent, expected):
    assert result_from_score(own, opponent) is expected


# --- details: bottom frags and main weapons -----------------------------------------------


def test_v4_fixture_details(v4_matches):
    records = [parse_v4_match(match, TRACKED_PUUID) for match in v4_matches]

    # The captured account never finished last and always played the Vandal.
    assert all(record.has_details for record in records)
    assert {record.bottom_fragged for record in records} == {False}
    assert {record.main_weapon for record in records} == {"Vandal"}


def set_scores(match, own_score, teammate_scores):
    me = next(p for p in match["players"] if p["puuid"] == TRACKED_PUUID)
    me["stats"]["score"] = own_score
    teammates = [p for p in match["players"] if p["team_id"] == me["team_id"] and p is not me]
    for teammate, score in zip(teammates, teammate_scores, strict=True):
        teammate["stats"]["score"] = score
    for opponent in (p for p in match["players"] if p["team_id"] != me["team_id"]):
        opponent["stats"]["score"] = 1  # the other team's scores don't matter


@pytest.mark.parametrize(
    ("own", "teammates", "expected"),
    [
        (1000, [2000, 3000, 4000, 5000], True),
        (1000, [1000, 3000, 4000, 5000], True),  # tied for last still counts
        (2000, [1000, 3000, 4000, 5000], False),
    ],
)
def test_bottom_frag_is_the_lowest_score_on_his_team(v4_match, own, teammates, expected):
    set_scores(v4_match, own, teammates)

    assert parse_v4_match(v4_match, TRACKED_PUUID).bottom_fragged is expected


def rounds_with(weapons):
    return [
        {"stats": [{"player": {"puuid": TRACKED_PUUID}, "economy": {"weapon": {"name": w}}}]}
        for w in weapons
    ]


@pytest.mark.parametrize(
    ("weapons", "expected"),
    [
        (["Odin", "Odin", "Vandal", None, None, None], "Odin"),
        (["Operator", "Vandal", "Vandal", "Operator"], "Operator"),  # a tie goes to the first
        ([None, None], None),
        ([], None),
    ],
)
def test_main_weapon_is_the_one_he_started_most_rounds_with(v4_match, weapons, expected):
    v4_match["rounds"] = rounds_with(weapons)

    assert parse_v4_match(v4_match, TRACKED_PUUID).main_weapon == expected


def test_main_weapon_ignores_other_players_rounds(v4_match):
    v4_match["rounds"] = [
        {
            "stats": [
                {"player": {"puuid": "someone-else"}, "economy": {"weapon": {"name": "Odin"}}},
                {"player": {"puuid": TRACKED_PUUID}, "economy": {"weapon": {"name": "Spectre"}}},
            ]
        }
    ]

    assert parse_v4_match(v4_match, TRACKED_PUUID).main_weapon == "Spectre"


def test_main_weapon_is_unknown_without_rounds(v4_match):
    del v4_match["rounds"]

    record = parse_v4_match(v4_match, TRACKED_PUUID)

    assert record.main_weapon is None
    assert record.has_details  # the bottom-frag check only needs the scoreboard


def test_stored_records_have_no_details():
    record = parse_stored_match(stored_record(red=7, blue=13))

    assert (record.bottom_fragged, record.main_weapon, record.has_details) == (None, None, False)

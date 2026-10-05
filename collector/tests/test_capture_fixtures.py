import json

import pytest

from capture_fixtures import Pseudonymizer, pseudonymize, trim

TRACKED = {"puuid": "puuid-real-tracked", "name": "RealFriend", "tag": "FR1"}
STRANGER = {"puuid": "puuid-real-stranger", "name": "Stranger", "tag": "Ultimate"}


def make_responses() -> dict:
    match = {
        "metadata": {
            "match_id": "real-match-id",
            "cluster": "Frankfurt",
            "party_rr_penaltys": [{"party_id": "real-party-1", "penalty": 0}],
        },
        "players": [
            {**TRACKED, "party_id": "real-party-1", "agent": {"id": "a1", "name": "Neon"}},
            {**STRANGER, "party_id": "real-party-2", "agent": {"id": "a2", "name": "Jett"}},
        ],
        "kills": [
            {
                "killer": {**TRACKED, "team": "Red"},
                "victim": {**STRANGER, "team": "Blue"},
                # An ability kill whose weapon id happens to equal the stranger's tag.
                "weapon": {"id": "Ultimate", "name": None, "type": "Ability"},
            }
        ],
    }
    stored_record = {
        "meta": {"id": "real-match-id", "map": {"id": "m1", "name": "Ascent"}},
        "stats": {**TRACKED, "team": "Red", "kills": 20},
        "teams": {"red": 13, "blue": 7},
    }
    return {
        "account.json": {"status": 200, "data": {**TRACKED, "region": "eu"}},
        "matches-v4.json": {"status": 200, "data": [match]},
        "stored-matches.json": {"status": 200, "data": [stored_record]},
    }


PLAYER_CONFIG = {"id": "neon-main", "gameName": "RealFriend", "tagLine": "FR1"}
REAL_VALUES = [
    "puuid-real-tracked",
    "puuid-real-stranger",
    "RealFriend",
    "FR1",
    "Stranger",
    "real-match-id",
    "real-party-1",
    "real-party-2",
]


def test_pseudonymize_removes_every_identifier():
    sanitized, leaks = pseudonymize(make_responses(), PLAYER_CONFIG)

    text = json.dumps(sanitized)
    assert leaks == []
    for value in REAL_VALUES:
        assert value not in text


def test_pseudonymize_uses_stable_placeholders_and_keeps_game_data():
    sanitized, _ = pseudonymize(make_responses(), PLAYER_CONFIG)

    match = sanitized["matches-v4.json"]["data"][0]
    stored = sanitized["stored-matches.json"]["data"][0]
    assert match["players"][0] | {"agent": None} == {
        "puuid": "puuid-tracked",
        "name": "Example",
        "tag": "EUW",
        "party_id": "party-0001",
        "agent": None,
    }
    assert match["kills"][0]["victim"]["name"] == "Player"
    assert match["kills"][0]["victim"]["tag"] == "0000"
    assert match["kills"][0]["weapon"]["id"] == "Ultimate"
    assert match["metadata"]["match_id"] == stored["meta"]["id"]
    assert match["players"][1]["agent"]["name"] == "Jett"
    assert stored["meta"]["map"]["name"] == "Ascent"


def test_find_leaks_reports_riot_ids_in_unknown_structures_without_the_value():
    pseudonymizer = Pseudonymizer(TRACKED["puuid"])
    pseudonymizer.register({"players": [TRACKED]})
    document = {"mystery": {"owner_name": "RealFriend"}}

    leaks = pseudonymizer.find_leaks(document)

    assert leaks == ["$.mystery.owner_name (Riot ID name/tag)"]
    assert "RealFriend" not in leaks[0]


@pytest.mark.parametrize(
    "document",
    [
        {"kills": [{"weapon": {"id": "FR1"}}]},
        {"players": [{"agent": {"name": "FR1"}}]},
        {"metadata": {"cluster": "FR1"}},
    ],
)
def test_find_leaks_ignores_riot_id_coincidences_in_game_data(document):
    pseudonymizer = Pseudonymizer(TRACKED["puuid"])
    pseudonymizer.register({"players": [TRACKED]})

    assert pseudonymizer.find_leaks(document) == []


def test_find_leaks_never_ignores_ids_even_in_game_data():
    pseudonymizer = Pseudonymizer(TRACKED["puuid"])
    pseudonymizer.register({"players": [TRACKED]})
    document = {"kills": [{"weapon": {"id": TRACKED["puuid"]}}]}

    assert pseudonymizer.find_leaks(document) == ["$.kills[0].weapon.id (puuid ID)"]


def test_find_leaks_reports_riot_ids_used_as_keys():
    pseudonymizer = Pseudonymizer(TRACKED["puuid"])
    pseudonymizer.register({"players": [TRACKED]})
    document = {"weapon": {"RealFriend": 1}}

    assert pseudonymizer.find_leaks(document) == ["$.weapon.{key} (Riot ID name/tag)"]


def test_empty_riot_ids_are_not_treated_as_identifiers():
    pseudonymizer = Pseudonymizer(TRACKED["puuid"])
    pseudonymizer.register({"players": [TRACKED, {"puuid": "puuid-unresolved", "name": ""}]})
    document = {"mystery": {"value": ""}}

    assert pseudonymizer.find_leaks(document) == []


def test_trim_drops_unused_v4_sections_only():
    responses = make_responses()
    responses["matches-v4.json"]["data"][0]["rounds"] = [{"stats": []}]

    trimmed = trim(responses)

    match = trimmed["matches-v4.json"]["data"][0]
    assert sorted(match) == ["metadata", "players"]
    assert trimmed["stored-matches.json"] == responses["stored-matches.json"]
    assert "kills" in responses["matches-v4.json"]["data"][0]

import json
from pathlib import Path

import pytest

from collector.config import ConfigError, PlayerConfig, parse_players

VALID = {
    "id": "neon-main",
    "gameName": "Some Name",
    "tagLine": "EUW",
    "displayName": "The Neon Menace",
    "agent": "Neon",
}


def test_parses_the_example_config():
    example = Path(__file__).parents[2] / "config" / "players.example.json"

    assert parse_players(example.read_text(encoding="utf-8")) == [
        PlayerConfig("neon-main", "Example", "EUW", "The Neon Menace", "Neon")
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "not valid JSON"),
        ("{}", "non-empty JSON array"),
        ("[]", "non-empty JSON array"),
        ('["neon-main"]', "expected an object"),
        (json.dumps([{**VALID, "agent": ""}]), "'agent' must be a non-empty string"),
        (json.dumps([{**VALID, "tagLine": 1}]), "'tagLine' must be a non-empty string"),
        (json.dumps([{**VALID, "id": "../etc"}]), "id must match"),
        (json.dumps([{**VALID, "id": "Neon"}]), "id must match"),
        (json.dumps([VALID, VALID]), "unique"),
    ],
)
def test_rejects_invalid_config(raw, message):
    with pytest.raises(ConfigError, match=message):
        parse_players(raw)

"""Tracked-player configuration (config/players.json locally, the PLAYERS variable in AWS)."""

import json
import re
from dataclasses import dataclass
from typing import Any

# Player ids become S3 keys and URL paths, so they are restricted to a safe alphabet.
PLAYER_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PlayerConfig:
    id: str
    game_name: str
    tag_line: str
    display_name: str
    agent: str


def parse_players(raw: str) -> list[PlayerConfig]:
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"players config is not valid JSON: {error}") from None
    if not isinstance(entries, list) or not entries:
        raise ConfigError("players config must be a non-empty JSON array")

    players = [_parse_player(entry, index) for index, entry in enumerate(entries)]
    ids = [player.id for player in players]
    if len(set(ids)) != len(ids):
        raise ConfigError("player ids must be unique")
    return players


def _parse_player(entry: Any, index: int) -> PlayerConfig:
    if not isinstance(entry, dict):
        raise ConfigError(f"player {index}: expected an object")
    values = {}
    for key in ("id", "gameName", "tagLine", "displayName", "agent"):
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"player {index}: {key!r} must be a non-empty string")
        values[key] = value
    if not PLAYER_ID_PATTERN.fullmatch(values["id"]):
        raise ConfigError(f"player {index}: id must match {PLAYER_ID_PATTERN.pattern}")
    return PlayerConfig(
        id=values["id"],
        game_name=values["gameName"],
        tag_line=values["tagLine"],
        display_name=values["displayName"],
        agent=values["agent"],
    )

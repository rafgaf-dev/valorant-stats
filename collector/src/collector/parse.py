"""Turns HenrikDev API match data into MatchRecords.

Two shapes are parsed:

- v4 matches (recent matches and match details), which carry an explicit completed flag and
  per-team `won` flags.
- Stored-match records (backfill), which carry only round scores. Their result is derived
  from Valorant's rules; scores those rules can't decide (surrenders) need the v4 details.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from collector.records import MatchRecord, Result, Source

COMPETITIVE = "competitive"
ROUNDS_TO_WIN = 13
OVERTIME_FROM = ROUNDS_TO_WIN - 1  # overtime starts at 12-12


class ParseError(ValueError):
    """The data is missing something the collector relies on; never silently zeroed."""


@dataclass(frozen=True)
class Skipped:
    match_id: str
    reason: str


@dataclass(frozen=True)
class NeedsDetails:
    """A stored record whose result the score can't decide; fetch the v4 match details."""

    match_id: str


def parse_v4_match(match: dict[str, Any], puuid: str) -> MatchRecord | Skipped:
    metadata = _field(match, "metadata", dict)
    match_id = _field(metadata, "match_id", str)
    queue = _field(_field(metadata, "queue", dict), "id", str)
    if queue != COMPETITIVE:
        return Skipped(match_id, f"queue {queue}")
    if not _field(metadata, "is_completed", bool):
        return Skipped(match_id, "not completed")

    player = _find_player(_field(match, "players", list), puuid, match_id)
    stats = _field(player, "stats", dict)
    teams = _field(match, "teams", list)
    own_team = _field(player, "team_id", str)
    team = next((t for t in teams if _field(t, "team_id", str) == own_team), None)
    if team is None:
        raise ParseError(f"match {match_id}: no team entry for the player's team")
    rounds = _field(team, "rounds", dict)
    if _field(rounds, "won", int) + _field(rounds, "lost", int) <= 1:
        return Skipped(match_id, "remake")

    return MatchRecord(
        match_id=match_id,
        played_at=_timestamp(_field(metadata, "started_at", str), match_id),
        result=_v4_result(teams, own_team),
        agent=_field(_field(player, "agent", dict), "name", str),
        kills=_field(stats, "kills", int),
        deaths=_field(stats, "deaths", int),
        assists=_field(stats, "assists", int),
        headshots=_field(stats, "headshots", int),
        bodyshots=_field(stats, "bodyshots", int),
        legshots=_field(stats, "legshots", int),
        source=Source.V4,
        bottom_fragged=_bottom_fragged(match["players"], player, own_team),
        main_weapon=_main_weapon(match.get("rounds"), puuid),
    )


def _bottom_fragged(players: list[dict[str, Any]], player: dict[str, Any], team: str) -> bool:
    """Whether his combat score was the lowest on his team (a tie for last counts)."""
    teammates = [p for p in players if p.get("team_id") == team]
    lowest = min(_field(_field(p, "stats", dict), "score", int) for p in teammates)
    return _field(_field(player, "stats", dict), "score", int) == lowest


def _main_weapon(rounds: Any, puuid: str) -> str | None:
    """The weapon he started the most rounds with; ties go to the one he used first."""
    if not isinstance(rounds, list):
        return None
    weapons: Counter[str] = Counter()
    for round_ in rounds:
        for entry in round_.get("stats", []):
            if entry.get("player", {}).get("puuid") != puuid:
                continue
            weapon = ((entry.get("economy") or {}).get("weapon") or {}).get("name")
            if isinstance(weapon, str) and weapon:
                weapons[weapon] += 1
    return weapons.most_common(1)[0][0] if weapons else None


def parse_stored_match(record: dict[str, Any]) -> MatchRecord | Skipped | NeedsDetails:
    meta = _field(record, "meta", dict)
    match_id = _field(meta, "id", str)
    mode = _field(meta, "mode", str)
    if mode.lower() != COMPETITIVE:
        return Skipped(match_id, f"mode {mode}")

    stats = _field(record, "stats", dict)
    scores = _field(record, "teams", dict)
    own_team = _field(stats, "team", str).lower()
    opponent = {"red": "blue", "blue": "red"}.get(own_team)
    if opponent is None:
        raise ParseError(f"match {match_id}: unknown team {own_team!r}")
    own_rounds = _field(scores, own_team, int)
    opponent_rounds = _field(scores, opponent, int)

    if own_rounds + opponent_rounds <= 1:
        return Skipped(match_id, "remake")
    result = result_from_score(own_rounds, opponent_rounds)
    if result is None:
        return NeedsDetails(match_id)

    shots = _field(stats, "shots", dict)
    return MatchRecord(
        match_id=match_id,
        played_at=_timestamp(_field(meta, "started_at", str), match_id),
        result=result,
        agent=_field(_field(stats, "character", dict), "name", str),
        kills=_field(stats, "kills", int),
        deaths=_field(stats, "deaths", int),
        assists=_field(stats, "assists", int),
        headshots=_field(shots, "head", int),
        bodyshots=_field(shots, "body", int),
        legshots=_field(shots, "leg", int),
        source=Source.STORED,
    )


def result_from_score(own: int, opponent: int) -> Result | None:
    """Result of a match that ended naturally, or None when only the details can tell.

    A remake can only happen in round 1, and a surrender (from round 5) ends the match before
    either team reaches 13, with the surrendering team losing regardless of score. So only
    these scores are decidable:

    - regulation: the winner has 13 and the loser at most 11;
    - overtime (from 12-12): the winner leads by exactly 2;
    - overtime draw: equal scores of 13 or more (agreed by vote during overtime).
    """
    high, low = max(own, opponent), min(own, opponent)
    if own == opponent:
        return Result.DRAW if own >= ROUNDS_TO_WIN else None
    regulation = high == ROUNDS_TO_WIN and low < OVERTIME_FROM
    overtime = low >= OVERTIME_FROM and high - low == 2
    if not (regulation or overtime):
        return None
    return Result.WIN if own > opponent else Result.LOSS


def _v4_result(teams: list[dict[str, Any]], own_team: str) -> Result:
    winners = {_field(team, "team_id", str) for team in teams if _field(team, "won", bool)}
    if own_team in winners:
        return Result.WIN
    return Result.LOSS if winners else Result.DRAW


def _find_player(players: list[dict[str, Any]], puuid: str, match_id: str) -> dict[str, Any]:
    for player in players:
        if player.get("puuid") == puuid:
            return player
    raise ParseError(f"match {match_id}: tracked player not in the match")


def _timestamp(value: str, match_id: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ParseError(f"match {match_id}: invalid timestamp {value!r}") from None
    if parsed.tzinfo is None:
        raise ParseError(f"match {match_id}: timestamp without timezone {value!r}")
    return parsed


def _field[T](container: dict[str, Any], key: str, expected: type[T]) -> T:
    value = container.get(key)
    # bool is a subclass of int; a True kill count would be a data error, not a number.
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise ParseError(f"expected {expected.__name__} at {key!r}, got {type(value).__name__}")
    return value

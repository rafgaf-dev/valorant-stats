from collections.abc import Iterable
from dataclasses import dataclass

RECENT_MATCH_COUNT = 15


@dataclass(frozen=True)
class Match:
    played_at: str
    won: bool
    kills: int
    deaths: int
    assists: int
    headshots: int
    shots: int


def _sum(matches: Iterable[Match], attribute: str) -> int:
    return sum(getattr(match, attribute) for match in matches)


def calculate_metrics(matches: list[Match]) -> dict:
    recent = matches[:RECENT_MATCH_COUNT]

    def calculate_window(window: list[Match]) -> dict:
        kills = _sum(window, "kills")
        deaths = _sum(window, "deaths")
        assists = _sum(window, "assists")
        headshots = _sum(window, "headshots")
        shots = _sum(window, "shots")
        completed = len(window)
        return {
            "kda": kills / max(deaths, 1),
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "winRate": sum(match.won for match in window) / completed if completed else 0,
            "headshotPercentage": headshots / shots if shots else 0,
            "sampleSize": completed,
        }

    return {"recent": calculate_window(recent), "lifetime": calculate_window(matches)}

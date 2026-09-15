from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


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
            "kda": round(kills / max(deaths, 1), 2),
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "winRate": round(sum(match.won for match in window) / completed, 4) if completed else 0,
            "headshotPercentage": round(headshots / shots, 4) if shots else 0,
            "sampleSize": completed,
        }

    return {"recent": calculate_window(recent), "lifetime": calculate_window(matches)}
"""Metric definitions for the published summary (plan section 5).

All values are computed from summed totals, never by averaging per-match ratios, and are
left unrounded; rounding is a display concern.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from collector.records import MatchRecord, Result

RECENT_MATCH_COUNT = 15


@dataclass(frozen=True)
class Window:
    matches: int
    wins: int
    losses: int
    draws: int
    kills: int
    deaths: int
    assists: int
    headshots: int
    bodyshots: int
    legshots: int
    since: datetime | None

    @classmethod
    def of(cls, records: Iterable[MatchRecord]) -> "Window":
        records = list(records)
        return cls(
            matches=len(records),
            wins=sum(record.result is Result.WIN for record in records),
            losses=sum(record.result is Result.LOSS for record in records),
            draws=sum(record.result is Result.DRAW for record in records),
            kills=sum(record.kills for record in records),
            deaths=sum(record.deaths for record in records),
            assists=sum(record.assists for record in records),
            headshots=sum(record.headshots for record in records),
            bodyshots=sum(record.bodyshots for record in records),
            legshots=sum(record.legshots for record in records),
            since=min((record.played_at for record in records), default=None),
        )

    @property
    def kd(self) -> float | None:
        """Kills per death, with zero deaths counted as one."""
        return self.kills / max(self.deaths, 1) if self.matches else None

    @property
    def win_rate(self) -> float | None:
        """Wins per match; draws count as matches but not wins."""
        return self.wins / self.matches if self.matches else None

    @property
    def headshot_rate(self) -> float | None:
        """Headshot hits per hit (head + body + leg), not per shot fired."""
        hits = self.headshots + self.bodyshots + self.legshots
        return self.headshots / hits if hits else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": self.matches,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "headshots": self.headshots,
            "bodyshots": self.bodyshots,
            "legshots": self.legshots,
            "kd": self.kd,
            "winRate": self.win_rate,
            "headshotRate": self.headshot_rate,
        }


def calculate_windows(records: Iterable[MatchRecord]) -> dict[str, Window]:
    """The recent window (latest matches) and the since-tracking window (all matches)."""
    newest_first = sorted(records, key=lambda record: record.played_at, reverse=True)
    return {
        "recent": Window.of(newest_first[:RECENT_MATCH_COUNT]),
        "sinceTracking": Window.of(newest_first),
    }

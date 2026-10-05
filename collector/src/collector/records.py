from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Result(StrEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


class Source(StrEnum):
    V4 = "v4"  # full match details
    STORED = "stored"  # lightweight stored-match record, used for backfill


@dataclass(frozen=True)
class MatchRecord:
    """One completed competitive match from the tracked player's point of view."""

    match_id: str
    played_at: datetime
    result: Result
    agent: str
    kills: int
    deaths: int
    assists: int
    headshots: int
    bodyshots: int
    legshots: int
    source: Source
    # Only known from full match details (v4); None for lightweight stored records.
    bottom_fragged: bool | None = None  # lowest combat score on his team
    main_weapon: str | None = None  # the weapon he started the most rounds with

    @property
    def has_details(self) -> bool:
        return self.bottom_fragged is not None


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"  # some matches couldn't be parsed or fetched
    FAILED = "failed"


@dataclass(frozen=True)
class ImportRun:
    """The outcome of collecting one player's matches."""

    player_id: str
    started_at: datetime
    finished_at: datetime
    status: RunStatus
    matches_found: int = 0
    matches_imported: int = 0
    error_code: str | None = None

    @property
    def duration_ms(self) -> int:
        return round((self.finished_at - self.started_at).total_seconds() * 1000)

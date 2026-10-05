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

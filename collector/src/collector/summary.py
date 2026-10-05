"""The published summary contract: /data/players/{playerId}/summary.json (plan section 6)."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from collector.config import PlayerConfig
from collector.henrikdev import AFFINITY
from collector.metrics import RECENT_MATCH_COUNT, calculate_windows
from collector.parse import COMPETITIVE
from collector.records import ImportRun, MatchRecord

SCHEMA_VERSION = 3  # 2: matchesWithDetails, bottomFrags, odinOrOperatorMains; 3: recentMatches


def build_summary(
    player: PlayerConfig,
    records: Iterable[MatchRecord],
    last_import: ImportRun,
    generated_at: datetime,
) -> dict[str, Any]:
    records = list(records)
    windows = calculate_windows(records)
    newest_first = sorted(records, key=lambda record: record.played_at, reverse=True)
    since_tracking = windows["sinceTracking"]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "player": {
            "id": player.id,
            "displayName": player.display_name,
            "agent": player.agent,
            "region": AFFINITY,
        },
        "queue": COMPETITIVE,
        "generatedAt": format_timestamp(generated_at),
        "windows": {
            "recent": windows["recent"].to_dict(),
            "sinceTracking": {
                "since": format_timestamp(since_tracking.since) if since_tracking.since else None,
                **since_tracking.to_dict(),
            },
        },
        # Match IDs are left out on purpose: they would let anyone look up the other players.
        "recentMatches": [_recent_match(record) for record in newest_first[:RECENT_MATCH_COUNT]],
        "lastImport": {
            "status": last_import.status.value,
            "finishedAt": format_timestamp(last_import.finished_at),
        },
    }


def _recent_match(record: MatchRecord) -> dict[str, Any]:
    return {
        "playedAt": format_timestamp(record.played_at),
        "result": record.result.value,
        "map": record.map_name,
        "agent": record.agent,
        "kills": record.kills,
        "deaths": record.deaths,
        "assists": record.assists,
        "bottomFragged": record.bottom_fragged,
        "mainWeapon": record.main_weapon,
    }


def format_timestamp(value: datetime) -> str:
    """UTC, whole seconds, `Z` suffix: 2026-10-05T12:00:00Z."""
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

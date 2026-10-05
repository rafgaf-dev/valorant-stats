"""Runs the collector locally against the real API: `make collect-local`.

Matches are kept in collector/.local/store.json and summaries are written to
collector/.local/data/players/<id>/summary.json (both gitignored), so repeated runs only
fetch what's new. The key comes from HENRIKDEV_API_KEY, never from a file.
"""

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from collector.collect import collect_all
from collector.config import ConfigError, parse_players
from collector.henrikdev import HenrikDevClient
from collector.publish import DirectoryPublisher
from collector.store import JsonFileMatchStore
from collector.telemetry import configure_logging

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_DIR = REPO_ROOT / "collector" / ".local"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the collector locally.")
    parser.add_argument("--player", help="only collect this player id")
    args = parser.parse_args()
    configure_logging(logging.INFO)

    api_key = os.environ.get("HENRIKDEV_API_KEY", "")
    if not api_key:
        print("Set HENRIKDEV_API_KEY in the environment.", file=sys.stderr)
        return 2
    try:
        players = parse_players((REPO_ROOT / "config" / "players.json").read_text("utf-8"))
    except (OSError, ConfigError) as error:
        print(f"config/players.json: {error}", file=sys.stderr)
        return 2
    if args.player:
        players = [player for player in players if player.id == args.player]
        if not players:
            print(f"No player with id {args.player!r}.", file=sys.stderr)
            return 2

    publisher = DirectoryPublisher(LOCAL_DIR)
    result = collect_all(
        players,
        client=HenrikDevClient(api_key),
        store=JsonFileMatchStore(LOCAL_DIR / "store.json"),
        publisher=publisher,
        clock=lambda: datetime.now(UTC),
    )
    for run in result.runs:
        print(
            f"{run.player_id}: {run.status.value}, {run.matches_imported} imported "
            f"of {run.matches_found} found" + (f" ({run.error_code})" if run.error_code else ""),
            file=sys.stderr,
        )
        if run.error_code is None:
            path = publisher.path_for(run.player_id).relative_to(REPO_ROOT).as_posix()
            print(f"  summary: {path}", file=sys.stderr)
    return 0 if result.runs and all(run.error_code is None for run in result.runs) else 1


if __name__ == "__main__":
    sys.exit(main())

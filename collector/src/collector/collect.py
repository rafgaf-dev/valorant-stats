"""Collects each tracked player's matches and publishes their summary (plan section 7).

Players are handled independently: one player's failure doesn't affect the others, except
for errors that would fail every further request too (bad key, rate limited), which stop
the run. A summary is only published after a successful import, so the site always shows
the last good data.
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from collector.config import PlayerConfig
from collector.henrikdev import ApiError, AuthError, NotFoundError, RateLimitedError
from collector.parse import NeedsDetails, ParseError, Skipped, parse_stored_match, parse_v4_match
from collector.publish import Publisher
from collector.records import ImportRun, MatchRecord, RunStatus, Source
from collector.store import MatchStore
from collector.summary import build_summary

RECENT_MATCHES = 10  # per run; a 6-hour schedule would need >10 ranked games in between to miss one
RUN_STOPPING_CODES = frozenset({AuthError.code, RateLimitedError.code})

log = logging.getLogger(__name__)
Clock = Callable[[], datetime]


class MatchSource(Protocol):
    """The parts of HenrikDevClient the collector uses."""

    def account(self, name: str, tag: str) -> dict[str, Any]: ...
    def recent_matches(self, puuid: str, size: int) -> list[dict[str, Any]]: ...
    def stored_matches(self, puuid: str) -> list[dict[str, Any]]: ...
    def match_details(self, match_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CollectionResult:
    runs: list[ImportRun]

    @property
    def status(self) -> RunStatus:
        statuses = {run.status for run in self.runs}
        if statuses == {RunStatus.SUCCESS}:
            return RunStatus.SUCCESS
        if statuses == {RunStatus.FAILED}:
            return RunStatus.FAILED
        return RunStatus.PARTIAL


@dataclass
class _Import:
    """Per-player progress, also used for the import-run record."""

    player: PlayerConfig
    puuid: str = ""
    found: int = 0
    imported: int = 0
    problems: list[str] = field(default_factory=list)


def collect_all(
    players: list[PlayerConfig],
    client: MatchSource,
    store: MatchStore,
    publisher: Publisher,
    clock: Clock,
) -> CollectionResult:
    runs: list[ImportRun] = []
    stop_code: str | None = None
    for player in players:
        if stop_code:
            now = clock()
            run = ImportRun(player.id, now, now, RunStatus.FAILED, error_code=stop_code)
            store.put_import_run(run)
        else:
            run = collect_player(player, client, store, publisher, clock)
            if run.error_code in RUN_STOPPING_CODES:
                stop_code = run.error_code
        runs.append(run)
    return CollectionResult(runs)


def collect_player(
    player: PlayerConfig,
    client: MatchSource,
    store: MatchStore,
    publisher: Publisher,
    clock: Clock,
) -> ImportRun:
    started_at = clock()
    progress = _Import(player)
    try:
        _import_matches(progress, client, store)
        records = store.list_matches(player.id)
        finished_at = clock()
        status = RunStatus.PARTIAL if progress.problems else RunStatus.SUCCESS
        run = ImportRun(
            player.id, started_at, finished_at, status, progress.found, progress.imported
        )
        publisher.publish(player.id, build_summary(player, records, run, finished_at))
    except Exception as error:  # isolate players; the cause is logged and recorded
        has_code = isinstance(error, ApiError | AccountChangedError)
        error_code = error.code if has_code else "internal_error"
        log.exception("player_failed", extra={"player": player.id, "error_code": error_code})
        run = ImportRun(
            player.id,
            started_at,
            clock(),
            RunStatus.FAILED,
            progress.found,
            progress.imported,
            error_code,
        )
    store.put_import_run(run)
    log.info(
        "player_collected",
        extra={
            "player": player.id,
            "status": run.status.value,
            "matches_found": run.matches_found,
            "matches_imported": run.matches_imported,
            "problems": progress.problems,
        },
    )
    return run


class AccountChangedError(Exception):
    """The player's Riot ID now resolves to a different account than their stored matches."""

    code = "account_changed"

    def __init__(self, player_id: str) -> None:
        super().__init__(
            f"player {player_id!r} now points at a different Riot account; run "
            f"`make delete-player PLAYER={player_id}` to clear the old account's data first"
        )


def account_hash(puuid: str) -> str:
    return hashlib.sha256(puuid.encode()).hexdigest()


def _check_account(player: PlayerConfig, puuid: str, store: MatchStore) -> None:
    """Stops a changed Riot ID from mixing two accounts' matches under one player id.

    The first run records the account. Data from before this check existed is adopted as
    belonging to the current account.
    """
    recorded = store.get_account(player.id)
    current = account_hash(puuid)
    if recorded is None:
        store.put_account(player.id, current)
    elif recorded != current:
        raise AccountChangedError(player.id)


def _import_matches(progress: _Import, client: MatchSource, store: MatchStore) -> None:
    player = progress.player
    puuid = client.account(player.game_name, player.tag_line).get("puuid")
    if not isinstance(puuid, str):
        raise ParseError("account response has no puuid")
    progress.puuid = puuid
    _check_account(player, puuid, store)

    existing = {record.match_id: record for record in store.list_matches(player.id)}
    if not existing:  # first run: backfill the stored history once
        for stored in client.stored_matches(puuid):
            progress.found += 1
            _import_stored(stored, progress, client, store)

    for match in client.recent_matches(puuid, RECENT_MATCHES):
        progress.found += 1
        known = existing.get(match.get("metadata", {}).get("match_id"))
        if known is None or known.source is not Source.V4:
            _write(_parse(progress, parse_v4_match, match, puuid), progress, store)


def _import_stored(
    stored: dict[str, Any], progress: _Import, client: MatchSource, store: MatchStore
) -> None:
    parsed = _parse(progress, parse_stored_match, stored)
    if isinstance(parsed, NeedsDetails):
        try:
            details = client.match_details(parsed.match_id)
        except NotFoundError:
            progress.problems.append(f"match details not found for {parsed.match_id}")
            return
        parsed = _parse(progress, parse_v4_match, details, progress.puuid)
    _write(parsed, progress, store)


def _parse[**P](
    progress: _Import,
    parse: Callable[P, MatchRecord | Skipped | NeedsDetails],
    *args: P.args,
    **kwargs: P.kwargs,
) -> MatchRecord | Skipped | NeedsDetails | None:
    try:
        return parse(*args, **kwargs)
    except ParseError as error:
        progress.problems.append(str(error))
        log.warning("match_unparseable", extra={"player": progress.player.id, "error": str(error)})
        return None


def _write(
    parsed: MatchRecord | Skipped | NeedsDetails | None, progress: _Import, store: MatchStore
) -> None:
    if isinstance(parsed, MatchRecord) and store.put_match(progress.player.id, parsed):
        progress.imported += 1

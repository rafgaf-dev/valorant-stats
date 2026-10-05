"""AWS Lambda entry point for /api/votes/<player-id>, behind CloudFront.

    GET   the counts, and this viewer's vote today if any
    POST  {"choice": "fair" | "tooGenerous"}: one vote per viewer, per player, per UTC day

Environment:
    PLAYER_IDS  JSON array of the tracked player ids
    TABLE_NAME  DynamoDB table shared with the collector
    VOTER_KEY   Secret key for hashing viewer addresses

The function URL only accepts requests signed by CloudFront (Origin Access Control), so the
CloudFront-Viewer-Address header can be trusted. Addresses are never stored or logged: a
voter is an HMAC of the address, the player, and the day, kept for two days.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

from collector.telemetry import configure_logging
from votes.store import CHOICES, VoteStore

logger = logging.getLogger(__name__)

PATH = re.compile(r"/api/votes/([a-z0-9][a-z0-9-]{0,31})")
MAX_BODY_BYTES = 1024
VOTER_RECORD_DAYS = 2  # long enough to cover the whole UTC day it belongs to

Response = dict[str, Any]


def handler(event: dict[str, Any], context: Any) -> Response:
    configure_logging()
    return handle(
        event,
        store=VoteStore(boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])),
        player_ids=frozenset(json.loads(os.environ["PLAYER_IDS"])),
        voter_key=os.environ["VOTER_KEY"].encode(),
        clock=lambda: datetime.now(UTC),
    )


def handle(
    event: dict[str, Any],
    *,
    store: VoteStore,
    player_ids: Collection[str],
    voter_key: bytes,
    clock: Callable[[], datetime],
) -> Response:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    match = PATH.fullmatch(event.get("rawPath", ""))
    if not match or match[1] not in player_ids:
        return _json(404, {"error": "not_found"})
    player_id = match[1]
    if method not in ("GET", "POST"):
        return _json(405, {"error": "method_not_allowed"}, {"Allow": "GET, POST"})

    address = _viewer_address(event.get("headers") or {})
    if address is None:
        logger.warning("vote_without_viewer_address")
        return _json(400, {"error": "bad_request"})
    now = clock()
    voter = _voter(voter_key, player_id, now, address)

    if method == "GET":
        return _json(200, _tally(store, player_id, store.vote_of(player_id, voter)))

    choice = _choice(event)
    if choice is None:
        return _json(400, {"error": "invalid_choice"})
    expires_at = int((now + timedelta(days=VOTER_RECORD_DAYS)).timestamp())
    if not store.cast(player_id, voter, choice, expires_at):
        earlier = store.vote_of(player_id, voter)
        return _json(409, {"error": "already_voted", **_tally(store, player_id, earlier)})
    logger.info("vote_cast", extra={"playerId": player_id, "choice": choice})
    return _json(200, _tally(store, player_id, choice))


def _viewer_address(headers: dict[str, str]) -> str | None:
    """The viewer's IP from CloudFront-Viewer-Address ("ip:port", IPv6 unbracketed)."""
    value = headers.get("cloudfront-viewer-address", "")
    address, _, port = value.rpartition(":")
    return address if address and port.isdigit() else None


def _voter(key: bytes, player_id: str, now: datetime, address: str) -> str:
    message = f"{player_id}|{now.date().isoformat()}|{address}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _choice(event: dict[str, Any]) -> str | None:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode()
        except ValueError:
            return None
    if len(body.encode()) > MAX_BODY_BYTES:
        return None
    try:
        choice = json.loads(body).get("choice")
    except (ValueError, AttributeError):
        return None
    return choice if choice in CHOICES else None


def _tally(store: VoteStore, player_id: str, your_vote: str | None) -> dict[str, Any]:
    return {**store.counts(player_id), "yourVote": your_vote}


def _json(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> Response:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"}
        | (headers or {}),
        "body": json.dumps(body),
    }

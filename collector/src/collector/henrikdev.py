"""HTTP client for the unofficial HenrikDev Valorant API (plan section 2).

Requests are spaced to stay under the Basic key's 30 requests per minute, rate limits are
honoured once when the wait is short, and server errors are retried with backoff. Error
messages never include the request path, because it contains Riot IDs or PUUIDs.
"""

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

API_HOST = "https://api.henrikdev.xyz"
AFFINITY = "eu"
PLATFORM = "pc"
REQUEST_SPACING_SECONDS = 2.1
MAX_RETRY_AFTER_SECONDS = 60
DEFAULT_RETRY_AFTER_SECONDS = 30
SERVER_ERROR_RETRIES = 2
TIMEOUT_SECONDS = 15


class ApiError(Exception):
    code = "api_error"

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}" if status else message)
        self.status = status


class AuthError(ApiError):
    """The key is missing or invalid; every further request would fail too."""

    code = "api_auth"


class RateLimitedError(ApiError):
    """Still rate limited after waiting once; further requests would fail too."""

    code = "rate_limited"


class NotFoundError(ApiError):
    code = "not_found"


class BadRequestError(ApiError):
    code = "api_bad_request"


class ServerError(ApiError):
    """HenrikDev (or Riot behind it) failed or was unreachable, even after retries."""

    code = "api_unavailable"


Opener = Callable[..., Any]  # urllib.request.urlopen-compatible


class HenrikDevClient:
    def __init__(
        self,
        api_key: str,
        *,
        opener: Opener = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._api_key = api_key
        self._opener = opener
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_request_at: float | None = None

    def account(self, name: str, tag: str) -> dict[str, Any]:
        return self._data(f"/valorant/v2/account/{_segment(name)}/{_segment(tag)}", dict)

    def recent_matches(self, puuid: str, size: int) -> list[dict[str, Any]]:
        path = f"/valorant/v4/by-puuid/matches/{AFFINITY}/{PLATFORM}/{_segment(puuid)}"
        return self._data(path, list, {"mode": "competitive", "size": size})

    def stored_matches(self, puuid: str) -> list[dict[str, Any]]:
        """Every stored competitive match record (no `size`, so no pagination)."""
        path = f"/valorant/v1/by-puuid/stored-matches/{AFFINITY}/{_segment(puuid)}"
        return self._data(path, list, {"mode": "competitive"})

    def match_details(self, match_id: str) -> dict[str, Any]:
        return self._data(f"/valorant/v4/match/{AFFINITY}/{_segment(match_id)}", dict)

    def _data[T](self, path: str, expected: type[T], params: dict[str, Any] | None = None) -> T:
        body = self._get(path, params)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, expected):
            raise ServerError(200, f"response has no {expected.__name__} 'data'")
        return data

    def _get(self, path: str, params: dict[str, Any] | None) -> Any:
        url = API_HOST + path + (f"?{urlencode(params)}" if params else "")
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": self._api_key,
                "Accept": "application/json",
                "User-Agent": "valorant-stats-collector",
            },
        )
        server_retries = 0
        waited_for_rate_limit = False
        while True:
            self._wait_for_request_slot()
            try:
                with self._opener(request, timeout=TIMEOUT_SECONDS) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                message = _error_message(error)
                if error.code == 429:
                    wait = _retry_after_seconds(error.headers)
                    if not waited_for_rate_limit and wait <= MAX_RETRY_AFTER_SECONDS:
                        waited_for_rate_limit = True
                        self._sleep(wait)
                        continue
                    raise RateLimitedError(429, message) from None
                if error.code in (401, 403):
                    raise AuthError(error.code, message) from None
                if error.code == 404:
                    raise NotFoundError(404, message) from None
                if error.code < 500:
                    raise BadRequestError(error.code, message) from None
                failure = ServerError(error.code, message)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                failure = ServerError(None, f"request failed: {type(error).__name__}")

            if server_retries >= SERVER_ERROR_RETRIES:
                raise failure
            server_retries += 1
            self._sleep(2**server_retries + self._jitter())

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._monotonic() - self._last_request_at
            if elapsed < REQUEST_SPACING_SECONDS:
                self._sleep(REQUEST_SPACING_SECONDS - elapsed)
        self._last_request_at = self._monotonic()


def _segment(value: str) -> str:
    return quote(value, safe="")


def _retry_after_seconds(headers: Any) -> float:
    for header in ("Retry-After", "X-RateLimit-Reset"):
        value = headers.get(header) if headers else None
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return DEFAULT_RETRY_AFTER_SECONDS


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        errors = json.load(error).get("errors") or [{}]
        return f"{errors[0].get('message', '')} (code {errors[0].get('code')})"
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return str(error.reason)

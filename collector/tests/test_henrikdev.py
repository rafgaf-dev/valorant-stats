import io
import json
import urllib.error
from email.message import Message

import pytest

from collector.henrikdev import (
    REQUEST_SPACING_SECONDS,
    AuthError,
    BadRequestError,
    HenrikDevClient,
    NotFoundError,
    RateLimitedError,
    ServerError,
)

PUUID = "puuid-secret-value"


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def ok(data: object) -> Response:
    return Response(json.dumps({"status": 200, "data": data}).encode())


def http_error(status: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    body = json.dumps({"errors": [{"code": 0, "message": "nope", "status": status}]})
    return urllib.error.HTTPError(
        "https://api.henrikdev.xyz/hidden", status, "error", message, io.BytesIO(body.encode())
    )


class FakeTransport:
    """Plays back a scripted sequence of responses and records requests and sleeps."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[tuple[str, dict[str, str], float]] = []
        self.sleeps: list[float] = []
        self.time = 1000.0

    def opener(self, request, timeout):
        self.requests.append((request.full_url, dict(request.header_items()), timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.time += seconds

    def client(self) -> HenrikDevClient:
        return HenrikDevClient(
            "HDEV-test-key",
            opener=self.opener,
            sleep=self.sleep,
            monotonic=lambda: self.time,
            jitter=lambda: 0.5,
        )


def test_requests_send_the_key_and_build_the_documented_urls():
    transport = FakeTransport(ok({"puuid": PUUID}), ok([]), ok([]), ok({"metadata": {}}))
    client = transport.client()

    assert client.account("Some Name", "EU#1") == {"puuid": PUUID}
    client.recent_matches(PUUID, 10)
    client.stored_matches(PUUID)
    client.match_details("match id")

    urls = [url for url, _, _ in transport.requests]
    assert urls == [
        "https://api.henrikdev.xyz/valorant/v2/account/Some%20Name/EU%231",
        f"https://api.henrikdev.xyz/valorant/v4/by-puuid/matches/eu/pc/{PUUID}?mode=competitive&size=10",
        f"https://api.henrikdev.xyz/valorant/v1/by-puuid/stored-matches/eu/{PUUID}?mode=competitive",
        "https://api.henrikdev.xyz/valorant/v4/match/eu/match%20id",
    ]
    headers = transport.requests[0][1]
    assert headers["Authorization"] == "HDEV-test-key"
    assert all(timeout == 15 for _, _, timeout in transport.requests)


def test_requests_are_spaced_to_respect_the_rate_limit():
    transport = FakeTransport(ok([]), ok([]))
    client = transport.client()

    client.stored_matches(PUUID)
    transport.time += 0.5  # half a second of work between requests
    client.stored_matches(PUUID)

    assert transport.sleeps == [pytest.approx(REQUEST_SPACING_SECONDS - 0.5)]


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthError), (403, AuthError), (404, NotFoundError), (400, BadRequestError)],
)
def test_client_errors_are_not_retried(status, error):
    transport = FakeTransport(http_error(status))

    with pytest.raises(error) as raised:
        transport.client().recent_matches(PUUID, 10)

    assert len(transport.requests) == 1
    assert raised.value.status == status
    assert "nope (code 0)" in str(raised.value)


def test_error_messages_never_contain_the_request_path():
    transport = FakeTransport(http_error(404))

    with pytest.raises(NotFoundError) as raised:
        transport.client().recent_matches(PUUID, 10)

    assert PUUID not in str(raised.value)
    assert "henrikdev.xyz" not in str(raised.value)


def test_rate_limit_is_waited_out_once_when_short():
    transport = FakeTransport(http_error(429, {"Retry-After": "12"}), ok([]))

    assert transport.client().stored_matches(PUUID) == []
    assert 12.0 in transport.sleeps
    assert len(transport.requests) == 2


def test_rate_limit_uses_the_reset_header_when_retry_after_is_missing():
    transport = FakeTransport(http_error(429, {"X-RateLimit-Reset": "7"}), ok([]))

    transport.client().stored_matches(PUUID)

    assert 7.0 in transport.sleeps


def test_long_rate_limit_stops_immediately():
    transport = FakeTransport(http_error(429, {"Retry-After": "120"}))

    with pytest.raises(RateLimitedError):
        transport.client().stored_matches(PUUID)
    assert transport.sleeps == []


def test_repeated_rate_limit_stops_after_one_wait():
    transport = FakeTransport(
        http_error(429, {"Retry-After": "5"}), http_error(429, {"Retry-After": "5"})
    )

    with pytest.raises(RateLimitedError):
        transport.client().stored_matches(PUUID)
    assert len(transport.requests) == 2


def test_server_errors_are_retried_with_backoff():
    transport = FakeTransport(http_error(500), http_error(503), ok([]))

    assert transport.client().stored_matches(PUUID) == []
    backoffs = [s for s in transport.sleeps if s > REQUEST_SPACING_SECONDS]
    assert backoffs == [2.5, 4.5]


def test_server_errors_give_up_after_two_retries():
    transport = FakeTransport(http_error(500), http_error(500), http_error(500))

    with pytest.raises(ServerError) as raised:
        transport.client().stored_matches(PUUID)
    assert raised.value.status == 500
    assert len(transport.requests) == 3


@pytest.mark.parametrize(
    "failure", [urllib.error.URLError("dns"), TimeoutError(), Response(b"not json")]
)
def test_network_failures_and_bad_json_are_retried(failure):
    transport = FakeTransport(failure, ok([]))

    assert transport.client().stored_matches(PUUID) == []
    assert len(transport.requests) == 2


@pytest.mark.parametrize("body", [{"status": 200}, {"status": 200, "data": {}}, ["data"]])
def test_responses_without_the_expected_data_are_server_errors(body):
    transport = FakeTransport(Response(json.dumps(body).encode()))

    with pytest.raises(ServerError, match="no list 'data'"):
        transport.client().stored_matches(PUUID)


def test_error_without_a_json_body_uses_the_reason():
    error = urllib.error.HTTPError(
        "https://hidden", 502, "Bad Gateway", Message(), io.BytesIO(b"<html>")
    )
    transport = FakeTransport(error, error, error)

    with pytest.raises(ServerError, match="HTTP 502: Bad Gateway"):
        transport.client().stored_matches(PUUID)


def test_unparseable_retry_after_falls_back_to_the_default():
    transport = FakeTransport(http_error(429, {"Retry-After": "soon"}), ok([]))

    transport.client().stored_matches(PUUID)

    assert 30 in transport.sleeps

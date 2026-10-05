"""Capture pseudonymized HenrikDev API responses as collector test fixtures.

Run from the repository root with the key in the environment (never pass it as an argument):

    HENRIKDEV_API_KEY=... python3 collector/scripts/capture_fixtures.py --player neon-main

The script saves the account, recent competitive matches (v4), and stored match history (v1)
to collector/tests/fixtures/henrikdev/, and prints the fields the collector's parsing relies
on. Riot IDs, PUUIDs, party IDs, and match IDs are replaced before anything is written,
because the fixtures are committed to a public repository.

Raw responses are cached in collector/.fixture-cache/ (gitignored, local only). Online runs
fetch only what the cache is missing (--refresh fetches everything again), and --offline
makes no API requests at all. Delete the cache when the fixtures are final: it contains
other players' real Riot IDs.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "collector" / "src"))  # reuse the collector's parsing rules

from collector.parse import NeedsDetails, parse_stored_match  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "collector" / "tests" / "fixtures" / "henrikdev"
CACHE_DIR = REPO_ROOT / "collector" / ".fixture-cache"
API_HOST = "https://api.henrikdev.xyz"
AFFINITY = "eu"
PLATFORM = "pc"
REQUEST_SPACING_SECONDS = 2.1  # Basic keys allow 30 requests per minute
MAX_RETRY_AFTER_SECONDS = 60

AUTH_HINTS = {
    401: "No API key was sent. Check HENRIKDEV_API_KEY.",
    403: "The API key is invalid. Check it in the HenrikDev dashboard.",
}

V4_DOCUMENTS = ("matches-v4.json", "match-details-v4.json")
V4_UNUSED_SECTIONS = ("rounds", "kills")

TRACKED_RIOT_ID = {"name": "Example", "tag": "EUW"}
OTHER_RIOT_ID = {"name": "Player", "tag": "0000"}

# Game data that can coincidentally equal some player's Riot ID name or tag (an ability kill's
# weapon id, an agent called the same as a player). Such matches reveal nothing, so the leak
# check ignores them. PUUIDs, party IDs, and match IDs are never ignored.
GAME_DATA_PARENTS = frozenset(
    {"weapon", "agent", "character", "map", "armor", "queue", "season", "tier"}
)
GAME_DATA_FIELDS = frozenset(
    {"cluster", "region", "platform", "mode", "game_version", "version", "result", "site"}
    | {"winning_team", "team_id", "team", "ceremony", "card", "title"}
)


class ApiError(Exception):
    # The request path is deliberately left out: it contains Riot IDs or PUUIDs.
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def api_get(api_key: str, path: str, params: dict[str, Any] | None = None) -> Any:
    url = API_HOST + path + (f"?{urlencode(params)}" if params else "")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
            "User-Agent": "valorant-stats-fixtures",
        },
    )
    for _ in range(3):
        time.sleep(REQUEST_SPACING_SECONDS)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                reset = error.headers.get("Retry-After") or error.headers.get("X-RateLimit-Reset")
                wait = int(reset or 30)
                if wait <= MAX_RETRY_AFTER_SECONDS:
                    print(f"   rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue
            try:
                errors = json.load(error).get("errors") or [{}]
                message = f"{errors[0].get('message', '')} (code {errors[0].get('code')})"
            except (json.JSONDecodeError, AttributeError):
                message = str(error.reason)
            raise ApiError(error.code, message) from None
    raise ApiError(429, "still rate limited after retries")


def walk(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Yields (path, value) for every node; dict keys are yielded as nodes ending in '{key}'."""
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield (*path, "{key}"), key
            yield from walk(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, (*path, f"[{index}]"))


def format_path(path: tuple[str, ...]) -> str:
    return "$" + "".join(part if part.startswith("[") else f".{part}" for part in path)


class Pseudonymizer:
    """Replaces identifying values everywhere in JSON documents with stable placeholders."""

    PLACEHOLDERS = frozenset({*TRACKED_RIOT_ID.values(), *OTHER_RIOT_ID.values()})

    def __init__(self, tracked_puuid: str) -> None:
        self.tracked_puuid = tracked_puuid
        self.replacements: dict[str, str] = {tracked_puuid: "puuid-tracked"}
        self.counters: dict[str, int] = {}
        self.riot_ids: set[str] = set()

    def _register(self, value: Any, kind: str) -> None:
        if isinstance(value, str) and value and value not in self.replacements:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.replacements[value] = f"{kind}-{self.counters[kind]:04d}"

    def register(self, document: Any) -> None:
        for path, item in walk(document):
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("puuid"), str):
                self._register(item["puuid"], "puuid")
                # Empty names/tags occur when the API couldn't resolve a player; not identifying.
                self.riot_ids.update(
                    item[field] for field in ("name", "tag") if isinstance(item.get(field), str)
                )
                self.riot_ids.discard("")
            self._register(item.get("party_id"), "party")
            self._register(item.get("match_id"), "match")
            if path and path[-1] == "meta":
                self._register(item.get("id"), "match")

    def apply(self, value: Any) -> Any:
        if isinstance(value, dict):
            puuid = value.get("puuid")
            result = {}
            for key, item in value.items():
                if isinstance(puuid, str) and key in ("name", "tag"):
                    riot_id = TRACKED_RIOT_ID if puuid == self.tracked_puuid else OTHER_RIOT_ID
                    result[key] = riot_id[key]
                else:
                    result[self.replacements.get(key, key)] = self.apply(item)
            return result
        if isinstance(value, list):
            return [self.apply(item) for item in value]
        if isinstance(value, str):
            return self.replacements.get(value, value)
        return value

    def find_leaks(self, document: Any) -> list[str]:
        """Describes where identifying values remain and what kind they are, never the values."""
        riot_ids = self.riot_ids - self.PLACEHOLDERS
        leaks = []
        for path, item in walk(document):
            if not isinstance(item, str):
                continue
            if item in self.replacements:
                kind = self.replacements[item].rsplit("-", 1)[0] + " ID"
            elif item in riot_ids and not self._is_game_data(path):
                kind = "Riot ID name/tag"
            else:
                continue
            leaks.append(f"{format_path(path)} ({kind})")
        return sorted(leaks)

    @staticmethod
    def _is_game_data(path: tuple[str, ...]) -> bool:
        if not path or path[-1] == "{key}":
            return False
        parent = path[-2] if len(path) > 1 else ""
        return path[-1] in GAME_DATA_FIELDS or parent in GAME_DATA_PARENTS


def describe_v4_match(match: dict, puuid: str) -> None:
    metadata = match["metadata"]
    player = next(item for item in match["players"] if item["puuid"] == puuid)
    stats = player["stats"]
    team = next((t for t in match["teams"] if t["team_id"] == player["team_id"]), {})
    hits = {field: stats.get(field, 0) for field in ("headshots", "bodyshots", "legshots")}
    total_hits = sum(hits.values())
    rate = f"{hits['headshots'] / total_hits:.1%}" if total_hits else "n/a"
    print(
        f"   - {metadata['started_at']} queue={metadata['queue']['id']!r} "
        f"completed={metadata['is_completed']} agent={player['agent']['name']}"
    )
    print(
        f"     K/D/A {stats['kills']}/{stats['deaths']}/{stats['assists']}  hits {hits} "
        f"(HS {rate})  team won={team.get('won')} rounds={team.get('rounds')}"
    )


def describe_stored_matches(stored: dict) -> None:
    results = stored.get("results", {})
    records = stored.get("data", [])
    print(f"   total stored={results.get('total')} returned={results.get('returned')}")
    if records:
        newest, oldest = records[0]["meta"]["started_at"], records[-1]["meta"]["started_at"]
        print(f"   newest {newest}, oldest {oldest}")
        sample = records[0]
        stats = sample["stats"]
        print(
            f"   newest record: mode={sample['meta']['mode']!r} team={stats['team']} "
            f"K/D/A {stats['kills']}/{stats['deaths']}/{stats['assists']} "
            f"shots={stats['shots']} teams={sample['teams']}"
        )


def cross_check(v4_matches: list[dict], stored: dict, puuid: str) -> None:
    """Compares the two sources for matches that appear in both."""
    stored_by_id = {record["meta"]["id"]: record["stats"] for record in stored.get("data", [])}
    compared = 0
    for match in v4_matches:
        record = stored_by_id.get(match["metadata"]["match_id"])
        if record is None:
            continue
        compared += 1
        stats = next(p for p in match["players"] if p["puuid"] == puuid)["stats"]
        v4_values = (stats["kills"], stats["deaths"], stats["assists"], stats["headshots"])
        stored_values = (record["kills"], record["deaths"], record["assists"])
        stored_values += (record["shots"]["head"],)
        verdict = (
            "match" if v4_values == stored_values else f"DIFFER {v4_values} vs {stored_values}"
        )
        print(f"   {match['metadata']['started_at']}: {verdict}")
    if not compared:
        print("   no match appears in both responses")


def fetch(
    api_key: str, player: dict, match_count: int, stored_count: int, cached: dict[str, Any]
) -> dict[str, Any]:
    """Fetches the documents missing from `cached`; cached ones cost no requests."""
    responses = dict(cached)

    def step(name: str, label: str, request: Callable[[], Any]) -> Any:
        if name in responses:
            print(f"{label}: cached")
        else:
            print(f"{label}: fetching")
            responses[name] = request()
        return responses[name]

    account = step(
        "account.json",
        "1. account (v2)",
        lambda: api_get(
            api_key,
            f"/valorant/v2/account/{quote(player['gameName'], safe='')}/"
            f"{quote(player['tagLine'], safe='')}",
        ),
    )
    puuid = account["data"]["puuid"]
    step(
        "matches-v4.json",
        f"2. recent competitive matches (v4, size={match_count})",
        lambda: api_get(
            api_key,
            f"/valorant/v4/by-puuid/matches/{AFFINITY}/{PLATFORM}/{puuid}",
            {"mode": "competitive", "size": match_count},
        ),
    )
    stored = step(
        "stored-matches.json",
        f"3. stored competitive matches (v1, size={stored_count})",
        lambda: api_get(
            api_key,
            f"/valorant/v1/by-puuid/stored-matches/{AFFINITY}/{puuid}",
            {"mode": "competitive", "size": stored_count},
        ),
    )
    undecided = [
        record["meta"]["id"]
        for record in stored.get("data", [])
        if isinstance(parse_stored_match(record), NeedsDetails)
    ]

    def match_details() -> dict[str, Any]:
        details = [
            api_get(api_key, f"/valorant/v4/match/{AFFINITY}/{quote(match_id, safe='')}")["data"]
            for match_id in undecided
        ]
        return {"status": 200, "data": details}

    step(
        "match-details-v4.json",
        f"4. match details for {len(undecided)} record(s) the score can't decide (v4)",
        match_details,
    )
    return responses


def describe(responses: dict[str, Any], puuid: str) -> None:
    print("Recent v4 matches:")
    for match in responses["matches-v4.json"].get("data", []):
        describe_v4_match(match, puuid)
    print("Stored matches:")
    describe_stored_matches(responses["stored-matches.json"])
    print("Cross-check v4 against stored records:")
    cross_check(
        responses["matches-v4.json"].get("data", []), responses["stored-matches.json"], puuid
    )
    print("Match details for stored records the score can't decide:")
    for match in responses.get("match-details-v4.json", {}).get("data", []):
        describe_v4_match(match, puuid)


def trim(responses: dict[str, Any]) -> dict[str, Any]:
    """Drops v4 match sections the collector doesn't read; they are ~95% of the payload."""
    trimmed = dict(responses)
    for name in V4_DOCUMENTS:
        if name in responses:
            matches = [
                {key: value for key, value in match.items() if key not in V4_UNUSED_SECTIONS}
                for match in responses[name].get("data", [])
            ]
            trimmed[name] = {**responses[name], "data": matches}
    return trimmed


def pseudonymize(responses: dict[str, Any], player: dict) -> tuple[dict[str, Any], list[str]]:
    puuid = responses["account.json"]["data"]["puuid"]
    pseudonymizer = Pseudonymizer(puuid)
    pseudonymizer.riot_ids.update((player["gameName"], player["tagLine"]))
    for document in responses.values():
        pseudonymizer.register(document)
    sanitized = {name: pseudonymizer.apply(document) for name, document in responses.items()}
    leaks = [
        f"{name}: {leak}"
        for name, document in sanitized.items()
        for leak in pseudonymizer.find_leaks(document)
    ]
    return sanitized, leaks


def load_player(player_id: str | None) -> dict | None:
    players_file = REPO_ROOT / "config" / "players.json"
    if not players_file.exists():
        print("Create config/players.json from config/players.example.json.", file=sys.stderr)
        return None
    players = json.loads(players_file.read_text(encoding="utf-8"))
    player = next((p for p in players if player_id in (None, p["id"])), None)
    if player is None:
        print(f"No player with id {player_id!r} in config/players.json.", file=sys.stderr)
    return player


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--player", help="player id from config/players.json (default: first)")
    parser.add_argument("--matches", type=int, default=5, help="recent v4 matches to save")
    parser.add_argument("--stored", type=int, default=20, help="stored match records to save")
    requests = parser.add_mutually_exclusive_group()
    requests.add_argument(
        "--offline", action="store_true", help="use only the cached raw responses; no requests"
    )
    requests.add_argument(
        "--refresh", action="store_true", help="fetch everything again, ignoring the cache"
    )
    parser.add_argument("--out", type=Path, default=FIXTURES_DIR)
    args = parser.parse_args()

    player = load_player(args.player)
    if player is None:
        return 2
    cache_file = CACHE_DIR / f"{player['id']}.json"
    api_key = os.environ.get("HENRIKDEV_API_KEY", "")

    if args.offline:
        if not cache_file.exists():
            print("No cached responses yet; run once without --offline.", file=sys.stderr)
            return 2
        responses = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        if not api_key:
            print("Set HENRIKDEV_API_KEY in the environment.", file=sys.stderr)
            return 2
        cached = {}
        if cache_file.exists() and not args.refresh:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        try:
            responses = fetch(api_key, player, args.matches, args.stored, cached)
        except ApiError as error:
            print(f"   FAILED: {error}", file=sys.stderr)
            if error.status in AUTH_HINTS:
                print(f"   {AUTH_HINTS[error.status]}", file=sys.stderr)
            return 1
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(responses), encoding="utf-8")

    describe(responses, responses["account.json"]["data"]["puuid"])
    sanitized, leaks = pseudonymize(trim(responses), player)
    if api_key and api_key in json.dumps(sanitized):
        leaks.append("the API key")
    if leaks:
        print("Identifying values survived pseudonymization; nothing was written:", file=sys.stderr)
        for leak in leaks:
            print(f"   {leak}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for name, document in sanitized.items():
        path = args.out / name
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "henrikdev"


@pytest.fixture(scope="session")
def v4_matches() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "matches-v4.json").read_text(encoding="utf-8"))["data"]


@pytest.fixture(scope="session")
def stored_records() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "stored-matches.json").read_text(encoding="utf-8"))["data"]


@pytest.fixture(scope="session")
def match_details() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "match-details-v4.json").read_text(encoding="utf-8"))["data"]

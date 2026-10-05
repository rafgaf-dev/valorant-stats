import json
import logging

import pytest

from collector import local
from collector.henrikdev import AuthError


@pytest.fixture
def local_repo(tmp_path, monkeypatch, henrikdev):
    """A temporary repository root with a players file, and the fake API client."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "players.json").write_text(
        json.dumps(
            [
                {
                    "id": "neon-main",
                    "gameName": "Example",
                    "tagLine": "EUW",
                    "displayName": "The Neon Menace",
                    "agent": "Neon",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(local, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(local, "LOCAL_DIR", tmp_path / "collector" / ".local")
    monkeypatch.setattr(local, "HenrikDevClient", lambda api_key: henrikdev)
    monkeypatch.setenv("HENRIKDEV_API_KEY", "HDEV-local")
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", list(root.handlers))
    monkeypatch.setattr(root, "level", root.level)
    return tmp_path


def run(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["collector.local", *args])
    return local.main()


def test_collects_into_the_local_directory(local_repo, monkeypatch, capsys):
    assert run(monkeypatch) == 0

    summary = (
        local_repo / "collector" / ".local" / "data" / "players" / "neon-main" / "summary.json"
    )
    assert json.loads(summary.read_text())["windows"]["sinceTracking"]["matches"] == 20
    assert (local_repo / "collector" / ".local" / "store.json").exists()
    err = capsys.readouterr().err
    assert "neon-main: success, 25 found, 34 written" in err
    assert "collector/.local/data/players/neon-main/summary.json" in err


def test_requires_an_api_key(local_repo, monkeypatch):
    monkeypatch.delenv("HENRIKDEV_API_KEY")

    assert run(monkeypatch) == 2


def test_reports_a_missing_players_file(local_repo, monkeypatch, capsys):
    (local_repo / "config" / "players.json").unlink()

    assert run(monkeypatch) == 2
    assert "config/players.json" in capsys.readouterr().err


def test_unknown_player_is_rejected(local_repo, monkeypatch):
    assert run(monkeypatch, "--player", "nobody") == 2


def test_failed_player_returns_an_error_code(local_repo, monkeypatch, henrikdev, capsys):
    henrikdev.errors["account"] = AuthError(403, "Invalid API Key (code 0)")

    assert run(monkeypatch, "--player", "neon-main") == 1
    assert "neon-main: failed, 0 found, 0 written (api_auth)" in capsys.readouterr().err

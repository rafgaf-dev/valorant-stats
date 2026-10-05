from datetime import UTC, datetime, timedelta

import pytest

from collector.metrics import RECENT_MATCH_COUNT, Window, calculate_windows
from collector.records import MatchRecord, Result, Source

START = datetime(2026, 8, 1, 20, tzinfo=UTC)


def record(
    day: int = 0,
    result: Result = Result.WIN,
    kills: int = 10,
    deaths: int = 5,
    assists: int = 3,
    hits: tuple[int, int, int] = (4, 15, 1),
) -> MatchRecord:
    headshots, bodyshots, legshots = hits
    return MatchRecord(
        match_id=f"match-{day}",
        played_at=START + timedelta(days=day),
        result=result,
        agent="Neon",
        kills=kills,
        deaths=deaths,
        assists=assists,
        headshots=headshots,
        bodyshots=bodyshots,
        legshots=legshots,
        source=Source.V4,
    )


def test_window_sums_totals_and_derives_rates():
    window = Window.of(
        [
            record(0, Result.WIN, kills=20, deaths=10, hits=(5, 10, 5)),
            record(1, Result.LOSS, kills=5, deaths=15, hits=(1, 3, 0)),
            record(2, Result.DRAW, kills=10, deaths=10, hits=(0, 6, 0)),
        ]
    )

    assert (window.matches, window.wins, window.losses, window.draws) == (3, 1, 1, 1)
    assert (window.kills, window.deaths) == (35, 35)
    assert window.kd == 1.0
    assert window.win_rate == pytest.approx(1 / 3)
    assert window.headshot_rate == pytest.approx(6 / 30)
    assert window.since == START


def test_ratios_use_sums_not_per_match_averages():
    window = Window.of([record(0, kills=30, deaths=10), record(1, kills=0, deaths=10)])

    # Per-match K/Ds average to 1.5; the summed ratio is 30 / 20.
    assert window.kd == 1.5
    window = Window.of([record(0, kills=10, deaths=1), record(1, kills=10, deaths=19)])
    assert window.kd == 1.0


def test_zero_deaths_count_as_one():
    assert Window.of([record(kills=12, deaths=0)]).kd == 12.0


def test_draws_count_as_matches_but_not_wins():
    window = Window.of([record(0, Result.WIN), record(1, Result.DRAW)])

    assert window.win_rate == 0.5


def test_no_hits_gives_no_headshot_rate():
    assert Window.of([record(hits=(0, 0, 0))]).headshot_rate is None


def test_empty_window_has_null_rates():
    window = Window.of([])

    assert window.matches == 0
    assert (window.kd, window.win_rate, window.headshot_rate, window.since) == (None,) * 4


def test_recent_window_is_the_latest_matches_regardless_of_input_order():
    records = [record(day, kills=day) for day in range(RECENT_MATCH_COUNT + 5)]

    windows = calculate_windows(reversed(records))

    recent = windows["recent"]
    assert recent.matches == RECENT_MATCH_COUNT
    assert recent.kills == sum(range(5, RECENT_MATCH_COUNT + 5))
    assert recent.since == START + timedelta(days=5)
    assert windows["sinceTracking"].matches == RECENT_MATCH_COUNT + 5
    assert windows["sinceTracking"].since == START


def test_fewer_matches_than_the_recent_window():
    windows = calculate_windows([record(0), record(1)])

    assert windows["recent"] == windows["sinceTracking"]
    assert windows["recent"].matches == 2


def test_to_dict_matches_the_published_contract_keys():
    window = Window.of([record(kills=12, deaths=0, hits=(3, 9, 0))])

    assert window.to_dict() == {
        "matches": 1,
        "wins": 1,
        "losses": 0,
        "draws": 0,
        "kills": 12,
        "deaths": 0,
        "assists": 3,
        "headshots": 3,
        "bodyshots": 9,
        "legshots": 0,
        "kd": 12.0,
        "winRate": 1.0,
        "headshotRate": 0.25,
    }

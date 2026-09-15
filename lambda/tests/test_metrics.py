import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from shared.metrics import Match, calculate_metrics


def test_metrics_use_last_fifteen_and_clamp_zero_deaths():
    matches = [Match(str(index), index % 2 == 0, 10, 0 if index == 0 else 5, 3, 4, 20) for index in range(16)]
    result = calculate_metrics(matches)
    assert result["recent"]["sampleSize"] == 15
    assert result["recent"]["kda"] == 150 / 70
    assert result["lifetime"]["sampleSize"] == 16
    assert result["recent"]["kills"] == 150


def test_empty_metrics_are_zero():
    result = calculate_metrics([])
    assert result["recent"]["kda"] == 0
    assert result["lifetime"]["winRate"] == 0
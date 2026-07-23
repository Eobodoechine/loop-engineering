import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402
from duration import parse_duration  # noqa: E402


def test_hours_minutes():
    assert parse_duration("1h30m") == 5400


def test_minutes_only():
    assert parse_duration("45m") == 2700


def test_seconds_only():
    assert parse_duration("90s") == 90


def test_combined_hms():
    assert parse_duration("2h15m30s") == 8130


def test_whitespace_and_case():
    assert parse_duration("  1H 30M ") == 5400


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_duration("")


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_duration("banana")

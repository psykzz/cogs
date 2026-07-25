from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from when_cog.parser import find_time


@pytest.fixture
def now():
    return datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("See you in an hour.", datetime(2026, 7, 25, 13, 0, tzinfo=timezone.utc)),
        ("Meet in 3 days.", datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)),
        ("It was 5 minutes ago.", datetime(2026, 7, 25, 11, 55, tzinfo=timezone.utc)),
        ("An hour ago", datetime(2026, 7, 25, 11, 0, tzinfo=timezone.utc)),
        ("Tomorrow at 7:30 pm", datetime(2026, 7, 26, 19, 30, tzinfo=timezone.utc)),
        ("On Tuesday at 7", datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc)),
    ],
)
def test_finds_supported_time_expressions(now, content, expected):
    assert find_time(content, now) == expected


def test_uses_configured_timezone_for_weekdays():
    london = ZoneInfo("Europe/London")
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc).astimezone(london)

    assert find_time("On Tuesday at 7", now) == datetime(
        2026, 7, 28, 6, 0, tzinfo=timezone.utc
    )


def test_does_not_return_a_past_time_today(now):
    assert find_time("today at 7am", now) is None

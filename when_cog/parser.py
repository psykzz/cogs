import re
from datetime import datetime, timedelta, timezone
from typing import Optional

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

TIME_PATTERN = (
    r"(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:a\.?m\.?|p\.?m\.?)?"
)
RELATIVE_PATTERN = re.compile(
    rf"\bin\s+(?P<amount>an?|one|\d+)\s+"
    rf"(?P<unit>seconds?|minutes?|hours?|days?|weeks?)"
    rf"(?:\s+at\s+(?P<time>{TIME_PATTERN}))?\b",
    re.IGNORECASE,
)
PAST_PATTERN = re.compile(
    r"\b(?P<amount>an?|one|\d+)\s+"
    r"(?P<unit>seconds?|minutes?|hours?|days?|weeks?)\s+ago\b",
    re.IGNORECASE,
)
DAY_PATTERN = re.compile(
    rf"\b(?:on\s+)?(?:(?P<next>next)\s+)?"
    rf"(?P<weekday>{'|'.join(WEEKDAYS)})\s+at\s+(?P<time>{TIME_PATTERN})\b",
    re.IGNORECASE,
)
TODAY_TOMORROW_PATTERN = re.compile(
    rf"\b(?P<day>today|tomorrow)(?:\s+at\s+(?P<time>{TIME_PATTERN}))?\b",
    re.IGNORECASE,
)
CLOCK_PATTERN = re.compile(
    r"^(?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<period>a\.?m\.?|p\.?m\.?)?$",
    re.IGNORECASE,
)


def _parse_clock(value: str) -> Optional[tuple[int, int]]:
    match = CLOCK_PATTERN.fullmatch(value.strip())
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    period = (match.group("period") or "").lower().replace(".", "")
    if period:
        if not 1 <= hour <= 12:
            return None
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return hour, minute


def _with_clock(value: datetime, clock: str) -> Optional[datetime]:
    parsed_clock = _parse_clock(clock)
    if parsed_clock is None:
        return None
    hour, minute = parsed_clock
    return value.replace(hour=hour, minute=minute, second=0, microsecond=0)


def find_time(content: str, now: datetime) -> Optional[datetime]:
    """Return the first supported time expression in UTC."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    relative_match = RELATIVE_PATTERN.search(content)
    if relative_match:
        amount_text = relative_match.group("amount").lower()
        amount = 1 if amount_text in {"a", "an", "one"} else int(amount_text)
        unit = relative_match.group("unit").lower().rstrip("s")
        target = now + timedelta(**{unit + "s": amount})
        clock = relative_match.group("time")
        if clock:
            target = _with_clock(target, clock)
            if target is None:
                return None
        return target.astimezone(timezone.utc)

    past_match = PAST_PATTERN.search(content)
    if past_match:
        amount_text = past_match.group("amount").lower()
        amount = 1 if amount_text in {"a", "an", "one"} else int(amount_text)
        unit = past_match.group("unit").lower().rstrip("s")
        target = now - timedelta(**{unit + "s": amount})
        return target.astimezone(timezone.utc)

    local_now = now
    weekday_match = DAY_PATTERN.search(content)
    if weekday_match:
        weekday = WEEKDAYS[weekday_match.group("weekday").lower()]
        days = (weekday - local_now.weekday()) % 7
        if weekday_match.group("next"):
            days += 7
        target = _with_clock(local_now + timedelta(days=days), weekday_match.group("time"))
        if target is None:
            return None
        if target <= local_now:
            target += timedelta(days=7)
        return target.astimezone(timezone.utc)

    day_match = TODAY_TOMORROW_PATTERN.search(content)
    if day_match:
        days = 1 if day_match.group("day").lower() == "tomorrow" else 0
        target = local_now + timedelta(days=days)
        clock = day_match.group("time")
        if clock:
            target = _with_clock(target, clock)
            if target is None or target <= local_now:
                return None
        return target.astimezone(timezone.utc)

    return None

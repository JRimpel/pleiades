"""Time helpers. All timestamps in the DB and API are timezone-aware UTC."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .errors import bad_request

UTC = timezone.utc

# A "night" is the local window [18:00, 06:00 next day). The nightly continuous
# aggregate uses a noon-to-noon local day, which contains this window.
NIGHT_START = time(18, 0)
NIGHT_END = time(6, 0)


def utcnow() -> datetime:
    return datetime.now(UTC)


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_iso(value: str | None, *, field: str = "time") -> datetime | None:
    """Parse an ISO-8601 timestamp (accepts a trailing 'Z'). Naive values are treated as UTC."""
    if value is None or value == "":
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as e:
        raise bad_request(f"Invalid ISO-8601 timestamp for '{field}': {value!r}") from e
    return ensure_utc(dt)


def parse_date(value: str | None, *, field: str = "date") -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as e:
        raise bad_request(f"Invalid date for '{field}' (expected YYYY-MM-DD): {value!r}") from e


def night_window(night: date, tz: str) -> tuple[datetime, datetime]:
    """UTC [start, end) of the night that begins on local date `night`."""
    zone = ZoneInfo(tz)
    start = datetime.combine(night, NIGHT_START, tzinfo=zone)
    end = datetime.combine(night + timedelta(days=1), NIGHT_END, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def current_night(now: datetime, tz: str) -> date:
    """Local date of the night in progress or upcoming. Before local noon counts as last night."""
    local = now.astimezone(ZoneInfo(tz))
    return local.date() - timedelta(days=1) if local.time() < time(12, 0) else local.date()


def local_day_window(day: date, tz: str) -> tuple[datetime, datetime]:
    """UTC [start, end) of a local calendar day."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time(0, 0), tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)

"""Timestamps and calendar dates. RFC 0001 sections 6.1 and 8."""

from datetime import UTC, date, datetime, timedelta


def utc(value: datetime) -> datetime:
    """Naive values are read as UTC. Every timestamp the kernel holds is aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def now() -> datetime:
    return datetime.now(UTC)


def later_than(previous: datetime | None, candidate: datetime) -> datetime:
    """A `modified` strictly later than `previous` (RFC 0004 section 3)."""
    candidate = utc(candidate)
    if previous is not None and candidate <= utc(previous):
        return utc(previous) + timedelta(microseconds=1)
    return candidate


def format_timestamp(value: datetime) -> str:
    value = utc(value)
    text = value.strftime("%Y-%m-%dT%H:%M:%S")
    if value.microsecond:
        text += f".{value.microsecond:06d}"
    return text + "Z"


def on_or_after(day: date | None, evaluation_date: date) -> bool:
    """A calendar date includes the whole of that UTC day. None means no end."""
    return day is None or day >= evaluation_date


# RFC 0001 section 8. `event-driven` uses the result's own `valid_until`.
FRESHNESS_DAYS: dict[str, int] = {
    "continuous": 1,
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}

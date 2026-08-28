"""Canonical employer posting time. Never treat scrape/discovery as posted-at."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

# Provider epoch leftovers (Himalayas and similar) must not become 1970 postings.
_MIN_TRUSTWORTHY = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MAX_FUTURE_SKEW = timedelta(days=2)
# Unix microseconds are 15+ digits. Do not guess by dividing twice.
_MICROSECOND_THRESHOLD = 1e14
# 13-digit values are milliseconds. 1e10 seconds is already year 2286.
_MILLISECOND_THRESHOLD = 1e11


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_posted_at(raw: str | None, *, now: datetime | None = None) -> datetime | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    clock = _aware(now) or datetime.now(timezone.utc)
    parsed: datetime | None = None
    if value.replace(".", "", 1).isdigit():
        try:
            timestamp = float(value)
        except ValueError:
            return None
        if not math.isfinite(timestamp) or timestamp < 0:
            return None
        if timestamp >= _MICROSECOND_THRESHOLD:
            return None
        if timestamp >= _MILLISECOND_THRESHOLD:
            timestamp /= 1000.0
        try:
            parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(value[:10], "%Y-%m-%d")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
    if parsed < _MIN_TRUSTWORTHY or parsed > clock + _MAX_FUTURE_SKEW:
        return None
    return parsed


def job_posting_datetime(
    date_posted: str | None,
    date_scraped: datetime | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Valid employer posting time only. Discovery/scrape is never posting time."""
    return parse_posted_at(date_posted, now=now)


def discovery_datetime(date_scraped: datetime | None) -> datetime | None:
    return _aware(date_scraped)


def posted_date_for_display(date_posted: str | None, *, now: datetime | None = None) -> date | None:
    parsed = parse_posted_at(date_posted, now=now)
    return parsed.date() if parsed else None

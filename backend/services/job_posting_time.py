"""Canonical employer posting time. Never treat scrape/discovery as posted-at.

Date-only provider values (YYYY-MM-DD) are calendar dates, not midnight UTC
instants. Filters must not pretend 00:00 UTC is the posting time.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

# Provider epoch leftovers (Himalayas and similar) must not become 1970 postings.
_MIN_TRUSTWORTHY = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MAX_FUTURE_SKEW = timedelta(days=2)
# Unix microseconds are 15+ digits. Do not guess by dividing twice.
_MICROSECOND_THRESHOLD = 1e14
# 13-digit values are milliseconds. 1e10 seconds is already year 2286.
_MILLISECOND_THRESHOLD = 1e11
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DATE_POSTED_WINDOWS = {
    "past_24h": timedelta(hours=24),
    "past_3d": timedelta(days=3),
    "past_7d": timedelta(days=7),
    "past_14d": timedelta(days=14),
    "past_30d": timedelta(days=30),
}

PostingPrecision = Literal["datetime", "date"]


@dataclass(frozen=True)
class ParsedPostingTime:
    """Employer posting time with preserved precision.

    ``value`` for date-only inputs is a UTC calendar-day anchor (midnight).
    That anchor is not a claimed posting instant; callers must consult
    ``precision`` before doing timestamp comparisons.
    """

    value: datetime
    precision: PostingPrecision


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_posting_time(raw: str | None, *, now: datetime | None = None) -> ParsedPostingTime | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    clock = _aware(now) or datetime.now(timezone.utc)
    parsed: datetime | None = None
    precision: PostingPrecision = "datetime"
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
        date_only = _DATE_ONLY.fullmatch(value) is not None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(value[:10], "%Y-%m-%d")
            except ValueError:
                return None
            date_only = True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        if date_only:
            precision = "date"
            parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    if parsed < _MIN_TRUSTWORTHY or parsed > clock + _MAX_FUTURE_SKEW:
        return None
    return ParsedPostingTime(value=parsed, precision=precision)


def parse_posted_at(raw: str | None, *, now: datetime | None = None) -> datetime | None:
    parsed = parse_posting_time(raw, now=now)
    return parsed.value if parsed else None


def job_posting_datetime(
    date_posted: str | None,
    date_scraped: datetime | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Valid employer posting time only. Discovery/scrape is never posting time.

    Date-only values return a UTC calendar-day anchor, not a claimed instant.
    Use ``parse_posting_time`` when filter semantics depend on precision.
    """
    return parse_posted_at(date_posted, now=now)


def discovery_datetime(date_scraped: datetime | None) -> datetime | None:
    return _aware(date_scraped)


def posted_date_for_display(date_posted: str | None, *, now: datetime | None = None) -> date | None:
    parsed = parse_posting_time(date_posted, now=now)
    return parsed.value.date() if parsed else None


def cutoff_for_date_posted_window(window: str | None, now: datetime) -> datetime | None:
    delta = DATE_POSTED_WINDOWS.get(window or "")
    return now - delta if delta else None


def posting_in_window(parsed: ParsedPostingTime, cutoff: datetime, now: datetime) -> bool:
    """Whether a posting falls in ``[cutoff, now]``.

    Exact timestamps compare as instants.

    Date-only values use UTC calendar-date intersection: include the posting
    when its calendar date overlaps the requested window. A date-only
    ``2026-08-30`` at ``now=2026-08-31T03:00Z`` (Past 24h) is included because
    30 Aug still intersects the window, even though fake midnight 00:00 UTC
    would fall before the cutoff.
    """
    if parsed.precision == "datetime":
        return parsed.value >= cutoff
    day = parsed.value.date()
    return cutoff.date() <= day <= now.date()

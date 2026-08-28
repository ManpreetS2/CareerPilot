"""Canonical employer posting time. Never treat scrape/discovery as posted-at."""

from __future__ import annotations

from datetime import date, datetime, timezone

# Provider epoch leftovers (Himalayas and similar) must not become 1970 postings.
_MIN_TRUSTWORTHY = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_posted_at(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value.replace(".", "", 1).isdigit():
        try:
            timestamp = float(value)
        except ValueError:
            return None
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        if timestamp < 0:
            return None
        parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return parsed if parsed >= _MIN_TRUSTWORTHY else None

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
    if parsed < _MIN_TRUSTWORTHY:
        return None
    return parsed


def job_posting_datetime(date_posted: str | None, date_scraped: datetime | None) -> datetime | None:
    """Prefer a trustworthy employer/provider date_posted; scrape time is fallback only."""
    posted = parse_posted_at(date_posted)
    if posted is not None:
        return posted
    return _aware(date_scraped)


def posted_date_for_display(date_posted: str | None) -> date | None:
    parsed = parse_posted_at(date_posted)
    return parsed.date() if parsed else None

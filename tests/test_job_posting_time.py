"""Posted-at parser: support ISO/unix, reject garbage and absurd future dates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.job_posting_time import discovery_datetime, job_posting_datetime, parse_posted_at


NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def test_parse_posted_at_accepts_iso_and_unix_seconds_and_milliseconds() -> None:
    iso_date = parse_posted_at("2026-08-20", now=NOW)
    iso_datetime = parse_posted_at("2026-08-20T15:30:00Z", now=NOW)
    seconds = parse_posted_at(str(int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp())), now=NOW)
    millis = parse_posted_at(
        str(int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp() * 1000)),
        now=NOW,
    )
    assert iso_date is not None and iso_date.date().isoformat() == "2026-08-20"
    assert iso_datetime is not None and iso_datetime.hour == 15
    assert seconds is not None and seconds.date().isoformat() == "2026-08-20"
    assert millis is not None and millis.date().isoformat() == "2026-08-20"


def test_parse_posted_at_rejects_microseconds_garbage_and_future_dates() -> None:
    assert parse_posted_at("1717000000000000", now=NOW) is None
    assert parse_posted_at("9999999999999999", now=NOW) is None
    assert parse_posted_at("9999999999999", now=NOW) is None
    assert parse_posted_at("NaN", now=NOW) is None
    assert parse_posted_at("Infinity", now=NOW) is None
    assert parse_posted_at("not-a-date", now=NOW) is None
    far_future = (NOW + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert parse_posted_at(far_future, now=NOW) is None
    slightly_ahead = (NOW + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert parse_posted_at(slightly_ahead, now=NOW) is not None


def test_job_posting_datetime_does_not_treat_scrape_time_as_posted_at() -> None:
    scraped = NOW
    assert job_posting_datetime("2026-08-20T15:30:00Z", scraped, now=NOW) is not None
    assert job_posting_datetime(None, scraped, now=NOW) is None
    assert job_posting_datetime("not-a-date", scraped, now=NOW) is None
    assert job_posting_datetime("1970-01-01", scraped, now=NOW) is None
    assert discovery_datetime(scraped) == scraped

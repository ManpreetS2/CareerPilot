"""Posted-at parser: support ISO/unix, reject garbage and absurd future dates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.job_posting_time import (
    cutoff_for_date_posted_window,
    discovery_datetime,
    job_posting_datetime,
    parse_posted_at,
    parse_posting_time,
    posting_in_window,
)


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


def test_parse_posting_time_distinguishes_date_only_from_exact_timestamp() -> None:
    date_only = parse_posting_time("2026-08-20", now=NOW)
    exact = parse_posting_time("2026-08-20T15:30:00Z", now=NOW)
    midnight_claimed = parse_posting_time("2026-08-20T00:00:00Z", now=NOW)
    seconds = parse_posting_time(str(int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp())), now=NOW)
    millis = parse_posting_time(
        str(int(datetime(2026, 8, 20, tzinfo=timezone.utc).timestamp() * 1000)),
        now=NOW,
    )
    assert date_only is not None and date_only.precision == "date"
    assert date_only.value.date().isoformat() == "2026-08-20"
    assert exact is not None and exact.precision == "datetime" and exact.value.hour == 15
    assert midnight_claimed is not None and midnight_claimed.precision == "datetime"
    assert seconds is not None and seconds.precision == "datetime"
    assert millis is not None and millis.precision == "datetime"


def test_parse_posted_at_rejects_microseconds_garbage_and_future_dates() -> None:
    assert parse_posted_at("1717000000000000", now=NOW) is None
    assert parse_posted_at("9999999999999999", now=NOW) is None
    assert parse_posted_at("9999999999999", now=NOW) is None
    assert parse_posted_at("NaN", now=NOW) is None
    assert parse_posted_at("Infinity", now=NOW) is None
    assert parse_posted_at("not-a-date", now=NOW) is None
    assert parse_posting_time("1717000000000000", now=NOW) is None
    assert parse_posting_time("not-a-date", now=NOW) is None
    far_future = (NOW + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert parse_posted_at(far_future, now=NOW) is None
    slightly_ahead = (NOW + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert parse_posted_at(slightly_ahead, now=NOW) is not None
    assert parse_posted_at("1970-01-01", now=NOW) is None
    assert parse_posting_time("1970-01-01", now=NOW) is None


def test_job_posting_datetime_does_not_treat_scrape_time_as_posted_at() -> None:
    scraped = NOW
    assert job_posting_datetime("2026-08-20T15:30:00Z", scraped, now=NOW) is not None
    assert job_posting_datetime(None, scraped, now=NOW) is None
    assert job_posting_datetime("not-a-date", scraped, now=NOW) is None
    assert job_posting_datetime("1970-01-01", scraped, now=NOW) is None
    assert discovery_datetime(scraped) == scraped


def test_date_only_past_24h_uses_calendar_intersection_independent_of_utc_hour() -> None:
    early = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)
    late = datetime(2026, 8, 31, 23, 30, tzinfo=timezone.utc)
    date_aug_30 = parse_posting_time("2026-08-30", now=early)
    date_aug_31 = parse_posting_time("2026-08-31", now=late)
    exact_aug_30_afternoon = parse_posting_time("2026-08-30T15:00:00Z", now=early)
    exact_recent = parse_posting_time("2026-08-31T22:00:00Z", now=late)
    assert date_aug_30 is not None and date_aug_30.precision == "date"
    assert date_aug_31 is not None and date_aug_31.precision == "date"
    assert exact_aug_30_afternoon is not None and exact_aug_30_afternoon.precision == "datetime"
    assert exact_recent is not None and exact_recent.precision == "datetime"

    early_cutoff = cutoff_for_date_posted_window("past_24h", early)
    late_cutoff = cutoff_for_date_posted_window("past_24h", late)
    assert early_cutoff == datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc)
    assert late_cutoff == datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc)

    assert posting_in_window(date_aug_30, early_cutoff, early) is True
    assert posting_in_window(date_aug_31, late_cutoff, late) is True
    assert posting_in_window(exact_aug_30_afternoon, early_cutoff, early) is True
    assert posting_in_window(exact_aug_30_afternoon, late_cutoff, late) is False
    assert posting_in_window(exact_recent, late_cutoff, late) is True
    # Fake midnight 2026-08-30 00:00Z would miss Past 24h at 03:00Z; calendar intersection must not.
    assert date_aug_30.value < early_cutoff
    assert posting_in_window(date_aug_30, early_cutoff, early) is True

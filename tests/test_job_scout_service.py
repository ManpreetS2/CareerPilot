"""Job Scout normalization/dedup tests. No network calls — scout_adzuna,
scout_remoteok, and ingest_job_url hit live services and are covered by
manual verification instead."""

from __future__ import annotations

from datetime import date

from backend.services.job_scout_service import (
    _clean_description,
    _clean_line,
    _dedupe_key,
    _format_salary,
    _normalize_url,
    deduplicate_jobs,
    normalize_job,
)


def test_normalize_adzuna_job() -> None:
    raw = {
        "title": "Software Engineer Intern",
        "company": {"display_name": "Aether Analytics"},
        "location": {"display_name": "San Francisco, CA"},
        "redirect_url": "https://www.adzuna.com/land/ad/1234",
        "description": "Build things.",
        "created": "2026-08-15T10:00:00Z",
        "salary_min": 40000,
        "salary_max": 60000,
    }
    job = normalize_job(raw, "adzuna")
    assert job.title == "Software Engineer Intern"
    assert job.company == "Aether Analytics"
    assert job.location == "San Francisco, CA"
    assert job.source == "adzuna"
    assert job.salary == "$40,000–$60,000"
    assert job.date_posted == date(2026, 8, 15)
    assert job.status == "discovered"


def test_normalize_remoteok_job_fixes_html_entities_and_strips_markup() -> None:
    raw = {
        "position": "Costing Engineer",
        "company": "Larsen &amp; Toubro",
        "location": "Coimbatore South, ",
        "url": "https://remoteok.com/remote-jobs/1",
        "description": "<strong>Role</strong><br>Own <ul><li>costing</li></ul> work.",
        "date": "2026-08-19T18:17:34+00:00",
        "salary_min": 0,
        "salary_max": 0,
    }
    job = normalize_job(raw, "remoteok")
    assert job.company == "Larsen & Toubro"
    assert "<" not in job.description
    assert "Role" in job.description
    assert job.salary is None  # zero/zero should not render as a fake salary


def test_normalize_remoteok_job_fixes_mojibake() -> None:
    raw = {
        "position": "Costing Engineer â Jigs & Fixtures",
        "company": "Acme",
        "url": "https://remoteok.com/remote-jobs/2",
        "description": "",
    }
    job = normalize_job(raw, "remoteok")
    assert job.title == "Costing Engineer – Jigs & Fixtures"


def test_normalize_manual_job() -> None:
    raw = {
        "title": "Jobs at Acme",
        "company": "Acme",
        "url": "https://acme.com/jobs/1",
        "description": "Manually added.",
    }
    job = normalize_job(raw, "manual")
    assert job.source == "manual"
    assert job.status == "discovered"
    assert job.date_posted is None


def test_format_salary_handles_missing_and_equal_values() -> None:
    assert _format_salary(None, None) is None
    assert _format_salary(0, 0) is None
    assert _format_salary(50000, 50000) == "$50,000"
    assert _format_salary(40000, 60000) == "$40,000–$60,000"


def test_clean_line_and_description_round_trip() -> None:
    assert _clean_line("  Larsen  &amp;   Toubro  ") == "Larsen & Toubro"
    assert _clean_description(None) == ""
    cleaned = _clean_description("<p>Line one</p><p>Line two &amp; more</p>")
    assert cleaned == "Line one\nLine two & more"


def test_normalize_url_ignores_scheme_www_query_and_trailing_slash() -> None:
    a = _normalize_url("https://www.Example.com/jobs/123/?utm=abc")
    b = _normalize_url("http://example.com/jobs/123")
    assert a == b


def test_deduplicate_jobs_by_normalized_url() -> None:
    job_a = normalize_job(
        {"title": "A", "company": "Acme", "url": "https://example.com/jobs/1/", "description": ""},
        "manual",
    )
    job_b = normalize_job(
        {"title": "A dup", "company": "Acme", "url": "https://www.example.com/jobs/1", "description": ""},
        "manual",
    )
    job_c = normalize_job(
        {"title": "B", "company": "Acme", "url": "https://example.com/jobs/2", "description": ""},
        "manual",
    )
    deduped = deduplicate_jobs([job_a, job_b, job_c])
    assert len(deduped) == 2
    assert deduped[0].title == "A"  # first occurrence wins


def test_deduplicate_jobs_falls_back_to_fingerprint_without_url() -> None:
    job_a = normalize_job({"title": "A", "company": "Acme", "url": "", "description": ""}, "manual")
    job_b = normalize_job({"title": "A", "company": "Acme", "url": "", "description": ""}, "manual")
    assert _dedupe_key(job_a) == _dedupe_key(job_b)
    assert len(deduplicate_jobs([job_a, job_b])) == 1

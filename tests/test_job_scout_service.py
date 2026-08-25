"""Job Scout normalization/dedup tests. No network calls — scout_adzuna and
scout_remoteok hit live third-party services and are covered by manual
verification instead. ingest_job_url is the exception: it takes a
user-supplied URL (not a hardcoded trusted endpoint), so its outbound-fetch
safety is tested here with a mocked transport — see also test_url_safety.py
for the shared validator's own unit tests."""

from __future__ import annotations

import socket
from datetime import date

import httpx
import pytest

from backend.services.job_scout_service import (
    JobScoutError,
    _clean_description,
    _clean_line,
    _dedupe_key,
    _format_salary,
    _guess_company,
    _normalize_listings,
    _normalize_url,
    deduplicate_jobs,
    ingest_job_url,
    normalize_job,
)
from backend.services.url_safety import UnsafeURLError

_RealClient = httpx.Client  # captured before any test monkeypatches httpx.Client itself


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


def test_normalize_url_ignores_tracking_parameters() -> None:
    a = _normalize_url("https://example.com/jobs/123?utm_source=linkedin&utm_campaign=spring")
    b = _normalize_url("https://example.com/jobs/123")
    assert a == b


def test_normalize_url_ignores_fragment() -> None:
    a = _normalize_url("https://example.com/jobs/123#apply-section")
    b = _normalize_url("https://example.com/jobs/123")
    assert a == b


def test_normalize_url_treats_greenhouse_and_lever_urls_as_ordinary_paths() -> None:
    """No ATS-specific normalization beyond the generic scheme/www/query/
    fragment stripping — two URLs differing only in query/fragment noise
    dedupe together; genuinely different paths (different postings) do not."""
    same_posting_a = _normalize_url("https://boards.greenhouse.io/acme/jobs/12345?gh_src=abc")
    same_posting_b = _normalize_url("https://boards.greenhouse.io/acme/jobs/12345#content")
    assert same_posting_a == same_posting_b

    different_posting = _normalize_url("https://boards.greenhouse.io/acme/jobs/67890")
    assert same_posting_a != different_posting


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


def test_guess_company_from_greenhouse_path_not_subdomain() -> None:
    assert _guess_company("https://boards.greenhouse.io/acmecorp/jobs/12345") == "Acmecorp"
    assert _guess_company("https://job-boards.greenhouse.io/acme-corp/jobs/1") == "Acme Corp"


def test_guess_company_from_lever_path_not_subdomain() -> None:
    assert _guess_company("https://jobs.lever.co/acmecorp/abc-123") == "Acmecorp"


def test_guess_company_from_subdomain_for_other_hosts() -> None:
    assert _guess_company("https://acme.wd5.myworkdayjobs.com/careers/job/1") == "Acme"


def test_guess_company_unknown_when_no_host() -> None:
    assert _guess_company("") == "Unknown"


def test_normalize_listings_skips_malformed_record_not_whole_batch() -> None:
    good = {
        "title": "Good Job",
        "company": {"display_name": "Acme"},
        "redirect_url": "https://example.com/1",
        "description": "",
    }
    bad = {
        "title": "Bad Job",
        "company": {"display_name": "Acme"},
        "redirect_url": "https://example.com/2",
        "salary_min": "not-a-number",
    }
    another_good = {
        "title": "Another Good Job",
        "company": {"display_name": "Acme"},
        "redirect_url": "https://example.com/3",
        "description": "",
    }
    jobs = _normalize_listings([good, bad, another_good], "adzuna")
    assert [job.title for job in jobs] == ["Good Job", "Another Good Job"]


# ---------------------------------------------------------------------------
# ingest_job_url — outbound-fetch safety (SSRF regression). Real, previously
# unguarded gap: the server fetched any user-supplied URL with no scheme,
# host, or redirect-target validation. Mocked transport, no real network.
# ---------------------------------------------------------------------------


def _fake_resolve(ip: str):
    def _getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _getaddrinfo


def test_ingest_job_url_rejects_a_private_address_and_makes_no_request(monkeypatch) -> None:
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text="<title>internal admin panel</title>")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(UnsafeURLError):
        ingest_job_url("https://127.0.0.1:9000/admin")
    assert called["n"] == 0


def test_ingest_job_url_rejects_a_redirect_into_a_private_address(monkeypatch) -> None:
    """The URL the user submits looks like an ordinary public posting; the
    site redirects into a private address. This is the scenario an initial-
    URL-only check (the old code had none at all) would still miss."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://10.0.0.5/internal"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(UnsafeURLError):
        ingest_job_url("https://example.com/jobs/1")


def test_ingest_job_url_succeeds_for_a_safe_https_url(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<html><head><title>Backend Intern</title>'
            '<meta name="description" content="Great role."></head></html>',
        )

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    result = ingest_job_url("https://example.com/jobs/1")
    assert result["title"] == "Backend Intern"
    assert result["description"] == "Great role."


def test_ingest_job_url_wraps_a_real_http_error_as_job_scout_error(monkeypatch) -> None:
    """A genuine (safe-target) network/HTTP failure still raises the existing
    JobScoutError contract the route already handles — unrelated to the new
    safety check, and must not regress."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: _RealClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(JobScoutError):
        ingest_job_url("https://example.com/gone")

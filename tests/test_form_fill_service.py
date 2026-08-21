"""Form Fill / Assisted Apply Agent tests.

Split into three layers:
1. Pure function tests — no Playwright, no DB.
2. Orchestration tests (isolated_session) — the approval gate, 404/409s,
   and the unsupported-platform path all return before a browser ever
   launches, so these run without Playwright too.
3. Real Playwright tests against static local HTML fixtures shaped like
   real Greenhouse/Lever forms (tests/fixtures/ats_forms/) — deterministic,
   no live network calls, same "fixtures over live calls" philosophy as
   the rest of this test suite.

A safety meta-test at the bottom guards the single most important
invariant of this module: the automation must never click a submit
control.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from playwright.sync_api import sync_playwright

from backend.db.models import ApplicationPackageRecord, Candidate, FormFillAttemptRecord, JobRecord
from backend.services import form_fill_service
from backend.services.form_fill_service import (
    _build_candidate_fields,
    _current_company,
    _fill_greenhouse,
    _fill_lever,
    _first_url,
    _navigation_url,
    _split_name,
    detect_ats_platform,
    run_assisted_apply,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ats_forms"


def _fixture_url(name: str) -> str:
    return f"file://{(FIXTURES_DIR / name).resolve()}"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://boards.greenhouse.io/acme/jobs/12345",
        "https://job-boards.greenhouse.io/acme/jobs/12345",
        "https://www.greenhouse.io/embed/job_app?token=123",
    ],
)
def test_detect_ats_platform_greenhouse(url) -> None:
    assert detect_ats_platform(url) == "greenhouse"


@pytest.mark.parametrize("url", ["https://jobs.lever.co/acme/abc-123", "https://www.lever.co/acme/abc-123"])
def test_detect_ats_platform_lever(url) -> None:
    assert detect_ats_platform(url) == "lever"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/jobs/123",
        "https://linkedin.com/jobs/view/123",
        "",
        "not-a-url",
    ],
)
def test_detect_ats_platform_unsupported(url) -> None:
    assert detect_ats_platform(url) == "unsupported"


def test_detect_ats_platform_does_not_false_positive_on_unrelated_host_containing_the_word() -> None:
    # "greenhouse.io.evil.com" is NOT greenhouse.io — must not match on substring.
    assert detect_ats_platform("https://greenhouse.io.evil.com/jobs/1") == "unsupported"


def test_navigation_url_appends_apply_for_lever() -> None:
    """Regression test for a real bug caught testing against multiple live
    Lever postings: the posting/description URL (what gets scouted and
    stored) has zero form fields in the DOM — Lever only mounts the actual
    application form at "{posting_url}/apply"."""
    assert (
        _navigation_url("https://jobs.lever.co/acme/abc-123", "lever")
        == "https://jobs.lever.co/acme/abc-123/apply"
    )


def test_navigation_url_does_not_double_append_apply_for_lever() -> None:
    assert (
        _navigation_url("https://jobs.lever.co/acme/abc-123/apply", "lever")
        == "https://jobs.lever.co/acme/abc-123/apply"
    )
    # Already ends with /apply (trailing slash or not) — left as-is rather
    # than double-appended.
    assert (
        _navigation_url("https://jobs.lever.co/acme/abc-123/apply/", "lever")
        == "https://jobs.lever.co/acme/abc-123/apply/"
    )


def test_navigation_url_unchanged_for_greenhouse() -> None:
    # Confirmed by testing against a real posting: unlike Lever, the
    # Greenhouse form is present on the posting page itself.
    url = "https://job-boards.greenhouse.io/acme/jobs/12345"
    assert _navigation_url(url, "greenhouse") == url


def test_split_name_two_words() -> None:
    assert _split_name("Jordan Quill") == ("Jordan", "Quill")


def test_split_name_multiple_words_keeps_remainder_as_last() -> None:
    assert _split_name("Mary Jane Watson") == ("Mary", "Jane Watson")


def test_split_name_single_word() -> None:
    assert _split_name("Cher") == ("Cher", "")


def test_split_name_empty() -> None:
    assert _split_name("") == ("", "")


def test_split_name_extra_whitespace() -> None:
    assert _split_name("  Jordan   Quill  ") == ("Jordan", "Quill")


def _candidate(**overrides) -> Candidate:
    defaults = dict(
        name="Jordan Quill",
        email="jordan@example.com",
        phone="+1-555-0100",
        skills=[],
        projects=[],
        experience=[],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    defaults.update(overrides)
    return Candidate(**defaults)


def test_current_company_finds_entry_with_empty_end_date() -> None:
    candidate = _candidate(experience=[{"title": "Engineer", "company": "Acme", "end_date": ""}])
    assert _current_company(candidate) == "Acme"


def test_current_company_finds_entry_marked_present() -> None:
    candidate = _candidate(experience=[{"title": "Engineer", "company": "Acme", "end_date": "Present"}])
    assert _current_company(candidate) == "Acme"


def test_current_company_case_insensitive_present() -> None:
    candidate = _candidate(experience=[{"title": "Engineer", "company": "Acme", "end_date": "PRESENT"}])
    assert _current_company(candidate) == "Acme"


def test_current_company_none_when_all_roles_have_end_dates() -> None:
    candidate = _candidate(experience=[{"title": "Engineer", "company": "Acme", "end_date": "2020-01"}])
    assert _current_company(candidate) is None


def test_current_company_none_when_no_experience() -> None:
    assert _current_company(_candidate(experience=[])) is None


def test_current_company_handles_missing_company_key_gracefully() -> None:
    candidate = _candidate(experience=[{"title": "Engineer", "end_date": ""}])
    assert _current_company(candidate) is None


def test_first_url_finds_http_link() -> None:
    assert _first_url(["not a url", "https://portfolio.example.com"]) == "https://portfolio.example.com"


def test_first_url_none_without_any_url() -> None:
    assert _first_url(["just some text", "github.com/no-scheme"]) is None


def test_first_url_none_for_empty_list() -> None:
    assert _first_url([]) is None


def test_build_candidate_fields_maps_all_sources() -> None:
    candidate = _candidate(
        name="Jordan Quill",
        experience=[{"company": "Acme", "end_date": "Present"}],
        evidence_links=["https://portfolio.example.com"],
    )
    package = ApplicationPackageRecord(job_id=1, cover_letter_draft="Dear team,", tailored_bullets=[], source_traceability_notes=[])
    fields = _build_candidate_fields(candidate, package)
    assert fields.full_name == "Jordan Quill"
    assert fields.first_name == "Jordan"
    assert fields.last_name == "Quill"
    assert fields.current_company == "Acme"
    assert fields.portfolio_url == "https://portfolio.example.com"
    assert fields.cover_letter == "Dear team,"


# ---------------------------------------------------------------------------
# Orchestration: approval gate, error paths — no Playwright needed since
# these all return before a browser launches.
# ---------------------------------------------------------------------------


def _job(session, *, public_id: str = "manual-abc123", url: str = "https://example.com/jobs/1") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineer Intern",
        company="Acme",
        url=url,
        description="Build things.",
        source="manual",
        status="discovered",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _seed_candidate(session) -> Candidate:
    candidate = _candidate()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _approved_package(session, job: JobRecord, candidate: Candidate | None) -> ApplicationPackageRecord:
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id if candidate else None,
        tailored_bullets=[],
        cover_letter_draft="Dear hiring team,",
        source_traceability_notes=[],
        approval_status="approved",
        eligibility_confirmed=True,
    )
    session.add(record)
    session.commit()
    return record


def test_run_assisted_apply_missing_job_404s(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "does-not-exist")
    assert exc_info.value.status_code == 404


def test_run_assisted_apply_without_package_409s(isolated_session) -> None:
    _job(isolated_session)
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123")
    assert exc_info.value.status_code == 409


def test_run_assisted_apply_unapproved_package_409s(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _seed_candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        tailored_bullets=[],
        source_traceability_notes=[],
        approval_status="pending_review",
    )
    isolated_session.add(record)
    isolated_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123")
    assert exc_info.value.status_code == 409
    assert "approved" in exc_info.value.detail.lower()


def test_run_assisted_apply_without_candidate_409s(isolated_session) -> None:
    job = _job(isolated_session)
    _approved_package(isolated_session, job, candidate=None)
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123")
    assert exc_info.value.status_code == 409
    assert "candidate" in exc_info.value.detail.lower()


def test_run_assisted_apply_unsupported_platform_persists_failed_result(isolated_session) -> None:
    job = _job(isolated_session, url="https://example.com/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    result = run_assisted_apply(isolated_session, "manual-abc123")

    assert result.status == "failed"
    assert result.ats_platform == "unsupported"
    assert "greenhouse" in (result.error_message or "").lower()
    assert isolated_session.query(FormFillAttemptRecord).count() == 1


def test_run_assisted_apply_multiple_attempts_are_not_upserted(isolated_session) -> None:
    job = _job(isolated_session, url="https://example.com/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    run_assisted_apply(isolated_session, "manual-abc123")
    run_assisted_apply(isolated_session, "manual-abc123")

    assert isolated_session.query(FormFillAttemptRecord).count() == 2


# ---------------------------------------------------------------------------
# Real Playwright field-fill tests against static local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def browser():
    # Function-scoped, not module-scoped: Playwright's sync API doesn't
    # support two overlapping sync_playwright() contexts in the same
    # thread, and run_assisted_apply() opens its own internally — a
    # module-scoped fixture staying open across the whole file would
    # collide with that the moment a full-orchestration test runs.
    with sync_playwright() as playwright:
        b = playwright.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    p = browser.new_page()
    yield p
    p.close()


def _fields(**overrides):
    candidate = _candidate(**{k: v for k, v in overrides.items() if k in ("name", "email", "phone", "experience", "evidence_links")})
    package = ApplicationPackageRecord(
        job_id=1,
        cover_letter_draft=overrides.get("cover_letter", "Dear hiring team, I would love to join."),
        tailored_bullets=[],
        source_traceability_notes=[],
    )
    return _build_candidate_fields(candidate, package)


def test_fill_greenhouse_standard_fills_mappable_fields(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(name="Jordan Quill", experience=[{"company": "Acme", "end_date": "Present"}])

    filled, flagged = _fill_greenhouse(page, fields)

    assert "first_name" in filled
    assert "last_name" in filled
    assert "email" in filled
    assert "phone" in filled
    assert "current_company" in filled
    assert "cover_letter" in filled
    assert page.locator("#first_name").input_value() == "Jordan"
    assert page.locator("#last_name").input_value() == "Quill"
    assert page.locator("#email").input_value() == "jordan@example.com"
    assert page.locator("#company").input_value() == "Acme"


def test_fill_greenhouse_flags_resume_upload(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields()
    _, flagged = _fill_greenhouse(page, fields)
    resume_flags = [f for f in flagged if f.field == "resume"]
    assert len(resume_flags) == 1
    assert "attach your resume" in resume_flags[0].reason.lower()


def test_fill_greenhouse_flags_custom_required_question(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields()
    _, flagged = _fill_greenhouse(page, fields)
    flagged_names = {f.field for f in flagged}
    assert "job_application[answers][0][text_value]" in flagged_names


def test_fill_greenhouse_never_leaves_a_required_field_silently_unflagged(page) -> None:
    """Every required input on the page ends up either filled or flagged —
    none are silently skipped."""
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(name="Jordan Quill")
    filled, flagged = _fill_greenhouse(page, fields)

    required_inputs = page.locator("input[required], textarea[required]")
    for i in range(required_inputs.count()):
        el = required_inputs.nth(i)
        has_value = bool((el.input_value() or "").strip())
        name_or_id = el.get_attribute("name") or el.get_attribute("id")
        is_flagged = any(name_or_id == f.field for f in flagged) or el.get_attribute("type") == "file"
        assert has_value or is_flagged, f"required field {name_or_id} neither filled nor flagged"


def test_fill_greenhouse_combined_full_name_field(page) -> None:
    page.goto(_fixture_url("greenhouse_combined_name.html"))
    fields = _fields(name="Jordan Quill")
    filled, _flagged = _fill_greenhouse(page, fields)
    assert "full_name" in filled
    assert "first_name" not in filled  # combined field used, not both
    assert page.locator("#full_name").input_value() == "Jordan Quill"


def test_fill_greenhouse_label_fallback_when_selectors_miss(page) -> None:
    page.goto(_fixture_url("greenhouse_label_only.html"))
    fields = _fields(name="Jordan Quill")
    filled, flagged = _fill_greenhouse(page, fields)
    assert page.locator("#q1").input_value() == "Jordan"
    assert page.locator("#q2").input_value() == "Quill"
    assert page.locator("#q3").input_value() == "jordan@example.com"


def test_fill_greenhouse_missing_candidate_email_is_flagged_not_left_blank(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(email=None)
    _, flagged = _fill_greenhouse(page, fields)
    email_flags = [f for f in flagged if f.field == "email"]
    assert len(email_flags) == 1
    assert "no email on file" in email_flags[0].reason.lower()


def test_fill_lever_standard_fills_mappable_fields(page) -> None:
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields(
        name="Jordan Quill",
        experience=[{"company": "Acme", "end_date": ""}],
        evidence_links=["https://portfolio.example.com"],
    )

    filled, flagged = _fill_lever(page, fields)

    assert "full_name" in filled
    assert "email" in filled
    assert "phone" in filled
    assert "current_company" in filled
    assert "portfolio_url" in filled
    assert "cover_letter" in filled
    assert page.locator("input[name='name']").input_value() == "Jordan Quill"
    assert page.locator("input[name='org']").input_value() == "Acme"
    assert page.locator("input[name='urls[Portfolio]']").input_value() == "https://portfolio.example.com"
    # Regression: the fixture's #name field is `required`. This agent
    # fills it under the semantic label "full_name", whose raw HTML `name`
    # attribute is "name" — the two labels must not cause it to also show
    # up in `flagged` as if it were never filled.
    assert not any(f.field == "name" for f in flagged)


def test_fill_lever_does_not_reflag_a_required_field_it_already_filled(page) -> None:
    """Regression test for a real bug caught testing against a live Lever
    posting: `.fill()` updates a field's live value, not necessarily its
    static HTML `value` attribute, so checking the attribute instead of
    the live value made this agent re-flag fields it had just filled
    itself (whenever the semantic label it filled under — e.g. "full_name"
    — differs from the field's raw HTML name/id — e.g. "name")."""
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields(name="Jordan Quill")

    filled, flagged = _fill_lever(page, fields)

    assert "full_name" in filled
    flagged_names = {f.field for f in flagged}
    assert "name" not in flagged_names
    assert "email" not in flagged_names
    assert "phone" not in flagged_names


def test_fill_lever_flags_resume_upload(page) -> None:
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields()
    _, flagged = _fill_lever(page, fields)
    assert any(f.field == "resume" for f in flagged)


def test_fill_lever_flags_custom_required_question(page) -> None:
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields()
    _, flagged = _fill_lever(page, fields)
    assert any(f.field == "cards[why]" for f in flagged)


# ---------------------------------------------------------------------------
# Full orchestration against a real (local, fixture-backed) browser session
# ---------------------------------------------------------------------------


def test_run_assisted_apply_full_success_path(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(form_fill_service, "detect_ats_platform", lambda _url: "greenhouse")
    job = _job(isolated_session, url=_fixture_url("greenhouse_standard.html"))
    candidate = _seed_candidate(isolated_session)
    isolated_session.query(Candidate).filter(Candidate.id == candidate.id).update({"name": "Jordan Quill"})
    isolated_session.commit()
    _approved_package(isolated_session, job, candidate)

    result = run_assisted_apply(isolated_session, "manual-abc123")

    assert result.status == "needs_review"  # resume + custom question always flagged
    assert "email" in result.filled_fields
    assert any(f.field == "resume" for f in result.flagged_fields)
    assert result.error_message is None
    assert isolated_session.query(FormFillAttemptRecord).count() == 1


def test_run_assisted_apply_persists_filled_and_flagged_fields(isolated_session, monkeypatch) -> None:
    monkeypatch.setattr(form_fill_service, "detect_ats_platform", lambda _url: "lever")
    # The local fixture file is the form itself, not a Lever posting page —
    # bypass the real-world "/apply" URL rewrite (test_navigation_url_*
    # covers that in isolation) so this test loads the fixture directly.
    monkeypatch.setattr(form_fill_service, "_navigation_url", lambda url, _platform: url)
    job = _job(isolated_session, url=_fixture_url("lever_standard.html"))
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    run_assisted_apply(isolated_session, "manual-abc123")

    record = isolated_session.query(FormFillAttemptRecord).first()
    assert record.ats_platform == "lever"
    assert "email" in record.filled_fields
    assert any(f["field"] == "resume" for f in record.flagged_fields)


# ---------------------------------------------------------------------------
# Route-level test
# ---------------------------------------------------------------------------


def test_fill_application_route_requires_approval(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db)
    response = client.post("/api/jobs/manual-abc123/fill-application")
    assert response.status_code == 409


def test_fill_application_route_missing_job_404s(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.post("/api/jobs/does-not-exist/fill-application")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Safety: never submit
# ---------------------------------------------------------------------------


def test_service_source_never_invokes_a_click_or_submit_action() -> None:
    """Belt-and-suspenders guard on the single most important invariant of
    this module. This isn't a substitute for reading the code — it's a
    tripwire so an accidental submit call doesn't slip through unnoticed."""
    source = Path(form_fill_service.__file__).read_text()
    assert ".click(" not in source
    assert ".submit(" not in source
    assert "press(\"Enter\")" not in source and "press('Enter')" not in source

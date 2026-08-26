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

from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    FormFillAttemptRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.services import form_fill_service
from backend.services.form_fill_service import (
    _build_candidate_fields,
    _categorize_urls,
    _current_company,
    _fill_greenhouse,
    _fill_lever,
    _load_target_preference,
    _navigation_url,
    _split_name,
    _strip_lever_apply_suffix,
    _try_select_by_label,
    detect_ats_platform,
    find_job_by_url,
    get_autofill_data,
    get_extension_panel_data,
    run_assisted_apply,
)
from tests.mvp_helpers import ensure_user

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ats_forms"


def _fixture_url(name: str) -> str:
    return f"file://{(FIXTURES_DIR / name).resolve()}"


def _names(filled_or_flagged) -> set[str]:
    return {f.field for f in filled_or_flagged}


def _value_of(filled, field_name: str) -> str | None:
    return next((f.value for f in filled if f.field == field_name), None)


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


TEST_USER_ID = 1


def _candidate(**overrides) -> Candidate:
    defaults = dict(
        user_id=TEST_USER_ID,
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


def test_categorize_urls_splits_linkedin_github_portfolio() -> None:
    linkedin, github, portfolio = _categorize_urls(
        [
            "not a url",
            "https://www.linkedin.com/in/jordanquill",
            "https://github.com/jordanquill",
            "https://portfolio.example.com",
        ]
    )
    assert linkedin == "https://www.linkedin.com/in/jordanquill"
    assert github == "https://github.com/jordanquill"
    assert portfolio == "https://portfolio.example.com"


def test_categorize_urls_keeps_first_match_per_category() -> None:
    linkedin, github, portfolio = _categorize_urls(
        [
            "https://linkedin.com/in/first",
            "https://linkedin.com/in/second",
            "https://portfolio-one.example.com",
            "https://portfolio-two.example.com",
        ]
    )
    assert linkedin == "https://linkedin.com/in/first"
    assert github is None
    # Only the first non-linkedin/github link becomes "portfolio" — later
    # ones are dropped rather than silently overwriting it.
    assert portfolio == "https://portfolio-one.example.com"


def test_categorize_urls_ignores_non_http_entries() -> None:
    assert _categorize_urls(["just some text", "github.com/no-scheme"]) == (None, None, None)


def test_categorize_urls_empty_list() -> None:
    assert _categorize_urls([]) == (None, None, None)


def test_load_target_preference_returns_most_recent_record(isolated_session) -> None:
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(TargetPreference(candidate_id=candidate.id, preferred_locations=["Austin, TX"]))
    isolated_session.commit()
    isolated_session.add(TargetPreference(candidate_id=candidate.id, preferred_locations=["Remote"]))
    isolated_session.commit()
    pref = _load_target_preference(isolated_session, candidate)
    assert pref is not None
    assert pref.preferred_locations == ["Remote"]


def test_load_target_preference_none_without_a_preference_record(isolated_session) -> None:
    candidate = _seed_candidate(isolated_session)
    assert _load_target_preference(isolated_session, candidate) is None


def test_build_candidate_fields_maps_all_sources() -> None:
    candidate = _candidate(
        name="Jordan Quill",
        experience=[{"company": "Acme", "end_date": "Present"}],
        evidence_links=[
            "https://www.linkedin.com/in/jordanquill",
            "https://github.com/jordanquill",
            "https://portfolio.example.com",
        ],
    )
    package = ApplicationPackageRecord(job_id=1, cover_letter_draft="Dear team,", tailored_bullets=[], source_traceability_notes=[])
    preference = TargetPreference(
        preferred_locations=["Austin, TX"],
        legal_name="Jordan A. Quill",
        earliest_start_date="Immediately",
        currently_enrolled_in_program="Yes",
        expected_graduation="May 2027",
        degree_pursuing="Bachelor's in Computer Science",
        work_authorization="US Citizen",
        sponsorship_required=False,
        gender="Non-binary",
        race_ethnicity="No",
        veteran_status="I am not a protected veteran",
        disability_status="No, I do not have a disability and have not had one in the past",
    )
    fields = _build_candidate_fields(candidate, package, preference)
    assert fields.full_name == "Jordan Quill"
    assert fields.first_name == "Jordan"
    assert fields.last_name == "Quill"
    assert fields.current_company == "Acme"
    assert fields.location == "Austin, TX"
    assert fields.legal_name == "Jordan A. Quill"
    assert fields.linkedin_url == "https://www.linkedin.com/in/jordanquill"
    assert fields.github_url == "https://github.com/jordanquill"
    assert fields.portfolio_url == "https://portfolio.example.com"
    assert fields.cover_letter == "Dear team,"
    assert fields.work_authorization == "US Citizen"
    assert fields.sponsorship_required is False
    assert fields.earliest_start_date == "Immediately"
    assert fields.currently_enrolled_in_program == "Yes"
    assert fields.expected_graduation == "May 2027"
    assert fields.degree_pursuing == "Bachelor's in Computer Science"
    assert fields.gender == "Non-binary"
    assert fields.race_ethnicity == "No"
    assert fields.veteran_status == "I am not a protected veteran"
    assert fields.disability_status == "No, I do not have a disability and have not had one in the past"


def test_build_candidate_fields_manual_linkedin_overrides_resume_grounded_link() -> None:
    """A manually-saved linkedin_url is more deliberate than whatever
    resume-grounding happened to find (and is the only way to get a
    correct value at all when the resume's link is a PDF hyperlink rather
    than printed text, which grounding can never see) — it must win."""
    candidate = _candidate(
        name="Jordan Quill", evidence_links=["https://www.linkedin.com/in/from-resume"]
    )
    package = ApplicationPackageRecord(job_id=1, tailored_bullets=[], source_traceability_notes=[])
    preference = TargetPreference(linkedin_url="https://www.linkedin.com/in/manually-saved")
    fields = _build_candidate_fields(candidate, package, preference)
    assert fields.linkedin_url == "https://www.linkedin.com/in/manually-saved"


def test_build_candidate_fields_defaults_to_none_without_a_preference() -> None:
    candidate = _candidate(name="Jordan Quill")
    package = ApplicationPackageRecord(job_id=1, tailored_bullets=[], source_traceability_notes=[])
    fields = _build_candidate_fields(candidate, package)
    assert fields.location is None
    assert fields.legal_name is None
    assert fields.work_authorization is None
    assert fields.sponsorship_required is None
    assert fields.earliest_start_date is None
    assert fields.currently_enrolled_in_program is None
    assert fields.expected_graduation is None
    assert fields.degree_pursuing is None
    assert fields.gender is None
    assert fields.race_ethnicity is None
    assert fields.veteran_status is None
    assert fields.disability_status is None


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
    from backend.db.models import User

    if session.get(User, TEST_USER_ID) is None:
        session.add(User(id=TEST_USER_ID, email="user1@example.com", hashed_password="x"))
        session.commit()
    previous = session.query(Candidate).filter(Candidate.user_id == TEST_USER_ID).first()
    if previous is not None:
        previous.user_id = None
        session.commit()
    candidate = _candidate()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _extension_auth_headers(client) -> dict[str, str]:
    from backend.core.config import settings

    token = client.cookies.get(settings.session_cookie_name)
    assert token, "expected an authenticated test client session cookie"
    return {settings.session_header_name: token}


def _approved_package(
    session, job: JobRecord, candidate: Candidate | None, *, grounded: bool = True
) -> ApplicationPackageRecord:
    """`grounded=True` by default: a realistically-approved package went
    through the real grounded-generation pipeline, which is_grounded_package_record
    now also requires to have real (non-blank) bullets, cover letter,
    recruiter message, and traceability notes — so all four are populated
    here, not left empty. Tests that specifically exercise the
    grounded-package gate (is_package_ready_for_apply) pass grounded=False
    to build the exact "ungrounded but somehow approved" legacy row the
    gate exists to reject."""
    record = ApplicationPackageRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        candidate_id=candidate.id if candidate else None,
        tailored_bullets=["Built Python APIs relevant to this role."],
        cover_letter_draft="Dear hiring team,",
        recruiter_message="Happy to discuss my background.",
        source_traceability_notes=["Python <- candidate skills"],
        approval_status="approved",
        eligibility_confirmed=True,
        grounded=grounded,
    )
    session.add(record)
    session.commit()
    return record


def test_run_assisted_apply_missing_job_404s(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "does-not-exist", TEST_USER_ID)
    assert exc_info.value.status_code == 404


def test_run_assisted_apply_without_package_409s(isolated_session) -> None:
    _job(isolated_session)
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    assert exc_info.value.status_code == 409


def test_run_assisted_apply_unapproved_package_409s(isolated_session) -> None:
    job = _job(isolated_session)
    candidate = _seed_candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        candidate_id=candidate.id,
        tailored_bullets=[],
        source_traceability_notes=[],
        approval_status="pending_review",
    )
    isolated_session.add(record)
    isolated_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    assert exc_info.value.status_code == 409
    assert "approved" in exc_info.value.detail.lower()


def test_run_assisted_apply_without_candidate_409s(isolated_session) -> None:
    job = _job(isolated_session)
    _approved_package(isolated_session, job, candidate=None)
    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    assert exc_info.value.status_code == 409
    assert "candidate" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Regression coverage: the shared grounded-package gate
# (is_package_ready_for_apply) rejects a legacy row that's marked approved
# but was never actually grounded — both Assisted Apply paths (server-side
# Playwright preview via run_assisted_apply, and the browser extension via
# get_autofill_data) reuse the same gate.
# ---------------------------------------------------------------------------


def test_run_assisted_apply_rejects_an_ungrounded_approved_legacy_package(isolated_session) -> None:
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate, grounded=False)

    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    assert exc_info.value.status_code == 409
    assert "grounded" in exc_info.value.detail.lower()
    assert isolated_session.query(FormFillAttemptRecord).count() == 0


def test_get_autofill_data_rejects_an_ungrounded_approved_legacy_package(isolated_session) -> None:
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate, grounded=False)

    with pytest.raises(HTTPException) as exc_info:
        get_autofill_data(isolated_session, "https://job-boards.greenhouse.io/acme/jobs/1", TEST_USER_ID)
    assert exc_info.value.status_code == 409
    assert "grounded" in exc_info.value.detail.lower()


def test_extension_autofill_route_rejects_an_ungrounded_approved_legacy_package(isolated_client) -> None:
    """Same check via the real HTTP route the extension calls, not just the
    service function directly."""
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db, url="https://job-boards.greenhouse.io/acme/jobs/1")
        candidate = _seed_candidate(db)
        _approved_package(db, job, candidate, grounded=False)

    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        "/api/extension/autofill",
        params={"url": "https://job-boards.greenhouse.io/acme/jobs/1"},
        headers=headers,
    )
    assert response.status_code == 409


def test_run_assisted_apply_rejects_a_wrong_candidate_package(isolated_session) -> None:
    """A package approved against a candidate profile that's since been
    superseded by a fresh resume upload must not reach Form Fill against
    the new, current candidate's data."""
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    stale_candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, stale_candidate, grounded=True)
    _seed_candidate(isolated_session)  # a fresh resume upload supersedes stale_candidate as "current"

    with pytest.raises(HTTPException) as exc_info:
        run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    assert exc_info.value.status_code == 409


def test_run_assisted_apply_unsupported_platform_persists_failed_result(isolated_session) -> None:
    job = _job(isolated_session, url="https://example.com/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    result = run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)

    assert result.status == "failed"
    assert result.ats_platform == "unsupported"
    assert "greenhouse" in (result.error_message or "").lower()
    assert isolated_session.query(FormFillAttemptRecord).count() == 1


def test_run_assisted_apply_multiple_attempts_are_not_upserted(isolated_session) -> None:
    job = _job(isolated_session, url="https://example.com/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)
    run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)

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


_PREFERENCE_OVERRIDE_KEYS = (
    "location",
    "legal_name",
    "linkedin_url",
    "github_url",
    "portfolio_url",
    "earliest_start_date",
    "currently_enrolled_in_program",
    "expected_graduation",
    "degree_pursuing",
    "work_authorization",
    "sponsorship_required",
    "gender",
    "race_ethnicity",
    "veteran_status",
    "disability_status",
)


def _fields(**overrides):
    candidate = _candidate(**{k: v for k, v in overrides.items() if k in ("name", "email", "phone", "experience", "evidence_links")})
    package = ApplicationPackageRecord(
        job_id=1,
        cover_letter_draft=overrides.get("cover_letter", "Dear hiring team, I would love to join."),
        tailored_bullets=[],
        source_traceability_notes=[],
    )
    preference = TargetPreference(
        preferred_locations=[overrides["location"]] if overrides.get("location") else [],
        **{k: v for k, v in overrides.items() if k in _PREFERENCE_OVERRIDE_KEYS and k != "location"},
    )
    return _build_candidate_fields(candidate, package, preference)


def test_fill_greenhouse_standard_fills_mappable_fields(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(name="Jordan Quill", experience=[{"company": "Acme", "end_date": "Present"}])

    filled, flagged = _fill_greenhouse(page, fields)

    names = _names(filled)
    assert {"first_name", "last_name", "email", "phone", "current_company", "cover_letter"} <= names
    # The whole point of returning filled fields at all: the actual value,
    # not just that some field named "email" exists — a human needs the
    # real value to copy into the form themselves.
    assert _value_of(filled, "first_name") == "Jordan"
    assert _value_of(filled, "last_name") == "Quill"
    assert _value_of(filled, "email") == "jordan@example.com"
    assert _value_of(filled, "current_company") == "Acme"
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
    names = _names(filled)
    assert "full_name" in names
    assert "first_name" not in names  # combined field used, not both
    assert _value_of(filled, "full_name") == "Jordan Quill"
    assert page.locator("#full_name").input_value() == "Jordan Quill"


def test_fill_greenhouse_label_fallback_when_selectors_miss(page) -> None:
    page.goto(_fixture_url("greenhouse_label_only.html"))
    fields = _fields(name="Jordan Quill")
    filled, flagged = _fill_greenhouse(page, fields)
    assert page.locator("#q1").input_value() == "Jordan"
    assert page.locator("#q2").input_value() == "Quill"
    assert page.locator("#q3").input_value() == "jordan@example.com"
    # Regression: the label-fallback path filled these successfully but
    # previously never recorded them in `filled` at all — they'd silently
    # vanish from both filled and flagged, undercounting what the human
    # actually needs to review.
    names = _names(filled)
    assert {"first_name", "last_name", "email"} <= names
    assert _value_of(filled, "first_name") == "Jordan"
    assert _value_of(filled, "email") == "jordan@example.com"


def test_fill_greenhouse_missing_candidate_email_is_flagged_not_left_blank(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(email=None)
    _, flagged = _fill_greenhouse(page, fields)
    email_flags = [f for f in flagged if f.field == "email"]
    assert len(email_flags) == 1
    assert "no email on file" in email_flags[0].reason.lower()


def test_fill_greenhouse_fills_location_linkedin_github_via_label_match(page) -> None:
    """Location, LinkedIn, and GitHub are modeled as per-posting custom
    questions on Greenhouse (confirmed live against a real Cloudflare
    posting) — no stable id/name, so this only works via label-text
    matching, unlike the fixed-selector fields above."""
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(
        name="Jordan Quill",
        location="Austin, TX",
        evidence_links=["https://www.linkedin.com/in/jordanquill", "https://github.com/jordanquill"],
    )
    filled, _flagged = _fill_greenhouse(page, fields)

    assert _value_of(filled, "location") == "Austin, TX"
    assert _value_of(filled, "linkedin_url") == "https://www.linkedin.com/in/jordanquill"
    assert _value_of(filled, "github_url") == "https://github.com/jordanquill"
    assert page.locator("#question_1").input_value() == "Austin, TX"
    assert page.locator("#question_2").input_value() == "https://www.linkedin.com/in/jordanquill"
    assert page.locator("#question_3").input_value() == "https://github.com/jordanquill"


def test_try_select_by_label_exact_match(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    assert _try_select_by_label(page, [r"sponsorship"], "Yes") is True
    assert page.locator("#question_5").input_value() == "Yes"


def test_try_select_by_label_fuzzy_fallback_when_wording_differs(page) -> None:
    """A saved answer won't always match a posting's exact option text —
    e.g. "Yes" should still match an option literally worded "Yes, I will
    need sponsorship" via substring matching."""
    page.goto(_fixture_url("greenhouse_label_only.html"))
    page.evaluate(
        """() => {
            const select = document.createElement('select');
            select.id = 'sponsorship_select';
            select.innerHTML = '<option value="">Select...</option>'
                + '<option value="need_sponsorship">Yes, I will need sponsorship</option>'
                + '<option value="no_sponsorship">No, I will not need sponsorship</option>';
            const label = document.createElement('label');
            label.htmlFor = 'sponsorship_select';
            label.textContent = 'Sponsorship required';
            document.querySelector('form').append(label, select);
        }"""
    )
    assert _try_select_by_label(page, [r"sponsorship"], "Yes") is True
    assert page.locator("#sponsorship_select").input_value() == "need_sponsorship"


def test_try_select_by_label_returns_false_when_nothing_matches(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    assert _try_select_by_label(page, [r"sponsorship"], "Maybe eventually") is False
    assert page.locator("#question_5").input_value() == ""


def test_try_select_by_label_matches_when_saved_value_is_more_specific_than_the_option(page) -> None:
    """Regression test: the fuzzy fallback originally only checked whether
    the OPTION text contained the saved value, missing the equally common
    reverse case — a saved answer more specific than the posting's option
    (e.g. "Bachelor's in Computer Science" saved, but the posting only
    offers a plain "Bachelor's" option)."""
    page.goto(_fixture_url("greenhouse_label_only.html"))
    page.evaluate(
        """() => {
            const select = document.createElement('select');
            select.id = 'degree_select';
            select.innerHTML = '<option value="">Select...</option>'
                + '<option value="bachelors">Bachelor\\'s</option>'
                + '<option value="masters">Master\\'s</option>';
            const label = document.createElement('label');
            label.htmlFor = 'degree_select';
            label.textContent = 'Degree currently pursuing';
            document.querySelector('form').append(label, select);
        }"""
    )
    assert _try_select_by_label(page, [r"degree"], "Bachelor's in Computer Science") is True
    assert page.locator("#degree_select").input_value() == "bachelors"


def test_fill_greenhouse_fills_new_reusable_select_and_text_fields(page) -> None:
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(
        name="Jordan Quill",
        legal_name="Jordan A. Quill",
        work_authorization="US Citizen",
        sponsorship_required=False,
        currently_enrolled_in_program="Yes",
    )
    filled, _flagged = _fill_greenhouse(page, fields)

    assert _value_of(filled, "legal_name") == "Jordan A. Quill"
    assert page.locator("#question_4").input_value() == "Jordan A. Quill"
    assert _value_of(filled, "sponsorship_required") == "No"
    assert page.locator("#question_5").input_value() == "No"
    assert _value_of(filled, "currently_enrolled_in_program") == "Yes"
    assert page.locator("#question_6").input_value() == "Yes"


def test_fill_greenhouse_never_touches_the_privacy_policy_checkbox(page) -> None:
    """Accepting a company's privacy policy/terms is a consent action that
    must always stay a deliberate human click, never something this agent
    answers on the candidate's behalf — regardless of how much of the rest
    of the profile is filled in."""
    page.goto(_fixture_url("greenhouse_standard.html"))
    fields = _fields(
        name="Jordan Quill",
        legal_name="Jordan A. Quill",
        sponsorship_required=True,
        currently_enrolled_in_program="Yes",
        gender="Non-binary",
        veteran_status="I am not a protected veteran",
        disability_status="No, I do not have a disability and have not had one in the past",
    )
    filled, flagged = _fill_greenhouse(page, fields)

    assert page.locator("#privacy_ack").is_checked() is False
    assert not any("privacy" in f.field.lower() or "acknowledge" in f.field.lower() for f in filled)
    assert any(f.field == "job_application[answers][7][boolean_value]" for f in flagged)


def test_fill_lever_standard_fills_mappable_fields(page) -> None:
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields(
        name="Jordan Quill",
        experience=[{"company": "Acme", "end_date": ""}],
        location="Austin, TX",
        evidence_links=[
            "https://www.linkedin.com/in/jordanquill",
            "https://github.com/jordanquill",
            "https://portfolio.example.com",
        ],
    )

    filled, flagged = _fill_lever(page, fields)

    names = _names(filled)
    assert {
        "full_name",
        "email",
        "phone",
        "current_company",
        "location",
        "linkedin_url",
        "github_url",
        "portfolio_url",
        "cover_letter",
    } <= names
    assert _value_of(filled, "full_name") == "Jordan Quill"
    assert _value_of(filled, "current_company") == "Acme"
    assert _value_of(filled, "location") == "Austin, TX"
    assert _value_of(filled, "linkedin_url") == "https://www.linkedin.com/in/jordanquill"
    assert _value_of(filled, "github_url") == "https://github.com/jordanquill"
    assert _value_of(filled, "portfolio_url") == "https://portfolio.example.com"
    assert page.locator("input[name='name']").input_value() == "Jordan Quill"
    assert page.locator("input[name='org']").input_value() == "Acme"
    assert page.locator("input[name='location']").input_value() == "Austin, TX"
    assert page.locator("input[name='urls[LinkedIn]']").input_value() == "https://www.linkedin.com/in/jordanquill"
    assert page.locator("input[name='urls[GitHub]']").input_value() == "https://github.com/jordanquill"
    assert page.locator("input[name='urls[Portfolio]']").input_value() == "https://portfolio.example.com"
    # Regression: the fixture's #name field is `required`. This agent
    # fills it under the semantic label "full_name", whose raw HTML `name`
    # attribute is "name" — the two labels must not cause it to also show
    # up in `flagged` as if it were never filled.
    assert not any(f.field == "name" for f in flagged)


def test_fill_lever_does_not_cross_fill_linkedin_github_and_portfolio(page) -> None:
    """Regression test for a real bug: the old code tried the single
    portfolio_url value against Portfolio, then LinkedIn, then GitHub
    selectors in a loop, so a candidate with only a portfolio link (no
    LinkedIn/GitHub) would get it stuffed into whichever field selector
    happened to still be empty — e.g. into the LinkedIn field. Each URL
    category must only ever land in its own field."""
    page.goto(_fixture_url("lever_standard.html"))
    fields = _fields(name="Jordan Quill", evidence_links=["https://portfolio.example.com"])

    filled, _flagged = _fill_lever(page, fields)

    assert _value_of(filled, "portfolio_url") == "https://portfolio.example.com"
    assert not any(f.field in ("linkedin_url", "github_url") for f in filled)
    assert page.locator("input[name='urls[Portfolio]']").input_value() == "https://portfolio.example.com"
    assert page.locator("input[name='urls[LinkedIn]']").input_value() == ""
    assert page.locator("input[name='urls[GitHub]']").input_value() == ""


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

    assert "full_name" in _names(filled)
    flagged_names = _names(flagged)
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

    result = run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)

    assert result.status == "needs_review"  # resume + custom question always flagged
    assert "email" in _names(result.filled_fields)
    assert _value_of(result.filled_fields, "email") == "jordan@example.com"
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

    run_assisted_apply(isolated_session, "manual-abc123", TEST_USER_ID)

    record = isolated_session.query(FormFillAttemptRecord).first()
    assert record.ats_platform == "lever"
    assert any(f["field"] == "email" and f["value"] == "jordan@example.com" for f in record.filled_fields)
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
# Extension autofill: URL matching and the field-data endpoint
# ---------------------------------------------------------------------------


def test_strip_lever_apply_suffix_removes_apply() -> None:
    assert _strip_lever_apply_suffix("https://jobs.lever.co/acme/abc-123/apply") == "https://jobs.lever.co/acme/abc-123"


def test_strip_lever_apply_suffix_handles_trailing_slash() -> None:
    assert _strip_lever_apply_suffix("https://jobs.lever.co/acme/abc-123/apply/") == "https://jobs.lever.co/acme/abc-123"


def test_strip_lever_apply_suffix_no_op_without_apply() -> None:
    assert _strip_lever_apply_suffix("https://job-boards.greenhouse.io/acme/jobs/1") == "https://job-boards.greenhouse.io/acme/jobs/1"


def test_find_job_by_url_exact_match(isolated_session) -> None:
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    found = find_job_by_url(isolated_session, "https://job-boards.greenhouse.io/acme/jobs/1")
    assert found is not None
    assert found.id == job.id


def test_find_job_by_url_matches_lever_apply_page(isolated_session) -> None:
    """The extension passes the tab's actual URL, which for Lever is the
    /apply form page — the stored job.url is always the plain posting
    page, so matching must strip that suffix to find it."""
    job = _job(isolated_session, url="https://jobs.lever.co/acme/abc-123")
    found = find_job_by_url(isolated_session, "https://jobs.lever.co/acme/abc-123/apply")
    assert found is not None
    assert found.id == job.id


def test_find_job_by_url_no_match_returns_none(isolated_session) -> None:
    _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    assert find_job_by_url(isolated_session, "https://job-boards.greenhouse.io/other/jobs/2") is None


def test_get_autofill_data_returns_field_values(isolated_session) -> None:
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    candidate = _seed_candidate(isolated_session)
    _approved_package(isolated_session, job, candidate)

    result = get_autofill_data(isolated_session, "https://job-boards.greenhouse.io/acme/jobs/1", TEST_USER_ID)

    assert result.job_id == "manual-abc123"
    assert result.platform == "greenhouse"
    assert result.fields.full_name == "Jordan Quill"
    assert result.fields.email == "jordan@example.com"


def test_get_autofill_data_unknown_url_404s(isolated_session) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_autofill_data(isolated_session, "https://job-boards.greenhouse.io/nope/jobs/1", TEST_USER_ID)
    assert exc_info.value.status_code == 404


def test_get_autofill_data_requires_approval(isolated_session) -> None:
    job = _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/1")
    candidate = _seed_candidate(isolated_session)
    record = ApplicationPackageRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        candidate_id=candidate.id,
        tailored_bullets=[],
        source_traceability_notes=[],
        approval_status="pending_review",
    )
    isolated_session.add(record)
    isolated_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_autofill_data(isolated_session, "https://job-boards.greenhouse.io/acme/jobs/1", TEST_USER_ID)
    assert exc_info.value.status_code == 409


def test_extension_autofill_route_returns_data(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db, url="https://job-boards.greenhouse.io/acme/jobs/1")
        candidate = _seed_candidate(db)
        _approved_package(db, job, candidate)

    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        "/api/extension/autofill",
        params={"url": "https://job-boards.greenhouse.io/acme/jobs/1"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "greenhouse"
    assert body["fields"]["email"] == "jordan@example.com"


def test_extension_autofill_route_unknown_url_404s(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        "/api/extension/autofill",
        params={"url": "https://example.com/nope"},
        headers=headers,
    )
    assert response.status_code == 404


def test_extension_autofill_rejects_cookie_only_auth(isolated_client) -> None:
    """Ordinary session cookies must not authenticate the extension route —
    only the narrowly scoped extension header is accepted there."""
    client, _SessionLocal = isolated_client
    response = client.get(
        "/api/extension/autofill",
        params={"url": "https://example.com/nope"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/extension/panel-data — read-only side-panel status
# ---------------------------------------------------------------------------


def _score(session, job: JobRecord, candidate: Candidate, **overrides) -> MatchScoreRecord:
    defaults = dict(
        job_id=job.id,
        candidate_id=candidate.id,
        overall_score=82.0,
        matched_skills=["Python"],
        partial_matches=[],
        missing_skills=["Docker"],
        recommendation="apply",
        rationale="Strong skills overlap.",
    )
    defaults.update(overrides)
    record = MatchScoreRecord(**defaults)
    session.add(record)
    session.commit()
    return record


def test_panel_data_returns_tracked_false_for_unknown_url(isolated_session) -> None:
    """A URL with no matching job is the panel's normal empty state, not an
    error — 200 + tracked=false, unlike autofill's 404 for the same case."""
    result = get_extension_panel_data(isolated_session, "https://example.com/nope", TEST_USER_ID)
    assert result.tracked is False
    assert result.job is None
    assert result.score is None
    assert result.materials_status is None


def test_panel_data_lever_apply_suffix_matches(isolated_session) -> None:
    job = _job(isolated_session, url="https://jobs.lever.co/acme/abc-123")
    result = get_extension_panel_data(
        isolated_session, "https://jobs.lever.co/acme/abc-123/apply", TEST_USER_ID
    )
    assert result.tracked is True
    assert result.job.id == job.public_id


def test_panel_data_does_not_require_approval(isolated_session) -> None:
    """Regression for the actual gap this closes: a pending-review (never
    approved) package must still surface real data, not the 409
    autofill would raise for the same package."""
    job = _job(isolated_session)
    candidate = _seed_candidate(isolated_session)
    package = ApplicationPackageRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        candidate_id=candidate.id,
        tailored_bullets=["Built Python APIs."],
        cover_letter_draft="Dear team,",
        recruiter_message="Hello,",
        source_traceability_notes=["Python <- skills"],
        approval_status="pending_review",
        grounded=True,
    )
    isolated_session.add(package)
    isolated_session.commit()
    _score(isolated_session, job, candidate)

    result = get_extension_panel_data(isolated_session, job.url, TEST_USER_ID)
    assert result.tracked is True
    assert result.materials_status == "current"
    assert result.score is not None
    assert result.score.overall_score == 82.0


def test_panel_data_missing_materials_reports_missing_not_an_error(isolated_session) -> None:
    job = _job(isolated_session)
    _seed_candidate(isolated_session)
    result = get_extension_panel_data(isolated_session, job.url, TEST_USER_ID)
    assert result.tracked is True
    assert result.materials_status == "missing"
    assert result.score is None


@pytest.mark.parametrize(
    ("reviewed", "expected"),
    [(False, "stale_pending"), (True, "stale_reviewed")],
)
def test_panel_data_stale_materials_status(isolated_session, reviewed: bool, expected: str) -> None:
    """Stale materials (belonging to a since-replaced candidate profile)
    still return 200 with a status the panel can render, not a 409."""
    job = _job(isolated_session)
    old_candidate = _seed_candidate(isolated_session)
    approval_status = "approved" if reviewed else "pending_review"
    package = ApplicationPackageRecord(
        job_id=job.id,
        user_id=TEST_USER_ID,
        candidate_id=old_candidate.id,
        tailored_bullets=["Built Python APIs."],
        cover_letter_draft="Dear team,",
        recruiter_message="Hello,",
        source_traceability_notes=["Python <- skills"],
        approval_status=approval_status,
        grounded=True,
    )
    isolated_session.add(package)
    isolated_session.commit()
    # Replace the candidate profile — the stored package now belongs to a
    # previous, no-longer-current profile revision.
    isolated_session.query(Candidate).filter(Candidate.id == old_candidate.id).update({"user_id": None})
    isolated_session.add(_candidate())
    isolated_session.commit()

    result = get_extension_panel_data(isolated_session, job.url, TEST_USER_ID)
    assert result.tracked is True
    assert result.materials_status == expected


def test_panel_data_missing_candidate_profile_is_graceful(isolated_session) -> None:
    """No candidate at all degrades to null score/materials, not an error —
    matches list_stored_match_scores's existing no-candidate behavior."""
    job = _job(isolated_session)
    result = get_extension_panel_data(isolated_session, job.url, TEST_USER_ID)
    assert result.tracked is True
    assert result.score is None
    assert result.materials_status == "missing"


def test_panel_data_scopes_score_and_materials_to_requesting_user(isolated_session) -> None:
    """Jobs are global/shared (JobRecord has no user_id) — score and
    materials must still never leak across users hitting the same job."""
    job = _job(isolated_session)
    owner = _seed_candidate(isolated_session)
    _score(isolated_session, job, owner, overall_score=91.0)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=owner.id,
            tailored_bullets=["Owner's tailored bullet."],
            cover_letter_draft="Owner's cover letter.",
            recruiter_message="Owner's message.",
            source_traceability_notes=["note"],
            approval_status="approved",
            grounded=True,
        )
    )
    isolated_session.commit()

    other_user = ensure_user(isolated_session, user_id=TEST_USER_ID + 1, email="other@example.com")
    result = get_extension_panel_data(isolated_session, job.url, other_user.id)
    assert result.tracked is True
    assert result.score is None
    assert result.materials_status == "missing"


def test_panel_data_route_rejects_cookie_only_auth(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    response = client.get("/api/extension/panel-data", params={"url": "https://example.com/nope"})
    assert response.status_code == 401


def test_panel_data_route_returns_tracked_status(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db, url="https://job-boards.greenhouse.io/acme/jobs/1")
        candidate = _seed_candidate(db)
        _score(db, job, candidate)

    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        "/api/extension/panel-data",
        params={"url": "https://job-boards.greenhouse.io/acme/jobs/1"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tracked"] is True
    assert body["score"]["overall_score"] == 82.0
    assert body["materials_status"] == "missing"
    assert body["platform"] == "greenhouse"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse"),
        ("https://boards.greenhouse.io/acme/jobs/1", "greenhouse"),
        ("https://jobs.lever.co/acme/abc-123", "lever"),
        ("https://remotive.com/remote-jobs/data/x-1", "unsupported"),
        ("https://example.com/careers/1", "unsupported"),
    ],
)
def test_panel_data_reports_the_platform_for_a_tracked_job(
    isolated_session, url: str, expected: str
) -> None:
    """The panel hides its fill button on postings assisted apply can never
    fill. It relies on this field rather than re-deriving the ATS host list
    in extension code, so the allowlist stays defined only here."""
    _job(isolated_session, url=url)
    result = get_extension_panel_data(isolated_session, url, TEST_USER_ID)
    assert result.tracked is True
    assert result.platform == expected


@pytest.mark.parametrize(
    "tab_url",
    [
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=7761472003",
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=7761472003&jr_id=6a8d&utm_source=jobright",
        "https://job-boards.greenhouse.io/acme/jobs/7761472003",
        "https://job-boards.greenhouse.io/acme/jobs/7761472003?utm_source=jobright",
        "https://boards.greenhouse.io/acme/jobs/7761472003",
        "https://boards.greenhouse.io/acme/jobs/7761472003/",
    ],
)
def test_panel_data_matches_every_greenhouse_url_shape(isolated_session, tab_url: str) -> None:
    """The extension sends the URL the user is genuinely looking at, which is
    often the embed form or carries an aggregator's tracking parameters. An
    exact-string match reported all of those as untracked even though the job
    was stored — the panel then offered no fit score and no assisted apply on
    a posting CareerPilot already knew about.
    """
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    result = get_extension_panel_data(isolated_session, tab_url, TEST_USER_ID)
    assert result.tracked is True, tab_url
    assert result.job.id == job.public_id
    assert result.platform == "greenhouse"


def test_panel_data_matches_a_job_stored_under_the_other_greenhouse_host(isolated_session) -> None:
    """Rows saved at different times carry either host (boards.greenhouse.io
    301s to job-boards.greenhouse.io); both must resolve to the same job."""
    _job(isolated_session, url="https://job-boards.greenhouse.io/acme/jobs/7761472003")
    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.tracked is True


def test_panel_data_does_not_match_a_different_posting(isolated_session) -> None:
    """The matching is looser than an exact string compare, so this pins down
    that it did not become loose enough to collide two different jobs."""
    _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    for other in (
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=9999999999",
        "https://job-boards.greenhouse.io/embed/job_app?for=otherco&token=7761472003",
        "https://boards.greenhouse.io/otherco/jobs/7761472003",
    ):
        assert get_extension_panel_data(isolated_session, other, TEST_USER_ID).tracked is False, other


def test_panel_data_apply_ready_is_false_without_an_approved_package(isolated_session) -> None:
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            tailored_bullets=["Built Python APIs."],
            cover_letter_draft="Dear team,",
            recruiter_message="Hello,",
            source_traceability_notes=["Python <- skills"],
            approval_status="pending_review",
            grounded=True,
        )
    )
    isolated_session.commit()

    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.apply_ready is False
    assert "approved" in (result.apply_blocked_reason or "")


def test_panel_data_apply_ready_is_true_for_an_approved_package(isolated_session) -> None:
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            tailored_bullets=["Built Python APIs."],
            cover_letter_draft="Dear team,",
            recruiter_message="Hello,",
            source_traceability_notes=["Python <- skills"],
            approval_status="approved",
            grounded=True,
        )
    )
    isolated_session.commit()

    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.apply_ready is True
    assert result.apply_blocked_reason is None


def test_panel_data_apply_readiness_agrees_with_the_autofill_route(isolated_session) -> None:
    """The panel shows the fill button exactly when autofill would succeed.
    If these two ever disagree the user gets a button that fails on click, or
    no button for a fill that would have worked — so assert them together."""
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    url = "https://boards.greenhouse.io/acme/jobs/7761472003"
    _seed_candidate(isolated_session)

    panel = get_extension_panel_data(isolated_session, url, TEST_USER_ID)
    autofill_succeeded = True
    try:
        get_autofill_data(isolated_session, url, TEST_USER_ID)
    except HTTPException:
        autofill_succeeded = False
    assert panel.apply_ready is autofill_succeeded
    assert job.public_id  # the job really was stored under this URL


def test_panel_data_reports_the_platform_even_when_untracked(isolated_session) -> None:
    """Platform comes from the URL, not the stored job, so it is still
    correct for a Greenhouse page CareerPilot has never seen."""
    result = get_extension_panel_data(
        isolated_session, "https://job-boards.greenhouse.io/acme/jobs/999", TEST_USER_ID
    )
    assert result.tracked is False
    assert result.platform == "greenhouse"


def test_panel_data_platform_matches_autofill_platform_detection(isolated_session) -> None:
    """Guards against the two paths drifting: whatever autofill would decide
    it is about to fill, the panel must have advertised the same."""
    for index, url in enumerate(
        (
            "https://job-boards.greenhouse.io/acme/jobs/1",
            "https://jobs.lever.co/acme/abc-123",
            "https://remotive.com/remote-jobs/data/x-1",
        )
    ):
        _job(isolated_session, public_id=f"manual-drift-{index}", url=url)
        result = get_extension_panel_data(isolated_session, url, TEST_USER_ID)
        assert result.platform == detect_ats_platform(url)


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


def test_panel_data_flags_an_overridden_package_as_unverified(isolated_session) -> None:
    """Assisted apply is allowed for an explicitly overridden package, but
    the panel must say so: this is the last screen before unverified claims
    are typed into a real employer's application form."""
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            tailored_bullets=["Led a global engineering team."],
            cover_letter_draft="Dear team,",
            recruiter_message="Hello,",
            source_traceability_notes=["unverified"],
            approval_status="approved",
            grounded=False,
            grounding_override=True,
            unsupported_claims=["invented_employer"],
        )
    )
    isolated_session.commit()

    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.apply_ready is True
    assert result.materials_unverified is True
    # Coherence: it must not simultaneously claim there are no materials.
    assert result.materials_status == "current"


def test_panel_data_leaves_unverified_false_for_evidence_backed_materials(isolated_session) -> None:
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            tailored_bullets=["Built Python APIs."],
            cover_letter_draft="Dear team,",
            recruiter_message="Hello,",
            source_traceability_notes=["Python <- skills"],
            approval_status="approved",
            grounded=True,
        )
    )
    isolated_session.commit()

    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.apply_ready is True
    assert result.materials_unverified is False


def test_an_ungrounded_package_without_the_override_stays_unfillable(isolated_session) -> None:
    """The override must be the only way an unverified package becomes
    fillable — not merely having grounded=False."""
    job = _job(isolated_session, url="https://boards.greenhouse.io/acme/jobs/7761472003")
    candidate = _seed_candidate(isolated_session)
    isolated_session.add(
        ApplicationPackageRecord(
            job_id=job.id,
            user_id=TEST_USER_ID,
            candidate_id=candidate.id,
            tailored_bullets=["Led a global engineering team."],
            cover_letter_draft="Dear team,",
            recruiter_message="Hello,",
            source_traceability_notes=["unverified"],
            approval_status="approved",
            grounded=False,
            grounding_override=False,
        )
    )
    isolated_session.commit()

    result = get_extension_panel_data(
        isolated_session, "https://boards.greenhouse.io/acme/jobs/7761472003", TEST_USER_ID
    )
    assert result.apply_ready is False

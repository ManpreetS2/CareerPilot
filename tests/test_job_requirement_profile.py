"""Full-posting requirement profile and final-year OR recent-grad regression."""

from __future__ import annotations

from datetime import date

from backend.db.models import Candidate, TargetPreference
from backend.services.eligibility_engine import evaluate_eligibility
from backend.services.job_content import classify_content_status, source_fingerprint
from backend.services.job_content import canonical_from_job
from backend.services.requirement_mining import mine_hard_requirements

AS_OF = date(2026, 8, 20)

LONG_POSTING = """
Software Engineering Intern — Platform

About us
We put customers first and have a sales-driven culture. Collaboration and
communication matter to everyone on the team.

The role
You will build APIs and internal tools with Python.

Requirements
- Python required
- SQL
- AWS preferred

Minimum Qualifications
Currently enrolled students are welcome. Bachelor's degree or equivalent
experience is a plus.

Who can apply
Please read this entire posting, including the last paragraph.

Responsibilities
- Build and maintain REST APIs
- Write tests
- Collaborate with senior engineers

Location
Hybrid, three days per week in San Francisco. Also hiring in New York and Austin.
Remote US only is not available for this intern role.
Travel is not required.

Compensation
This is a paid internship.

Work authorization
Sponsorship is not discussed in this posting.

""" + ("Additional program details, interview process, and team rituals. " * 40) + """

Additional Requirements
Candidates must either be in the final year of their degree program or have
graduated within the previous 12 months.
"""


def _candidate(**overrides) -> Candidate:
    return Candidate(
        user_id=1,
        name="Jordan Avery",
        email="jordan@example.com",
        skills=["Python", "SQL"],
        projects=[],
        experience=[{"title": "Software Engineer Intern", "company": "Northwind", "highlights": ["Python APIs"]}],
        education=[{"institution": "State University", "degree": "B.S.", "field": "Computer Science", "graduation_year": overrides.pop("graduation_year", "2028")}],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )


def _prefs(**overrides) -> TargetPreference:
    return TargetPreference(
        user_id=1,
        target_roles=["Software Engineer Intern"],
        preferred_locations=["Remote"],
        remote_preference=overrides.get("remote_preference", "hybrid"),
        currently_enrolled_in_program=overrides.get("currently_enrolled_in_program"),
        expected_graduation=overrides.get("expected_graduation"),
        academic_year=overrides.get("academic_year"),
        sponsorship_required=overrides.get("sponsorship_required"),
        work_mode_preferences=overrides.get("work_mode_preferences") or ["remote", "hybrid"],
    )


def _profile():
    canonical = canonical_from_job(
        title="Software Engineering Intern",
        company="Example Co",
        description=LONG_POSTING,
        source="manual",
        url="https://example.com/jobs/intern",
        content_status="full",
    )
    return mine_hard_requirements(canonical)


def test_fingerprint_is_stable() -> None:
    first = source_fingerprint("Software Engineering Intern", LONG_POSTING)
    second = source_fingerprint("  Software   Engineering Intern ", LONG_POSTING)
    assert first == second
    assert len(first) == 64


def test_adzuna_snippet_is_partial() -> None:
    assert classify_content_status("adzuna", "Short Adzuna snippet...") == "partial"
    assert classify_content_status("greenhouse", LONG_POSTING) == "full"


def test_final_year_or_recent_grad_is_extracted_from_end() -> None:
    profile = _profile()
    assert profile.requirement_groups
    group = profile.requirement_groups[0]
    assert group.operator == "any_of"
    assert "final year" in group.evidence_text.lower() or "final year" in group.text.lower()
    kinds = {
        (item.structured_condition or {}).get("kind")
        for item in profile.requirements
        if item.id in group.requirement_ids
    }
    assert kinds == {"final_year", "recent_graduate"}
    assert profile.work_mode == "hybrid"
    assert profile.hybrid_onsite_frequency == 3
    labels = {item.label for item in profile.locations}
    assert "San Francisco" in labels
    assert "New York" in labels
    assert "Austin" in labels


def test_remote_us_is_not_anywhere() -> None:
    canonical = canonical_from_job(
        title="Backend Engineer",
        company="Acme",
        description="Remote US only. Must overlap Pacific through Eastern business hours. "
        + ("Team culture notes. " * 80)
        + "Relocation is not required.",
        source="greenhouse",
        url="https://example.com/jobs/be",
        content_status="full",
    )
    profile = mine_hard_requirements(canonical)
    assert profile.work_mode == "remote"
    assert profile.remote_scope == "United States only"
    assert profile.timezone_requirements


def test_travel_percent_is_extracted() -> None:
    canonical = canonical_from_job(
        title="Solutions Engineer",
        company="Acme",
        description="Remote, but 50–75% travel is required. "
        + ("Customer visits and enablement. " * 80),
        source="lever",
        url="https://example.com/jobs/se",
        content_status="full",
    )
    profile = mine_hard_requirements(canonical)
    assert profile.travel_requirements
    assert profile.travel_requirements[0].structured_condition["min"] == 50


def test_unstated_sponsorship_is_watchout_not_failure() -> None:
    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year="2027"),
        _prefs(currently_enrolled_in_program="yes", academic_year="final_year", expected_graduation="2027-05"),
        as_of=AS_OF,
    )
    assert any("sponsorship not stated" in item.lower() for item in report.watchouts)
    assert report.status != "likely_ineligible"


def test_llm_cannot_invent_ungrounded_requirements() -> None:
    from backend.services.job_requirement_llm import LlmProfileDraft, LlmRequirementDraft, merge_llm_draft

    profile = _profile()
    before = len(profile.requirement_groups)
    draft = LlmProfileDraft(
        requirements=[
            LlmRequirementDraft(
                category="academic_year",
                text="Must own a yacht",
                importance="hard_required",
                evidence_text="Must own a yacht",
                structured_condition={"kind": "yacht"},
            )
        ]
    )
    merged = merge_llm_draft(profile, draft, LONG_POSTING)
    assert len(merged.requirement_groups) == before
    assert not any((item.structured_condition or {}).get("kind") == "yacht" for item in merged.requirements)


def test_candidate_a_not_final_year_is_ineligible() -> None:
    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year="2028"),
        _prefs(currently_enrolled_in_program="yes", academic_year="junior", expected_graduation="2028-05"),
        as_of=AS_OF,
    )
    assert report.groups
    assert report.groups[0].status == "not_satisfied"
    assert report.status == "likely_ineligible"


def test_candidate_b_final_year_satisfies_group() -> None:
    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year="2027"),
        _prefs(currently_enrolled_in_program="yes", academic_year="final_year", expected_graduation="2027-05"),
        as_of=AS_OF,
    )
    assert report.groups[0].status == "satisfied"
    assert report.status == "likely_eligible"


def test_candidate_c_recent_graduate_satisfies_group() -> None:
    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year="2026-02"),
        _prefs(currently_enrolled_in_program="no", academic_year=None, expected_graduation="2026-02"),
        as_of=AS_OF,
    )
    assert report.groups[0].status == "satisfied"
    assert report.status == "likely_eligible"


def test_candidate_d_missing_info_is_uncertain() -> None:
    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year=""),
        _prefs(currently_enrolled_in_program=None, academic_year=None, expected_graduation=None),
        as_of=AS_OF,
    )
    assert report.groups[0].status == "unknown"
    assert report.status == "eligibility_uncertain"


def test_ineligible_overlay_cannot_be_strong_match() -> None:
    from backend.services.analysis_service import ScoreBreakdown
    from backend.services.verified_fit_service import apply_verified_overlay

    profile = _profile()
    report = evaluate_eligibility(
        profile,
        _candidate(graduation_year="2028"),
        _prefs(currently_enrolled_in_program="yes", academic_year="junior", expected_graduation="2028-05"),
        as_of=AS_OF,
    )
    breakdown = ScoreBreakdown(
        skill=90,
        experience=80,
        education=70,
        location=60,
        preference=70,
        overall=88,
        recommendation="apply",
        rationale="Strong technical alignment.",
        match_tier="strong_match",
        apply_recommendation="strong_apply",
        score_kind="preliminary",
    )
    apply_verified_overlay(breakdown, report, content_status="full")
    assert breakdown.score_kind == "verified"
    assert breakdown.eligibility_status == "likely_ineligible"
    assert breakdown.match_tier != "strong_match"
    assert breakdown.apply_recommendation == "probably_skip"

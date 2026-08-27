"""Fit Score V2 scenario matrix. Ordering and ranges matter more than exact tenths."""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.models import Candidate, JobIntelligenceRecord, JobRecord, TargetPreference
from backend.services.analysis_service import RequirementsUnavailableError, score_job
from backend.services.fit_v2 import SCORING_VERSION, occupational_family

AS_OF = date(2026, 8, 20)
USER = 1


def _candidate(session, **overrides) -> Candidate:
    record = Candidate(
        user_id=overrides.get("user_id", USER),
        name="Matrix Candidate",
        email="matrix@example.com",
        skills=overrides.get("skills", ["Python", "FastAPI", "SQL", "React", "TypeScript"]),
        projects=overrides.get(
            "projects",
            [
                {
                    "name": "CareerPilot",
                    "description": "Built FastAPI endpoints and REST APIs.",
                    "technologies": ["Python", "FastAPI", "React"],
                }
            ],
        ),
        experience=overrides.get(
            "experience",
            [
                {
                    "title": "Software Engineer Intern",
                    "company": "Northwind",
                    "start_date": "2025-06",
                    "end_date": "2025-08",
                    "highlights": ["Built FastAPI endpoints for internal tools."],
                }
            ],
        ),
        education=overrides.get(
            "education",
            [
                {
                    "institution": "State University",
                    "degree": "B.S.",
                    "field": "Computer Science",
                    "graduation_year": "2027",
                }
            ],
        ),
        certifications=overrides.get("certifications", []),
        strengths=[],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _job(session, **overrides) -> JobRecord:
    record = JobRecord(
        public_id=overrides.get("public_id", "fit-v2-job"),
        title=overrides.get("title", "Software Engineer Intern"),
        company="Example Co",
        location=overrides.get("location", "Remote"),
        salary=overrides.get("salary", "$80,000/year"),
        url="https://example.com/jobs/fit-v2",
        description=overrides.get("description", "Requirements:\nPython\nFastAPI\n"),
        source="manual",
        status="discovered",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _prefs(session, candidate: Candidate, **overrides) -> TargetPreference:
    record = TargetPreference(
        candidate_id=candidate.id,
        user_id=candidate.user_id,
        target_roles=overrides.get("roles", ["Software Engineer Intern"]),
        preferred_locations=overrides.get("locations", ["Remote"]),
        remote_preference=overrides.get("remote", "remote"),
        salary_min=overrides.get("salary_min", 60000),
        work_authorization=overrides.get("work_authorization"),
        sponsorship_required=overrides.get("sponsorship_required"),
        constraints=overrides.get("constraints", ["role_type:internships"]),
        currently_enrolled_in_program=overrides.get("enrolled", "yes"),
        expected_graduation=overrides.get("graduation", "2027"),
        degree_pursuing=overrides.get("degree_pursuing", "Bachelor's"),
    )
    session.add(record)
    session.commit()
    return record


def _intel(session, job: JobRecord, **overrides) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=overrides.get("required", ["Python", "FastAPI"]),
        preferred_skills=overrides.get("preferred", ["Docker"]),
        years_experience=overrides.get("years"),
        education_requirements=overrides.get("education", []),
        tech_stack=overrides.get("tech", []),
        seniority=overrides.get("seniority", "intern"),
        responsibilities=overrides.get("responsibilities", ["Build and maintain REST APIs"]),
        likely_interview_focus=[],
    )
    session.add(record)
    session.commit()
    return record


def _score(session, job_id: str):
    return score_job(session, job_id, USER, as_of=AS_OF)


def test_perfect_intern_match(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(
        isolated_session,
        description=(
            "Software Engineer Intern\nCurrently enrolled students welcome.\n"
            "Requirements:\nPython\nFastAPI\nResponsibilities:\n"
            "- Build and maintain REST APIs\nPreferred:\nDocker"
        ),
    )
    _intel(isolated_session, job)
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert result.scoring_version == SCORING_VERSION
    assert result.qualification_score is not None and result.qualification_score >= 70
    assert result.eligibility_status in {"likely_eligible", "eligibility_uncertain"}
    assert result.match_tier in {"strong_match", "good_match", "possible_match"}
    assert result.recommendation != "skip"


def test_strong_skills_wrong_seniority(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(
        isolated_session,
        title="Senior Backend Engineer",
        description="Senior Backend Engineer. Requirements:\nPython\nFastAPI\n7+ years of experience",
    )
    _intel(
        isolated_session,
        job,
        required=["Python", "FastAPI"],
        seniority="senior",
        years=7,
        responsibilities=["Own backend services"],
    )
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    result = _score(isolated_session, job.public_id)
    assert result.qualification_score is not None and result.qualification_score <= 55
    assert result.match_tier in {"possible_match", "weak_match"}


def test_missing_one_preferred_skill(isolated_session) -> None:
    candidate = _candidate(isolated_session, skills=["Python", "FastAPI"])
    job = _job(isolated_session, description="Requirements:\nPython\nPreferred:\nDocker")
    _intel(isolated_session, job, required=["Python"], preferred=["Docker"], years=None, education=[])
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert "Docker" in result.missing_skills
    assert result.qualification_score is not None and result.qualification_score >= 55


def test_missing_several_required_skills(isolated_session) -> None:
    candidate = _candidate(isolated_session, skills=["Python"], projects=[], experience=[])
    job = _job(isolated_session, description="Requirements:\nPython\nJava\nKubernetes\nAWS")
    _intel(
        isolated_session,
        job,
        required=["Python", "Java", "Kubernetes", "AWS"],
        preferred=[],
        years=None,
        education=[],
        responsibilities=[],
    )
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert result.qualification_score is not None and result.qualification_score <= 62
    assert result.match_tier != "strong_match"


def test_exact_and_related_and_unrelated_technology(isolated_session) -> None:
    candidate = _candidate(isolated_session, skills=["TypeScript", "PostgreSQL", "Angular"], projects=[], experience=[])
    job = _job(isolated_session, description="Requirements:\nJavaScript\nSQL\nReact")
    _intel(
        isolated_session,
        job,
        required=["JavaScript", "SQL", "React"],
        preferred=[],
        years=None,
        education=[],
        responsibilities=[],
    )
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert "JavaScript" in result.partial_matches
    assert "SQL" in result.partial_matches
    assert "React" in result.missing_skills
    assert "Angular" not in result.matched_skills


def test_enrollment_and_completed_degree_gates(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    intern = _job(
        isolated_session,
        public_id="enroll-ok",
        description="Must currently be enrolled. Requirements:\nPython",
    )
    _intel(isolated_session, intern, required=["Python"], years=None, education=[], responsibilities=[])
    _prefs(isolated_session, candidate, enrolled="yes")
    intern_score = _score(isolated_session, intern.public_id)
    assert intern_score.eligibility_status != "likely_ineligible"

    full = _job(
        isolated_session,
        public_id="degree-block",
        title="Software Engineer",
        description="Bachelor's degree required. Must have completed Bachelor's degree before start. Requirements:\nPython",
    )
    _intel(isolated_session, full, required=["Python"], years=None, education=["Bachelor's"], seniority="entry")
    blocked = _score(isolated_session, full.public_id)
    assert blocked.eligibility_status == "likely_ineligible"
    assert blocked.apply_recommendation == "probably_skip"
    assert blocked.recommendation != "apply"


def test_degree_or_equivalent_experience(isolated_session) -> None:
    candidate = _candidate(
        isolated_session,
        education=[],
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "2018-01",
                "end_date": "Present",
                "highlights": ["Built APIs."],
            }
        ],
    )
    job = _job(
        isolated_session,
        title="Software Engineer",
        description="Bachelor's degree or equivalent experience. Requirements:\nPython",
    )
    _intel(isolated_session, job, required=["Python"], years=None, education=["Bachelor's"], seniority="mid")
    _prefs(isolated_session, candidate, roles=["Software Engineer"], constraints=["role_type:full_time"], enrolled="no")
    result = _score(isolated_session, job.public_id)
    assert result.qualification_score is not None and result.qualification_score >= 55
    assert result.eligibility_status != "likely_ineligible"


def test_zero_years_vs_explicit_five(isolated_session) -> None:
    candidate = _candidate(isolated_session, experience=[])
    job = _job(
        isolated_session,
        title="Software Engineer",
        description="Requirements:\nPython\n5+ years of experience",
    )
    _intel(isolated_session, job, required=["Python"], years=5, education=[], seniority="mid", responsibilities=[])
    _prefs(isolated_session, candidate, roles=["Software Engineer"], constraints=[])
    result = _score(isolated_session, job.public_id)
    assert result.experience_score is None or result.experience_score <= 40
    assert result.eligibility_status != "likely_ineligible"


def test_location_and_remote_cases(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    remote = _job(isolated_session, public_id="remote-ok", location="Remote", description="Requirements:\nPython")
    _intel(isolated_session, remote, required=["Python"], years=None, education=[], responsibilities=[])
    _prefs(isolated_session, candidate, remote="remote", locations=["Remote"])
    remote_score = _score(isolated_session, remote.public_id)
    assert remote_score.preference_score is not None and remote_score.preference_score >= 70

    onsite = _job(
        isolated_session,
        public_id="onsite-block",
        location="Onsite, Austin, TX",
        description="On-site only. Requirements:\nPython",
    )
    _intel(isolated_session, onsite, required=["Python"], years=None, education=[], responsibilities=[])
    blocked = _score(isolated_session, onsite.public_id)
    assert blocked.eligibility_status == "likely_ineligible"


def test_sponsorship_known_and_unknown(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, sponsorship_required=True)
    unknown = _job(isolated_session, public_id="auth-unknown", description="Requirements:\nPython")
    _intel(isolated_session, unknown, required=["Python"], years=None, education=[], responsibilities=[])
    unknown_score = _score(isolated_session, unknown.public_id)
    assert unknown_score.eligibility_status == "likely_eligible"
    assert any("not listed" in item.lower() for item in unknown_score.watchouts or [])

    blocked = _job(
        isolated_session,
        public_id="auth-block",
        description="Must have unrestricted work authorization. No sponsorship. Requirements:\nPython",
    )
    _intel(isolated_session, blocked, required=["Python"], years=None, education=[], responsibilities=[])
    blocked_score = _score(isolated_session, blocked.public_id)
    assert blocked_score.eligibility_status == "likely_ineligible"
    assert blocked_score.apply_recommendation == "probably_skip"


def test_sparse_vs_rich_description_confidence(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate)
    sparse = _job(isolated_session, public_id="sparse", description="Requirements:\nPython")
    _intel(isolated_session, sparse, required=["Python"], preferred=[], years=None, education=[], responsibilities=[])
    sparse_score = _score(isolated_session, sparse.public_id)
    rich = _job(
        isolated_session,
        public_id="rich",
        description=(
            "Software Engineer Intern in a product team.\n"
            "Requirements:\nPython\nFastAPI\nSQL\n"
            "Responsibilities:\n- Build and maintain REST APIs\n- Write tests\n"
            "Preferred:\nDocker\nCurrently enrolled students welcome.\n"
            + ("Details about the team, stack, and interviews. " * 20)
        ),
    )
    _intel(
        isolated_session,
        rich,
        required=["Python", "FastAPI", "SQL"],
        preferred=["Docker"],
        years=None,
        education=[],
        responsibilities=["Build and maintain REST APIs", "Write tests"],
    )
    rich_score = _score(isolated_session, rich.public_id)
    assert (sparse_score.confidence_score or 0) < (rich_score.confidence_score or 0)
    assert sparse_score.overall_score < 96
    assert (rich_score.ranking_score or 0) >= (sparse_score.ranking_score or 0)


def test_high_fit_low_confidence_ranks_below_high_confidence(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate)
    low = _job(isolated_session, public_id="low-conf", description="Requirements:\nPython")
    _intel(isolated_session, low, required=["Python"], preferred=[], years=None, education=[], responsibilities=[])
    low_score = _score(isolated_session, low.public_id)
    high = _job(
        isolated_session,
        public_id="high-conf",
        description=(
            "Software Engineer Intern. Currently enrolled.\nRequirements:\nPython\nFastAPI\n"
            "Responsibilities:\n- Build and maintain REST APIs\n"
            + ("More posting evidence about the team and the work. " * 25)
        ),
    )
    _intel(
        isolated_session,
        high,
        required=["Python", "FastAPI"],
        preferred=[],
        years=None,
        education=[],
        responsibilities=["Build and maintain REST APIs"],
    )
    high_score = _score(isolated_session, high.public_id)
    assert (high_score.confidence_score or 0) > (low_score.confidence_score or 0)
    assert (high_score.ranking_score or 0) >= (low_score.ranking_score or 0)


def test_responsibilities_without_exact_wording(isolated_session) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        projects=[{"name": "API", "description": "Built FastAPI endpoints for CareerPilot.", "technologies": ["FastAPI"]}],
        experience=[],
    )
    job = _job(
        isolated_session,
        description="Requirements:\nPython\nResponsibilities:\n- Build and maintain REST APIs",
    )
    _intel(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        years=None,
        education=[],
        responsibilities=["Build and maintain REST APIs"],
    )
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert result.covered_responsibilities or result.partial_responsibilities


def test_keyword_stuffing_without_responsibilities(isolated_session) -> None:
    stuffed = _candidate(
        isolated_session,
        skills=["Python", "FastAPI", "SQL", "Docker", "AWS", "React"],
        projects=[],
        experience=[],
    )
    job = _job(
        isolated_session,
        description="Requirements:\nPython\nResponsibilities:\n- Lead enterprise sales negotiations with Fortune 100 buyers",
    )
    _intel(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        years=None,
        education=[],
        responsibilities=["Lead enterprise sales negotiations with Fortune 100 buyers"],
    )
    _prefs(isolated_session, stuffed)
    result = _score(isolated_session, job.public_id)
    assert result.uncovered_responsibilities
    assert result.qualification_score is not None and result.qualification_score < 90


def test_no_education_requirement_is_unknown_not_mismatch(isolated_session) -> None:
    candidate = _candidate(isolated_session, education=[])
    job = _job(isolated_session, description="Requirements:\nPython")
    _intel(isolated_session, job, required=["Python"], preferred=[], years=None, education=[], responsibilities=[])
    _prefs(isolated_session, candidate)
    result = _score(isolated_session, job.public_id)
    assert result.education_score is None


def test_missing_mandatory_license(isolated_session) -> None:
    candidate = _candidate(isolated_session, certifications=[])
    job = _job(
        isolated_session,
        title="Staff Accountant",
        description="CPA required. Must have CPA. Requirements:\nPython",
    )
    _intel(isolated_session, job, required=["Python"], years=None, education=[], seniority="mid", responsibilities=[])
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    result = _score(isolated_session, job.public_id)
    assert result.eligibility_status == "likely_ineligible"


def test_target_role_and_role_type_mismatch(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(
        isolated_session,
        title="Senior Product Manager",
        description="Senior Product Manager. Requirements:\nPython",
    )
    _intel(isolated_session, job, required=["Python"], years=None, education=[], seniority="senior", responsibilities=[])
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"], constraints=["role_type:internships"])
    result = _score(isolated_session, job.public_id)
    assert result.preference_score is not None and result.preference_score < 50


def test_salary_below_minimum_and_unlisted(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    low = _job(
        isolated_session,
        public_id="low-pay",
        salary="$40,000/year",
        description="Requirements:\nPython",
    )
    _intel(isolated_session, low, required=["Python"], years=None, education=[], responsibilities=[])
    _prefs(isolated_session, candidate, salary_min=90000)
    low_score = _score(isolated_session, low.public_id)
    assert low_score.preference_score is not None and low_score.preference_score < 50

    none = _job(isolated_session, public_id="no-pay", salary=None, description="Requirements:\nPython")
    _intel(isolated_session, none, required=["Python"], years=None, education=[], responsibilities=[])
    none_score = _score(isolated_session, none.public_id)
    assert any("salary" in item.lower() for item in none_score.watchouts or [])


def test_multiple_must_have_blockers(isolated_session) -> None:
    candidate = _candidate(isolated_session, certifications=[])
    job = _job(
        isolated_session,
        title="Onsite CPA Director",
        location="Onsite, Boston, MA",
        description=(
            "Director role onsite only. No sponsorship. CPA required. Must have CPA. "
            "Requirements:\nPython"
        ),
    )
    _intel(isolated_session, job, required=["Python"], years=None, education=[], seniority="director", responsibilities=[])
    _prefs(isolated_session, candidate, sponsorship_required=True, remote="remote")
    result = _score(isolated_session, job.public_id)
    assert result.eligibility_status == "likely_ineligible"
    assert result.overall_score <= 48
    assert result.apply_recommendation == "probably_skip"


def test_preliminary_score_when_title_is_useful(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate)
    job = _job(
        isolated_session,
        title="Software Engineer Intern",
        description="Join a thoughtful team building customer products together.",
    )
    result = _score(isolated_session, job.public_id)
    assert result.score_kind == "preliminary"
    assert result.confidence_level == "low"
    assert result.recommendation != "apply"


def test_still_unscored_without_useful_evidence(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate)
    job = _job(
        isolated_session,
        title="Team Contributor",
        location=None,
        description="Join a collaborative team solving thoughtful customer problems.",
    )
    with pytest.raises(RequirementsUnavailableError):
        _score(isolated_session, job.public_id)


def test_no_llm_and_deterministic(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _intel(isolated_session, job)
    _prefs(isolated_session, candidate)
    first = _score(isolated_session, job.public_id)
    second = _score(isolated_session, job.public_id)
    assert first.overall_score == second.overall_score
    assert first.ranking_score == second.ranking_score
    assert first.eligibility_status == second.eligibility_status


def test_swe_intern_vs_investment_banking_and_marketing(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    swe = _job(
        isolated_session,
        public_id="swe-intern",
        title="Software Engineering Intern",
        description="Currently enrolled students welcome. Requirements:\nPython\nFastAPI",
    )
    _intel(isolated_session, swe, seniority="intern")
    ib = _job(
        isolated_session,
        public_id="ib-intern",
        title="Investment Banking Intern",
        description="Currently enrolled students welcome. Requirements:\nExcel\nFinancial modeling",
    )
    _intel(
        isolated_session,
        ib,
        required=["Excel"],
        preferred=[],
        seniority="intern",
        responsibilities=["Build financial models"],
    )
    marketing = _job(
        isolated_session,
        public_id="mkt-intern",
        title="Marketing Intern",
        description="Currently enrolled students welcome. Requirements:\nExcel",
    )
    _intel(
        isolated_session,
        marketing,
        required=["Excel"],
        preferred=[],
        seniority="intern",
        responsibilities=["Draft campaign copy"],
    )
    swe_score = _score(isolated_session, swe.public_id)
    ib_score = _score(isolated_session, ib.public_id)
    mkt_score = _score(isolated_session, marketing.public_id)
    assert occupational_family("Software Engineering Intern") == "software_engineering"
    assert occupational_family("Investment Banking Intern") == "investment_banking"
    assert occupational_family("Marketing Intern") == "marketing"
    assert occupational_family("Data Science Intern (Customer Success)") == "data_science"
    assert (swe_score.ranking_score or 0) > (ib_score.ranking_score or 0)
    assert (swe_score.ranking_score or 0) > (mkt_score.ranking_score or 0)
    assert any("occupational lane" in item.lower() for item in ib_score.gap_reasons or [])
    assert any("occupational lane" in item.lower() for item in mkt_score.gap_reasons or [])
    assert not any("title aligns" in item.lower() for item in ib_score.match_reasons or [])


def test_data_analyst_intern_related_to_data_target(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, roles=["Data Analyst Intern", "Software Engineer Intern"])
    job = _job(
        isolated_session,
        title="Data Analyst Intern",
        description="Currently enrolled. Requirements:\nSQL\nPython",
    )
    _intel(isolated_session, job, required=["SQL", "Python"], preferred=[], seniority="intern", responsibilities=[])
    result = _score(isolated_session, job.public_id)
    assert result.qualification_score is not None and result.qualification_score >= 55
    assert any("title aligns" in item.lower() for item in result.match_reasons or [])


def test_shared_intern_level_without_family_match(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    job = _job(
        isolated_session,
        title="Investment Banking Intern Summer Analyst",
        description="Internship. Currently enrolled. Requirements:\nExcel",
    )
    _intel(isolated_session, job, required=["Excel"], preferred=[], seniority="intern", responsibilities=[])
    result = _score(isolated_session, job.public_id)
    assert any("occupational lane" in item.lower() for item in result.gap_reasons or [])
    assert not any("title aligns" in item.lower() for item in result.match_reasons or [])


def test_matching_family_wrong_seniority(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    job = _job(
        isolated_session,
        title="Staff Software Engineer",
        description="Requirements:\nPython\nFastAPI",
    )
    _intel(isolated_session, job, seniority="staff", years=8, responsibilities=["Own backend services"])
    result = _score(isolated_session, job.public_id)
    assert any("title aligns" in item.lower() for item in result.match_reasons or [])
    assert any("seniority" in item.lower() for item in result.gap_reasons or [])
    assert result.qualification_score is not None and result.qualification_score <= 55


def test_generic_customer_in_about_section_does_not_boost(isolated_session) -> None:
    candidate = _candidate(
        isolated_session,
        experience=[
            {
                "title": "Software Engineer Intern",
                "company": "Northwind",
                "start_date": "2025-06",
                "end_date": "2025-08",
                "highlights": ["Customer-facing support for internal engineering users."],
            }
        ],
    )
    _prefs(isolated_session, candidate, roles=["Software Engineer Intern"])
    about = _job(
        isolated_session,
        public_id="about-customer",
        title="Investment Banking Intern",
        description=(
            "About us\nWe put customers first and have a sales-driven culture.\n"
            "Requirements:\nExcel"
        ),
    )
    _intel(isolated_session, about, required=["Excel"], preferred=[], seniority="intern", responsibilities=[])
    about_score = _score(isolated_session, about.public_id)
    assert not any("customer" in item.lower() or "sales" in item.lower() for item in about_score.match_reasons or [])

    explicit = _job(
        isolated_session,
        public_id="role-customer",
        title="Software Engineering Intern",
        description="Requirements:\nPython\nCustomer-facing support for engineering users.",
    )
    _intel(
        isolated_session,
        explicit,
        required=["Python"],
        preferred=[],
        seniority="intern",
        responsibilities=["Customer-facing support for engineering users."],
    )
    explicit_score = _score(isolated_session, explicit.public_id)
    assert any("customer-facing" in item.lower() for item in explicit_score.match_reasons or [])


def test_enrollment_makes_likely_eligible_without_sponsorship_text(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, enrolled="yes", sponsorship_required=True)
    job = _job(
        isolated_session,
        description="Currently enrolled students welcome. Requirements:\nPython\nFastAPI",
    )
    _intel(isolated_session, job, seniority="intern")
    result = _score(isolated_session, job.public_id)
    assert result.eligibility_status == "likely_eligible"
    assert any("not listed" in item.lower() for item in result.watchouts or [])


def test_low_confidence_preliminary_cannot_be_strong_match(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate)
    job = _job(isolated_session, description="Requirements:\nPython")
    _intel(isolated_session, job, required=["Python"], preferred=[], years=None, education=[], responsibilities=[])
    result = _score(isolated_session, job.public_id)
    if (result.overall_score or 0) >= 85:
        assert result.match_tier != "strong_match"
        assert result.confidence_level == "low"
        assert result.score_kind == "preliminary"


def test_high_confidence_deep_fit_can_be_strong_match(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    _prefs(isolated_session, candidate, enrolled="yes")
    job = _job(
        isolated_session,
        description=(
            "Software Engineer Intern. Currently enrolled students welcome.\n"
            "Requirements:\nPython\nFastAPI\nSQL\n"
            "Responsibilities:\n- Build and maintain REST APIs\n- Write tests\n"
            + ("Details about the internship work, stack, and interviews. " * 30)
        ),
    )
    _intel(
        isolated_session,
        job,
        required=["Python", "FastAPI", "SQL"],
        preferred=["Docker"],
        seniority="intern",
        responsibilities=["Build and maintain REST APIs", "Write tests"],
    )
    result = _score(isolated_session, job.public_id)
    assert result.score_kind == "full"
    assert result.confidence_level in {"medium", "high"}
    if (result.overall_score or 0) >= 85 and result.confidence_level != "low":
        assert result.match_tier == "strong_match"

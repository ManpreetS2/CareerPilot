"""Deterministic Fit & Gap scoring tests. Isolated SQLite only; no providers."""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.db.models import (
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.services import analysis_service
from backend.services.analysis_service import (
    RequirementsUnavailableError,
    extract_explicit_skills_from_description,
    score_job,
)


def _candidate(
    session,
    *,
    skills: list[str] | None = None,
    experience: list | None = None,
    education: list | None = None,
    projects: list | None = None,
    certifications: list | None = None,
) -> Candidate:
    record = Candidate(
        name="Jordan Avery Quill",
        email="jordan.quill@example.com",
        phone="+1-555-0101",
        skills=["Python", "FastAPI", "SQL"] if skills is None else skills,
        projects=[
            {
                "name": "Harbor Atlas",
                "description": "Dashboard built with FastAPI.",
                "technologies": ["Python", "React"],
                "url": "https://github.com/example/harbor-atlas",
            }
        ]
        if projects is None
        else projects,
        experience=[
            {
                "title": "Software Engineer",
                "company": "Northwind Systems",
                "start_date": "2023-01",
                "end_date": "Present",
                "highlights": ["Built APIs in Python."],
            }
        ]
        if experience is None
        else experience,
        education=[
            {
                "institution": "Lakeside Polytechnic",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2022",
            }
        ]
        if education is None
        else education,
        certifications=["AWS Cloud Practitioner"] if certifications is None else certifications,
        strengths=[],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _job(
    session,
    *,
    public_id: str = "job-fit-001",
    title: str = "Software Engineer",
    location: str = "Remote",
    salary: str = "$120,000/year",
    description: str = "We need Python and FastAPI.",
) -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title=title,
        company="Maple Circuit Labs",
        location=location,
        salary=salary,
        url="https://example.com/jobs/software-engineer",
        description=description,
        source="manual",
        status="discovered",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _intelligence(
    session,
    job: JobRecord,
    *,
    required: list[str] | None = None,
    preferred: list[str] | None = None,
    tech: list[str] | None = None,
    years: int | None = 2,
    education: list[str] | None = None,
) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "FastAPI"] if required is None else required,
        preferred_skills=["Docker"] if preferred is None else preferred,
        years_experience=years,
        education_requirements=["Bachelor's in Computer Science"] if education is None else education,
        tech_stack=["SQL"] if tech is None else tech,
        seniority="mid",
        responsibilities=["Build APIs"],
        likely_interview_focus=["Python"],
    )
    session.add(record)
    session.commit()
    return record


def _prefs(
    session,
    candidate: Candidate | None,
    *,
    roles: list[str] | None = None,
    locations: list[str] | None = None,
    remote: str | None = "remote",
    salary_min: int | None = 100000,
) -> TargetPreference:
    record = TargetPreference(
        candidate_id=candidate.id if candidate else None,
        target_roles=["Software Engineer"] if roles is None else roles,
        preferred_locations=["Remote"] if locations is None else locations,
        remote_preference=remote,
        salary_min=salary_min,
        work_authorization=None,
        sponsorship_required=None,
        constraints=[],
    )
    session.add(record)
    session.commit()
    return record


def test_unknown_job_returns_404(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _candidate(db)
        assert db.query(MatchScoreRecord).count() == 0
    response = client.post("/api/jobs/missing-job/score")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 0


def test_missing_candidate_returns_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db)
        assert db.query(MatchScoreRecord).count() == 0
    response = client.post("/api/jobs/job-fit-001/score")
    assert response.status_code == 409
    assert "candidate profile" in response.json()["detail"].lower()
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 0


def test_missing_requirements_return_409_without_persistence(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _candidate(db)
        _job(db, description="Join a collaborative team working on interesting problems.")
        assert db.query(MatchScoreRecord).count() == 0
    response = client.post("/api/jobs/job-fit-001/score")
    assert response.status_code == 409
    assert "requirements" in response.json()["detail"].lower()
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 0


def test_existing_job_intelligence_is_used(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session, description="Python FastAPI Docker SQL Bachelor's in Computer Science")
    _intelligence(isolated_session, job)
    _prefs(isolated_session, candidate)
    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    assert "Python" in result.matched_skills
    assert "FastAPI" in result.matched_skills
    assert result.rationale.lower().startswith("full job intelligence")
    assert result.recommendation in {"apply", "consider", "skip"}


def test_unsupported_intelligence_items_dropped_before_scoring(isolated_session, caplog: pytest.LogCaptureFixture) -> None:
    candidate = _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Python required.")
    _intelligence(
        isolated_session,
        job,
        required=["Python", "Quantum Teleportation"],
        preferred=["Warp Drive"],
        tech=[],
        years=None,
        education=[],
    )
    with caplog.at_level(logging.INFO, logger="backend.services.analysis_service"):
        result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    assert "Python" in result.matched_skills
    assert "Quantum Teleportation" not in result.matched_skills
    assert "Quantum Teleportation" not in result.missing_skills
    assert "Warp Drive" not in result.missing_skills
    assert "Quantum Teleportation" not in caplog.text
    assert "dropped=" in caplog.text


def test_description_only_fallback_is_marked_provisional(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python", "Docker"])
    job = _job(
        isolated_session,
        description="Requirements: Python.\nPreferred: Docker.\nWe also use Git.",
    )
    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    assert "provisional" in result.rationale.lower()
    assert result.recommendation != "apply"


def test_provisional_scoring_never_returns_apply(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python", "FastAPI", "SQL", "Docker", "React"],
        experience=[
            {
                "title": "Software Engineer",
                "company": "Northwind Systems",
                "start_date": "2018-01",
                "end_date": "Present",
                "highlights": [],
            }
        ],
    )
    job = _job(isolated_session, description="Requirements: Python, FastAPI, SQL, Docker, React.")
    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    assert result.recommendation != "apply"
    assert result.overall_score >= 60
    assert result.recommendation == "consider"


def test_explicit_required_preferred_classification() -> None:
    grounded = extract_explicit_skills_from_description(
        "Requirements:\nPython\nPreferred:\nDocker\nTeam tools:\nGit"
    )
    assert grounded.required == ["Python"]
    assert grounded.preferred == ["Docker"]
    assert "Git" in grounded.tech_stack
    assert grounded.source == "description"


def test_exact_skill_match(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert result.matched_skills == ["Python"]
    assert result.missing_skills == []


def test_java_is_not_javascript() -> None:
    grounded = extract_explicit_skills_from_description("Requirements: JavaScript.")
    assert grounded.required == ["JavaScript"]
    assert "Java" not in grounded.required
    java_only = extract_explicit_skills_from_description("Requirements: Java.")
    assert java_only.required == ["Java"]


def test_go_does_not_match_google() -> None:
    grounded = extract_explicit_skills_from_description("We work with Google Cloud.")
    assert "Go" not in grounded.required + grounded.preferred + grounded.tech_stack


def test_c_and_r_boundaries() -> None:
    grounded = extract_explicit_skills_from_description("Career research papers. Requirements: C, R, Go.")
    assert grounded.required == ["C", "R", "Go"]
    none = extract_explicit_skills_from_description("Career research and Google Cloud.")
    assert none.required == []
    assert none.tech_stack == []


def test_postgres_and_js_aliases() -> None:
    grounded = extract_explicit_skills_from_description("Requirements: Postgres and JS.")
    assert grounded.required == ["PostgreSQL", "JavaScript"]


def test_no_unsupported_fuzzy_match(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.\nBonus: Kubernetes.")
    result = score_job(isolated_session, job.public_id)
    assert "Kubernetes" not in result.matched_skills
    assert "Kubernetes" in result.missing_skills


def test_no_invented_missing_skill(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert result.missing_skills == []
    assert "Kubernetes" not in result.missing_skills


def test_required_skills_weighted_more_than_preferred(isolated_session) -> None:
    job = _job(
        isolated_session,
        description=(
            "Requirements:\nPython\nPreferred:\nDocker\n"
            "Education:\nBachelor's in Computer Science"
        ),
    )
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=["Docker"],
        tech=[],
        years=None,
        education=[],
    )
    required_only = _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    _prefs(isolated_session, required_only, roles=[], locations=[], remote=None, salary_min=None)
    high = score_job(isolated_session, job.public_id)
    isolated_session.query(MatchScoreRecord).delete()
    isolated_session.query(TargetPreference).delete()
    isolated_session.query(Candidate).delete()
    isolated_session.commit()
    preferred_only = _candidate(isolated_session, skills=["Docker"], experience=[], education=[], projects=[], certifications=[])
    _prefs(isolated_session, preferred_only, roles=[], locations=[], remote=None, salary_min=None)
    low = score_job(isolated_session, job.public_id)
    assert high.skill_score is not None and low.skill_score is not None
    assert high.skill_score > low.skill_score


def test_unavailable_components_remain_null(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    job = _job(isolated_session, location="", salary=None, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert result.experience_score is None
    assert result.education_score is None


def test_available_component_weights_are_renormalized(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    job = _job(isolated_session, location="", salary=None, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert result.skill_score is not None
    assert result.overall_score == result.skill_score


def test_overlapping_experience_ranges_are_not_double_counted(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "A",
                "start_date": "2024-01",
                "end_date": "2025-01",
                "highlights": [],
            },
            {
                "title": "Engineer",
                "company": "B",
                "start_date": "2024-06",
                "end_date": "2025-06",
                "highlights": [],
            },
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        description=(
            "Requirements: Python and 2 years of work experience. "
            "Bachelor's in Computer Science"
        ),
    )
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=2,
        education=[],
    )
    result = score_job(isolated_session, job.public_id, as_of=date(2026, 1, 1))
    assert result.experience_score is not None
    # Merged span is ~17 months, not 24. Double-counting would reach 100.
    assert 60.0 <= result.experience_score <= 80.0


def test_unknown_dates_do_not_become_zero_experience(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[{"title": "Engineer", "company": "A", "start_date": None, "end_date": None, "highlights": []}],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(isolated_session, description="Python")
    _intelligence(isolated_session, job, required=["Python"], preferred=[], tech=[], years=3, education=[])
    result = score_job(isolated_session, job.public_id)
    assert result.experience_score is None


def test_education_requirement_match_and_mismatch(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Python Bachelor's in Computer Science")
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=["Bachelor's in Computer Science"],
    )
    match = score_job(isolated_session, job.public_id)
    assert match.education_score == 100.0
    isolated_session.query(MatchScoreRecord).delete()
    isolated_session.query(Candidate).delete()
    isolated_session.commit()
    _candidate(
        isolated_session,
        skills=["Python"],
        education=[{"institution": "City College", "degree": "A.A.", "field": "General Studies", "graduation_year": "2020"}],
        experience=[],
        projects=[],
        certifications=[],
    )
    mismatch = score_job(isolated_session, job.public_id)
    assert mismatch.education_score == 0.0


def test_missing_preferences_do_not_penalize(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    job = _job(isolated_session, location="", salary=None, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert result.preference_score is None
    assert result.location_score is None
    assert result.overall_score == result.skill_score


def test_annual_salary_comparison_only_when_parseable(isolated_session) -> None:
    candidate = _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    _prefs(isolated_session, candidate, roles=[], locations=[], remote=None, salary_min=100000)
    hourly = _job(isolated_session, public_id="job-hourly", salary="$50/hour", location="", description="Requirements: Python.")
    hourly_score = score_job(isolated_session, hourly.public_id)
    assert hourly_score.preference_score is None
    annual = _job(isolated_session, public_id="job-annual", salary="$150,000/year", location="", description="Requirements: Python.")
    annual_score = score_job(isolated_session, annual.public_id)
    assert annual_score.preference_score == 100.0


def test_score_clamped_to_0_100(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    result = score_job(isolated_session, job.public_id)
    assert 0 <= result.overall_score <= 100
    assert result.skill_score is None or 0 <= result.skill_score <= 100


def test_deterministic_repeated_results(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session, description="Python FastAPI Docker SQL Bachelor's in Computer Science")
    _intelligence(isolated_session, job)
    _prefs(isolated_session, candidate)
    first = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    second = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    assert first.overall_score == second.overall_score
    assert first.recommendation == second.recommendation
    assert first.matched_skills == second.matched_skills


def test_recommendation_thresholds(isolated_session) -> None:
    candidate = _candidate(isolated_session, skills=["Python", "FastAPI", "SQL", "Docker"])
    job = _job(isolated_session, description="Python FastAPI Docker SQL Bachelor's in Computer Science")
    _intelligence(isolated_session, job, required=["Python", "FastAPI"], preferred=["Docker"], tech=["SQL"], years=1)
    _prefs(isolated_session, candidate)
    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))
    if result.overall_score >= 80:
        assert result.recommendation == "apply"
    elif result.overall_score >= 60:
        assert result.recommendation == "consider"
    else:
        assert result.recommendation == "skip"


def test_persisted_foreign_keys_are_correct(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session, description="Requirements: Python.")
    score_job(isolated_session, job.public_id)
    row = isolated_session.query(MatchScoreRecord).one()
    assert row.job_id == job.id
    assert row.candidate_id == candidate.id


def test_second_score_updates_instead_of_duplicating(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    score_job(isolated_session, job.public_id)
    score_job(isolated_session, job.public_id)
    assert isolated_session.query(MatchScoreRecord).count() == 1


def test_rollback_on_commit_failure(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    with patch.object(isolated_session, "commit", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            score_job(isolated_session, job.public_id)
    isolated_session.rollback()
    assert isolated_session.query(MatchScoreRecord).count() == 0


def test_no_row_after_scoring_failure(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session, description="No known technologies here.")
    with pytest.raises(RequirementsUnavailableError):
        score_job(isolated_session, job.public_id)
    assert isolated_session.query(MatchScoreRecord).count() == 0


def test_logs_contain_counts_and_ids_only(isolated_session, caplog: pytest.LogCaptureFixture) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session, description="Python FastAPI")
    _intelligence(isolated_session, job, education=[])
    with caplog.at_level(logging.INFO, logger="backend.services.analysis_service"):
        score_job(isolated_session, job.public_id)
    assert "Jordan Avery Quill" not in caplog.text
    assert "jordan.quill@example.com" not in caplog.text
    assert "+1-555-0101" not in caplog.text
    assert "Quantum" not in caplog.text


def test_mock_hash_fake_skill_path_is_unreachable() -> None:
    assert not hasattr(analysis_service, "mock_match_score")
    source = open(analysis_service.__file__, encoding="utf-8").read()
    assert "hashlib" not in source
    assert "Mock Day 1 score" not in source
    assert "sha256" not in source
    assert 'matched_skills=["Python", "SQL", "FastAPI"]' not in source


def test_route_uses_request_scoped_database_session(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _candidate(db)
        _job(db, description="Requirements: Python.")
    with patch("backend.db.database.SessionLocal") as forbidden:
        response = client.post("/api/jobs/job-fit-001/score")
    assert response.status_code == 200
    forbidden.assert_not_called()
    body = response.json()
    assert body["job_id"] == "job-fit-001"
    assert "Python" in body["matched_skills"]


def test_unlinked_preference_fallback(isolated_session) -> None:
    _candidate(isolated_session, skills=["Python"], experience=[], education=[], projects=[], certifications=[])
    _prefs(isolated_session, None, roles=["Software Engineer"], locations=["Remote"], remote="remote", salary_min=None)
    job = _job(isolated_session, description="Requirements: Python.", location="Remote")
    result = score_job(isolated_session, job.public_id)
    assert result.location_score == 100.0
    assert result.preference_score is not None


def test_intelligence_years_are_dropped_without_explicit_source_evidence(
    isolated_session,
) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Fictional Systems",
                "start_date": "2025-01",
                "end_date": "2026-01",
                "highlights": [],
            }
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(isolated_session, description="Requirements:\nPython")
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=7,
        education=[],
    )

    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))

    assert result.experience_score is None


def test_source_wording_reclassifies_stored_required_and_preferred_skills(
    isolated_session,
) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        location="",
        salary=None,
        description="Preferred:\nDocker\nRequirements:\nPython",
    )
    _intelligence(
        isolated_session,
        job,
        required=["Docker"],
        preferred=["Python"],
        tech=[],
        years=None,
        education=[],
    )

    result = score_job(isolated_session, job.public_id)

    assert result.skill_score == 75.0
    assert result.matched_skills == ["Python"]
    assert result.missing_skills == ["Docker"]


def test_description_section_heading_applies_to_long_requirement_lines() -> None:
    grounded = extract_explicit_skills_from_description(
        "Requirements:\nExperience building production APIs with Python and Docker"
    )

    assert grounded.required == ["Python", "Docker"]
    assert grounded.tech_stack == []


def test_alias_duplicate_requirements_are_scored_once(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["PostgreSQL"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        location="",
        salary=None,
        description="Requirements: PostgreSQL (Postgres).",
    )
    _intelligence(
        isolated_session,
        job,
        required=["PostgreSQL", "Postgres"],
        preferred=[],
        tech=[],
        years=None,
        education=[],
    )

    result = score_job(isolated_session, job.public_id)

    assert result.skill_score == 100.0
    assert result.matched_skills == ["PostgreSQL"]


@pytest.mark.parametrize("candidate_label", ["Node JS", "Node-JS", "NODE.JS"])
def test_nodejs_candidate_punctuation_variants_match_safely(
    isolated_session,
    candidate_label: str,
) -> None:
    _candidate(
        isolated_session,
        skills=[candidate_label],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        public_id=f"node-{candidate_label.lower().replace('.', '').replace(' ', '-').replace('#', 'sharp')}",
        location="",
        salary=None,
        description="Requirements: Node.js.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.matched_skills == ["Node.js"]


def test_future_employment_does_not_create_positive_experience(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Future Fiction LLC",
                "start_date": "2027-01-01",
                "end_date": "2028-01-01",
                "highlights": [],
            }
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        description="Requirements: Python and at least 1 year of work experience.",
    )
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=1,
        education=[],
    )

    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))

    assert result.experience_score is None


def test_ambiguous_degree_and_field_abbreviations_do_not_match(
    isolated_session,
) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        education=[
            {
                "institution": "Fictional Technical College",
                "degree": "BS",
                "field": "CS",
                "graduation_year": "2025",
            }
        ],
        experience=[],
        projects=[],
        certifications=[],
    )
    job = _job(isolated_session, description="Requirements: Python. BS in CS required.")
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=["BS in CS"],
    )

    result = score_job(isolated_session, job.public_id)

    assert result.education_score == 0.0


def test_education_field_does_not_match_from_institution_name(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        education=[
            {
                "institution": "Computer Science Academy",
                "degree": "Bachelor's",
                "field": "History",
                "graduation_year": "2024",
            }
        ],
        experience=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        description="Requirements: Python. Bachelor's in Computer Science.",
    )
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=["Bachelor's in Computer Science"],
    )

    result = score_job(isolated_session, job.public_id)

    assert result.education_score == 0.0


def test_ambiguous_job_location_is_omitted(isolated_session) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    _prefs(
        isolated_session,
        candidate,
        roles=[],
        locations=["York"],
        remote=None,
        salary_min=None,
    )
    job = _job(
        isolated_session,
        location="Flexible across our region",
        salary=None,
        description="Requirements: Python.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.location_score is None


def test_city_state_comparison_does_not_match_shared_city_token(isolated_session) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    _prefs(
        isolated_session,
        candidate,
        roles=[],
        locations=["York, NY"],
        remote=None,
        salary_min=None,
    )
    job = _job(
        isolated_session,
        location="New York, NY",
        salary=None,
        description="Requirements: Python.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.location_score == 0.0


@pytest.mark.parametrize(
    "salary",
    [
        "Estimated USD $150,000/year",
        "€150,000/year",
        "$150,000/day",
        "$150,000",
    ],
)
def test_unsafe_or_nonannual_salary_text_is_omitted(
    isolated_session,
    salary: str,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    _prefs(
        isolated_session,
        candidate,
        roles=[],
        locations=[],
        remote=None,
        salary_min=100_000,
    )
    job = _job(
        isolated_session,
        public_id=f"salary-{abs(hash(salary))}",
        location="",
        salary=salary,
        description="Requirements: Python.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.preference_score is None


def test_annual_salary_range_uses_maximum_against_candidate_minimum(
    isolated_session,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    _prefs(
        isolated_session,
        candidate,
        roles=[],
        locations=[],
        remote=None,
        salary_min=100_000,
    )
    job = _job(
        isolated_session,
        location="",
        salary="$80,000 - $120,000/year",
        description="Requirements: Python.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.preference_score == 100.0


@pytest.mark.parametrize(
    ("overall", "expected"),
    [
        (79.99, "consider"),
        (80.0, "apply"),
        (80.01, "apply"),
        (59.99, "skip"),
        (60.0, "consider"),
        (60.01, "consider"),
    ],
)
def test_full_intelligence_recommendation_boundaries(
    overall: float,
    expected: str,
) -> None:
    assert analysis_service._recommend(overall, "intelligence", True) == expected


@pytest.mark.parametrize(
    ("overall", "expected"),
    [
        (59.99, "skip"),
        (60.0, "consider"),
        (60.01, "consider"),
        (79.99, "consider"),
        (80.0, "consider"),
        (80.01, "consider"),
    ],
)
def test_provisional_recommendation_boundaries(
    overall: float,
    expected: str,
) -> None:
    assert analysis_service._recommend(overall, "description", True) == expected


def test_existing_duplicate_score_rows_are_collapsed_on_recalculation(
    isolated_session,
) -> None:
    candidate = _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")
    for score in (30.0, 40.0):
        isolated_session.add(
            MatchScoreRecord(
                job_id=job.id,
                candidate_id=candidate.id,
                overall_score=score,
                skill_score=score,
                experience_score=None,
                education_score=None,
                location_score=None,
                preference_score=None,
                matched_skills=[],
                partial_matches=[],
                missing_skills=["Python"],
                recommendation="skip",
                rationale="synthetic prior row",
            )
        )
    isolated_session.commit()

    score_job(isolated_session, job.public_id)

    assert isolated_session.query(MatchScoreRecord).count() == 1


def test_api_commit_failure_is_sanitized_and_rolls_back(
    isolated_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _candidate(db, skills=["Python"])
        _job(db, description="Requirements: Python.")

    secret_failure = "sqlite raw payload SELECT candidates.email"
    with caplog.at_level(logging.ERROR):
        with patch.object(Session, "commit", side_effect=RuntimeError(secret_failure)):
            response = client.post("/api/jobs/job-fit-001/score")

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to calculate fit score."}
    assert secret_failure not in caplog.text
    with SessionLocal() as db:
        assert db.query(MatchScoreRecord).count() == 0


def test_scoring_logs_do_not_include_score_or_recommendation(
    isolated_session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _candidate(isolated_session, skills=["Python"])
    job = _job(isolated_session, description="Requirements: Python.")

    with caplog.at_level(logging.INFO, logger="backend.services.analysis_service"):
        score_job(isolated_session, job.public_id)

    assert "overall=" not in caplog.text
    assert "recommendation=" not in caplog.text


def test_unsupported_intelligence_education_is_dropped_without_mutation(
    isolated_session,
) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(isolated_session, description="Requirements:\nPython")
    intelligence = _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=None,
        education=["Bachelor's in Computer Science"],
    )
    before = list(intelligence.education_requirements)

    result = score_job(isolated_session, job.public_id)

    assert result.education_score is None
    isolated_session.refresh(intelligence)
    assert intelligence.education_requirements == before


def test_description_fallback_does_not_infer_non_skill_requirements() -> None:
    grounded = extract_explicit_skills_from_description(
        "Senior contributor with 5 years of experience and a bachelor's degree. "
        "Sponsorship and work authorization are discussed during onboarding."
    )

    assert grounded.required == []
    assert grounded.preferred == []
    assert grounded.tech_stack == []
    assert grounded.years_experience is None
    assert grounded.education_requirements == []
    assert grounded.seniority is None


def test_react_does_not_match_react_native() -> None:
    grounded = extract_explicit_skills_from_description("Requirements: React Native.")

    assert "React" not in grounded.required + grounded.preferred + grounded.tech_stack


def test_exact_normal_weighting_and_component_rounding() -> None:
    assert (
        analysis_service._combine(
            {
                "skill": 100.0,
                "experience": 0.0,
                "education": 0.0,
                "location": 0.0,
                "preference": 0.0,
            }
        )
        == 55.0
    )
    assert (
        analysis_service._combine(
            {
                "skill": 1 / 3 * 100,
                "experience": None,
                "education": None,
                "location": None,
                "preference": None,
            }
        )
        == 33.3
    )


def test_empty_skill_groups_are_renormalized() -> None:
    required_only = analysis_service.GroundedRequirements(
        required=["Python"],
        preferred=[],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        source="intelligence",
    )
    preferred_only = analysis_service.GroundedRequirements(
        required=[],
        preferred=["Docker"],
        tech_stack=[],
        years_experience=None,
        education_requirements=[],
        seniority=None,
        source="intelligence",
    )

    required_match = analysis_service._match_skills(required_only, {"Python"})
    preferred_match = analysis_service._match_skills(preferred_only, {"Docker"})

    assert analysis_service._skill_component(required_match) == 100.0
    assert analysis_service._skill_component(preferred_match) == 100.0


def test_malformed_full_dates_are_not_coerced_to_month_start(isolated_session) -> None:
    _candidate(
        isolated_session,
        skills=["Python"],
        experience=[
            {
                "title": "Engineer",
                "company": "Fictional Dates",
                "start_date": "2025-02-31",
                "end_date": "2026-02-01",
                "highlights": [],
            }
        ],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        description="Requirements: Python and 1 year of work experience.",
    )
    _intelligence(
        isolated_session,
        job,
        required=["Python"],
        preferred=[],
        tech=[],
        years=1,
        education=[],
    )

    result = score_job(isolated_session, job.public_id, as_of=date(2026, 8, 20))

    assert result.experience_score is None


@pytest.mark.parametrize("present_label", ["Present", "Current"])
def test_present_dates_use_injected_as_of_date(
    isolated_session,
    present_label: str,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=[],
        experience=[
            {
                "title": "Engineer",
                "company": "Fictional Clock",
                "start_date": "2024-01-01",
                "end_date": present_label,
                "highlights": [],
            }
        ],
        education=[],
        projects=[],
        certifications=[],
    )

    years = analysis_service._experience_years(candidate, date(2025, 1, 1))

    assert years == pytest.approx(366 / 365.25)


def test_adjacent_and_same_employer_intervals_do_not_double_count(
    isolated_session,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=[],
        experience=[
            {
                "title": "Engineer I",
                "company": "Fictional Employer",
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                "highlights": [],
            },
            {
                "title": "Engineer II",
                "company": "Fictional Employer",
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "highlights": [],
            },
        ],
        education=[],
        projects=[],
        certifications=[],
    )

    years = analysis_service._experience_years(candidate, date(2026, 1, 1))

    assert years == pytest.approx(731 / 365.25)


def test_project_and_education_dates_do_not_count_as_employment(
    isolated_session,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=[],
        experience=[],
        projects=[
            {
                "name": "Synthetic Project",
                "description": "A dated project",
                "technologies": [],
                "start_date": "2010-01-01",
                "end_date": "2020-01-01",
            }
        ],
        education=[
            {
                "institution": "Fictional University",
                "degree": "Bachelor's",
                "field": "History",
                "start_date": "2010-01-01",
                "graduation_year": "2020",
            }
        ],
        certifications=[],
    )

    assert analysis_service._experience_years(candidate, date(2026, 1, 1)) is None


@pytest.mark.parametrize(
    ("job_location", "remote_preference", "expected"),
    [
        ("Remote", "remote", 100.0),
        ("Hybrid", "hybrid", 100.0),
        ("On-site", "onsite", 100.0),
        ("On-site", "remote", 0.0),
    ],
)
def test_explicit_work_modes_only(
    isolated_session,
    job_location: str,
    remote_preference: str,
    expected: float,
) -> None:
    candidate = _candidate(
        isolated_session,
        skills=["Python"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    _prefs(
        isolated_session,
        candidate,
        roles=[],
        locations=[],
        remote=remote_preference,
        salary_min=None,
    )
    job = _job(
        isolated_session,
        location=job_location,
        salary=None,
        description="Requirements: Python.",
    )

    result = score_job(isolated_session, job.public_id)

    assert result.location_score == expected


def test_grounded_custom_intelligence_skill_uses_exact_evidence_only(
    isolated_session,
) -> None:
    _candidate(
        isolated_session,
        skills=["Rust"],
        experience=[],
        education=[],
        projects=[],
        certifications=[],
    )
    job = _job(
        isolated_session,
        description="Requirements:\nRust",
        location="",
        salary=None,
    )
    _intelligence(
        isolated_session,
        job,
        required=["Rust", "Rustacean"],
        preferred=[],
        tech=[],
        years=None,
        education=[],
    )

    result = score_job(isolated_session, job.public_id)

    assert result.skill_score == 100.0
    assert result.matched_skills == ["Rust"]
    assert "Rustacean" not in result.missing_skills

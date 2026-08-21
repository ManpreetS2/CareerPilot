"""Deterministic Fit & Gap scoring tests. Isolated SQLite only; no providers."""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import patch

import pytest

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
    response = client.post("/api/jobs/missing-job/score")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_missing_candidate_returns_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db)
    response = client.post("/api/jobs/job-fit-001/score")
    assert response.status_code == 409
    assert "candidate profile" in response.json()["detail"].lower()


def test_missing_requirements_return_409_without_persistence(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _candidate(db)
        _job(db, description="Join a collaborative team working on interesting problems.")
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
        "Requirements:\nPython\nPreferred:\nDocker\nWe also mention Git in the team tools section."
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
        description="Python FastAPI Docker required preferred Bachelor's in Computer Science",
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
    job = _job(isolated_session, description="Python. Bachelor's in Computer Science")
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

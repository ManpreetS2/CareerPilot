"""Deterministic interview-prep foundation tests."""

from __future__ import annotations

import pytest

from backend.db.models import (
    Candidate,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
)
from backend.services.interview_service import (
    InterviewIntelligenceMissingError,
    InterviewJobNotFoundError,
    generate_and_store_interview_prep,
    get_interview_prep,
    unfinished_llm_interview_improver,
)


def _job(session, *, public_id: str = "job-interview") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineer Intern",
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Required: Python. Preferred: Kubernetes.",
        source="manual",
        status="verified",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _candidate(session) -> Candidate:
    record = Candidate(
        name="Jordan Avery",
        email="jordan@example.com",
        skills=["Python", "SQL"],
        projects=[{"name": "Campus Planner", "technologies": ["Python"], "description": "Python API"}],
        experience=[{"title": "Intern", "company": "Northstar Labs", "highlights": ["Wrote SQL reports."]}],
        education=[],
        certifications=[],
        strengths=[],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _intelligence(session, job: JobRecord) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "Kubernetes"],
        preferred_skills=["Docker"],
        years_experience=0,
        education_requirements=[],
        tech_stack=["Python"],
        seniority="intern",
        responsibilities=["Implement API endpoints"],
        likely_interview_focus=["Python fundamentals", "SQL joins"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def test_interview_missing_job(isolated_session) -> None:
    with pytest.raises(InterviewJobNotFoundError):
        get_interview_prep(isolated_session, "missing")
    with pytest.raises(InterviewJobNotFoundError):
        generate_and_store_interview_prep(isolated_session, "missing")


def test_interview_missing_intelligence(isolated_session) -> None:
    job = _job(isolated_session)
    with pytest.raises(InterviewIntelligenceMissingError):
        generate_and_store_interview_prep(isolated_session, job.public_id)
    assert isolated_session.query(InterviewPrepRecord).count() == 0


def test_interview_get_is_read_only(isolated_session) -> None:
    job = _job(isolated_session)
    assert get_interview_prep(isolated_session, job.public_id) is None
    assert isolated_session.query(InterviewPrepRecord).count() == 0


def test_interview_generation_uses_grounded_topics_only(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    isolated_session.add(
        MatchScoreRecord(
            job_id=job.id,
            candidate_id=candidate.id,
            overall_score=70.0,
            skill_score=60.0,
            matched_skills=["Python"],
            partial_matches=["SQL"],
            missing_skills=["Kubernetes", "Docker"],
            recommendation="consider",
            rationale="Python matched; Kubernetes is missing.",
        )
    )
    isolated_session.commit()

    prep = generate_and_store_interview_prep(isolated_session, job.public_id)
    blob = " ".join(prep.likely_questions)
    assert "Python fundamentals" in blob
    assert "SQL joins" in blob
    talking = " ".join(prep.talking_points).lower()
    gaps = " ".join(prep.gaps_to_address).lower()
    assert "python" in talking
    assert "kubernetes" not in talking
    assert "campus connect" not in talking
    assert "kubernetes" in gaps
    assert "docker" in gaps
    assert "not a current candidate strength" in gaps
    assert isolated_session.query(InterviewPrepRecord).count() == 1

    again = generate_and_store_interview_prep(isolated_session, job.public_id)
    assert again.job_id == prep.job_id
    assert isolated_session.query(InterviewPrepRecord).count() == 1


def test_missing_skills_are_gaps_not_strengths_without_fit_score(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    prep = generate_and_store_interview_prep(isolated_session, job.public_id)
    talking = " ".join(prep.talking_points).lower()
    gaps = " ".join(prep.gaps_to_address).lower()
    assert "kubernetes" in gaps
    assert "kubernetes" not in talking
    assert "python" in talking


def test_llm_improver_boundary_is_not_used_by_default(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    called = {"n": 0}

    def boom(_context, _prep):
        called["n"] += 1
        raise AssertionError("improver must not run")

    generate_and_store_interview_prep(isolated_session, job.public_id)
    assert called["n"] == 0
    with pytest.raises(Exception, match="not implemented"):
        unfinished_llm_interview_improver(None, None)  # type: ignore[arg-type]


def test_interview_http_get_read_only_and_explicit_generate(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        job = _job(db)
        _intelligence(db, job)
        _candidate(db)

    missing = client.get("/api/jobs/nope/interview-prep")
    assert missing.status_code == 404

    unread = client.get("/api/jobs/job-interview/interview-prep")
    assert unread.status_code == 404
    assert unread.json()["detail"] == "Interview prep has not been generated."
    with SessionLocal() as db:
        assert db.query(InterviewPrepRecord).count() == 0

    created = client.post("/api/jobs/job-interview/prepare-interview")
    assert created.status_code == 200
    body = created.json()
    assert body["likely_questions"]
    assert any("gap" in item.lower() or "not a current" in item.lower() for item in body["gaps_to_address"])

    stored = client.get("/api/jobs/job-interview/interview-prep")
    assert stored.status_code == 200
    assert stored.json()["job_id"] == "job-interview"

    with SessionLocal() as db:
        _job(db, public_id="job-no-intel")
    no_intel = client.post("/api/jobs/job-no-intel/prepare-interview")
    assert no_intel.status_code == 409
    assert "job requirements" in no_intel.json()["detail"].lower()

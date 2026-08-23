"""Application Materials Agent foundation tests.

The unfinished student-owned generator must fail closed: no persistence,
no provider calls, and no prompt/provider leakage.
"""

from __future__ import annotations

import inspect

import pytest

from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.services import application_service
from backend.services.application_materials_agent import (
    ApplicationMaterialsDraft,
    ApplicationMaterialsNotImplementedError,
    ApplicationMaterialsParseError,
    ApplicationMaterialsStructuredOutput,
    MaterialsGroundingReport,
    MissingCandidateError,
    MissingFitScoreError,
    MissingJobError,
    MissingJobIntelligenceError,
    build_application_materials_prompt,
    draft_to_application_package,
    generate_grounded_application_materials,
    ground_application_materials,
    load_application_materials_context,
    parse_application_materials_json,
)


def _job(session, *, public_id: str = "job-materials") -> JobRecord:
    record = JobRecord(
        public_id=public_id,
        title="Software Engineer Intern",
        company="Acme",
        url=f"https://example.com/jobs/{public_id}",
        description="Required: Python and SQL. Preferred: Docker.",
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
        projects=[
            {
                "name": "Campus Planner",
                "description": "Python API for campus events.",
                "technologies": ["Python", "FastAPI"],
                "url": None,
            }
        ],
        experience=[
            {
                "title": "Software Engineering Intern",
                "company": "Northstar Labs",
                "start_date": "2025-05",
                "end_date": "2025-08",
                "highlights": ["Reduced p95 latency on search endpoints by 28%."],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2027",
            }
        ],
        certifications=[],
        strengths=["Backend APIs"],
        evidence_links=[],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _intelligence(session, job: JobRecord) -> JobIntelligenceRecord:
    record = JobIntelligenceRecord(
        job_id=job.id,
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
        years_experience=0,
        education_requirements=["Bachelor's in CS"],
        tech_stack=["Python", "SQL"],
        seniority="intern",
        responsibilities=["Implement API endpoints with tests"],
        likely_interview_focus=["Python fundamentals", "SQL joins"],
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _score(session, job: JobRecord, candidate: Candidate) -> MatchScoreRecord:
    record = MatchScoreRecord(
        job_id=job.id,
        candidate_id=candidate.id,
        overall_score=82.0,
        skill_score=80.0,
        experience_score=70.0,
        education_score=100.0,
        location_score=None,
        preference_score=None,
        matched_skills=["Python", "SQL"],
        partial_matches=[],
        missing_skills=["Docker", "Kubernetes"],
        recommendation="apply",
        rationale="Matched Python and SQL from stored evidence.",
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _full_context(session):
    candidate = _candidate(session)
    job = _job(session)
    _intelligence(session, job)
    _score(session, job, candidate)
    session.add(
        TargetPreference(
            candidate_id=candidate.id,
            target_roles=["Software Engineer Intern"],
            preferred_locations=["Remote"],
        )
    )
    session.commit()
    return job, candidate


def test_missing_job_fails_sanitized(isolated_session) -> None:
    _candidate(isolated_session)
    with pytest.raises(MissingJobError, match="Job not found"):
        generate_grounded_application_materials(isolated_session, "missing-job")
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_candidate_fails_sanitized(isolated_session) -> None:
    _job(isolated_session)
    with pytest.raises(MissingCandidateError, match="candidate profile"):
        generate_grounded_application_materials(isolated_session, "job-materials")
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_job_intelligence_fails_sanitized(isolated_session) -> None:
    candidate = _candidate(isolated_session)
    job = _job(isolated_session)
    _score(isolated_session, job, candidate)
    with pytest.raises(MissingJobIntelligenceError, match="job requirements"):
        generate_grounded_application_materials(isolated_session, "job-materials")
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_missing_fit_score_fails_sanitized(isolated_session) -> None:
    _candidate(isolated_session)
    job = _job(isolated_session)
    _intelligence(isolated_session, job)
    with pytest.raises(MissingFitScoreError, match="fit score"):
        generate_grounded_application_materials(isolated_session, "job-materials")
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_unfinished_generator_fails_without_persistence_or_provider_leak(isolated_session) -> None:
    _full_context(isolated_session)
    called = {"n": 0}

    def boom(prompt: str, system_prompt: str | None = None) -> str:
        called["n"] += 1
        return f"SECRET_PROMPT_TOKEN {prompt} {system_prompt} gemini"

    before = isolated_session.query(ApplicationPackageRecord).count()
    with pytest.raises(ApplicationMaterialsNotImplementedError) as exc_info:
        generate_grounded_application_materials(
            isolated_session, "job-materials", generator=boom
        )
    message = str(exc_info.value).lower()
    assert called["n"] == 0
    assert isolated_session.query(ApplicationPackageRecord).count() == before
    assert "secret_prompt_token" not in message
    assert "gemini" not in message
    assert "prompt" not in message
    assert "not implemented" in message


def test_context_loading_uses_stored_grounded_records(isolated_session) -> None:
    job, candidate = _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, job.public_id)
    assert context.job.title == "Software Engineer Intern"
    assert context.candidate.name == candidate.name
    assert context.intelligence.required_skills == ["Python", "SQL"]
    assert context.fit_score.missing_skills == ["Docker", "Kubernetes"]
    assert context.preferences is not None
    assert context.preferences.target_roles == ["Software Engineer Intern"]
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_no_candidate_claim_invention(isolated_session) -> None:
    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials")
    invented = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Led production Kubernetes clusters and improved latency by 40%."],
        cover_letter_draft="I have deep Kubernetes experience at Globex.",
        recruiter_message="I used Kubernetes in production.",
        source_traceability_notes=["Invented Kubernetes claim"],
    )
    report = ground_application_materials(invented, context)
    assert report.grounded is False
    assert report.invented_candidate_claims >= 1
    assert report.numeric_literals_rejected >= 1
    assert "missing_skill_as_strength" in report.rejected_categories

    grounded = ApplicationMaterialsStructuredOutput(
        tailored_bullets=["Built Python APIs at Northstar Labs and reduced p95 latency by 28%."],
        cover_letter_draft="I am applying using stored Python and SQL evidence.",
        recruiter_message="Happy to discuss Python coursework.",
        source_traceability_notes=["Python <- candidate skills"],
    )
    ok = ground_application_materials(grounded, context)
    assert ok.invented_candidate_claims == 0
    assert ok.numeric_literals_rejected == 0


def test_prompt_json_and_persistence_conversion_do_not_write(isolated_session) -> None:
    _full_context(isolated_session)
    context = load_application_materials_context(isolated_session, "job-materials")
    system_prompt, user_prompt = build_application_materials_prompt(context)
    assert "Never invent" in system_prompt
    assert "Python" in user_prompt
    parsed = parse_application_materials_json(
        '{"tailored_bullets":["Used Python"],"cover_letter_draft":"Hello",'
        '"recruiter_message":"Hi","source_traceability_notes":["Python <- skills"]}'
    )
    assert parsed.tailored_bullets == ["Used Python"]
    with pytest.raises(ApplicationMaterialsParseError):
        parse_application_materials_json("not-json")
    package = draft_to_application_package(
        ApplicationMaterialsDraft(
            job_id="job-materials",
            tailored_bullets=["Used Python"],
            cover_letter_draft="Hello",
            recruiter_message="Hi",
            source_traceability_notes=["Python <- skills"],
            grounding=MaterialsGroundingReport(),
        )
    )
    assert package.job_id == "job-materials"
    assert package.approval_status == "pending_review"
    assert isolated_session.query(ApplicationPackageRecord).count() == 0


def test_legacy_placeholder_is_not_wired_to_new_service() -> None:
    source = inspect.getsource(application_service.get_or_generate_application_package)
    mock_source = inspect.getsource(application_service._mock_materials)
    assert "generate_grounded_application_materials(" not in source
    assert "placeholder" in mock_source.lower()
    assert "next replacement target" in mock_source.lower()


def test_production_generate_materials_still_uses_placeholder(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        _job(db, public_id="manual-abc123")
    response = client.post("/api/jobs/manual-abc123/generate-materials")
    assert response.status_code == 200
    body = response.json()
    assert "Placeholder bullet" in " ".join(body["source_traceability_notes"])
    assert body["approval_status"] == "pending_review"

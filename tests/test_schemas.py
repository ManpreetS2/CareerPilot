"""Pydantic schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.schemas import (
    ApplicationPackage,
    CandidateProfile,
    Experience,
    Job,
    MatchScore,
    Project,
    ScoutJobsResponse,
    TargetPreferences,
)


def test_candidate_profile_validates() -> None:
    profile = CandidateProfile(
        name="Alex Rivera",
        skills=["Python"],
        projects=[Project(name="Demo")],
        experience=[Experience(title="Intern", company="Acme")],
    )
    assert profile.name == "Alex Rivera"
    assert profile.projects[0].name == "Demo"


def test_candidate_profile_requires_name() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile()  # type: ignore[call-arg]


def test_job_and_preferences_validate() -> None:
    job = Job(
        title="Intern",
        company="Acme",
        url="https://example.com/job",
        description="Build APIs",
        source="mock",
    )
    prefs = TargetPreferences(target_roles=["Software Engineer Intern"], salary_min=100000)
    assert job.status == "discovered"
    assert prefs.salary_min == 100000


def test_match_score_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        MatchScore(
            job_id="job-001",
            overall_score=140,
            recommendation="apply",
            rationale="too high",
        )


def test_application_package_validates() -> None:
    package = ApplicationPackage(
        job_id="job-001",
        tailored_bullets=["Shipped an API"],
        approval_status="pending_review",
    )
    assert package.job_id == "job-001"


def test_scout_jobs_response_default_note_is_not_a_mock_stub() -> None:
    payload = ScoutJobsResponse(jobs=[])
    assert "not implemented" not in payload.note.lower()
    assert "day 1 mock" not in payload.note.lower()

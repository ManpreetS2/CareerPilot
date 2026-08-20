"""Candidate-facing Day 1 mocks. No real resume parsing yet."""

from __future__ import annotations

from backend.schemas.schemas import (
    CandidateProfile,
    Education,
    Experience,
    Project,
    TargetPreferences,
)


def mock_candidate_profile() -> CandidateProfile:
    """Return a realistic mock profile used by /api/parse-resume."""
    return CandidateProfile(
        id="cand-001",
        name="Alex Rivera",
        email="alex.rivera@example.com",
        phone="+1-555-0142",
        skills=[
            "Python",
            "FastAPI",
            "SQL",
            "PostgreSQL",
            "React",
            "Docker",
            "AWS",
        ],
        projects=[
            Project(
                name="Campus Connect",
                description="Student-org discovery platform with search and event RSVP.",
                technologies=["Python", "FastAPI", "React"],
                url="https://github.com/example/campus-connect",
            )
        ],
        experience=[
            Experience(
                title="Software Engineering Intern",
                company="Northstar Labs",
                start_date="2025-05",
                end_date="2025-08",
                highlights=[
                    "Shipped an internal API used by 4 product teams.",
                    "Reduced p95 latency on search endpoints by 28%.",
                ],
            )
        ],
        education=[
            Education(
                institution="State University",
                degree="B.S.",
                field="Computer Science",
                graduation_year="2027",
            )
        ],
        certifications=["AWS Cloud Practitioner"],
        strengths=["Backend APIs", "Clear written communication", "Fast iteration"],
        evidence_links=["https://github.com/example/campus-connect"],
    )


def mock_preferences() -> TargetPreferences:
    return TargetPreferences(
        target_roles=["Software Engineer Intern", "Backend Engineer Intern"],
        preferred_locations=["San Francisco, CA", "Remote"],
        remote_preference="hybrid_or_remote",
        salary_min=35,
        work_authorization="US Citizen",
        sponsorship_required=False,
        constraints=["Summer 2027 internship preferred"],
    )


def parse_resume_placeholder(filename: str | None = None) -> CandidateProfile:
    """Day 1: ignore file contents and return mock data."""
    _ = filename
    return mock_candidate_profile()

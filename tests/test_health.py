"""API smoke tests that do not depend on live LLM calls."""

from __future__ import annotations

from unittest.mock import patch

from backend.db.models import Candidate
from backend.schemas.schemas import CandidateProfile
from tests.pdf_fixtures import SAMPLE_RESUME_TEXT, build_simple_text_pdf


def test_health_returns_success(isolated_client) -> None:
    client, _ = isolated_client
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_root_returns_service_info(isolated_client) -> None:
    client, _ = isolated_client
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "CareerPilot AI"


def test_parse_resume_matches_candidate_profile(isolated_client) -> None:
    client, SessionLocal = isolated_client
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)
    payload = {
        "name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "phone": "+1-555-0142",
        "skills": ["Python", "FastAPI"],
        "projects": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "strengths": [],
        "evidence_links": [],
    }

    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        return_value=payload,
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    candidate = CandidateProfile.model_validate(body["candidate"])
    assert candidate.name == "Alex Rivera"
    assert isinstance(candidate.skills, list)
    assert body.get("preferences") is None
    with SessionLocal() as db:
        assert db.query(Candidate).count() == 1

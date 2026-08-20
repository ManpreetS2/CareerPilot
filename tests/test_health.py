"""API health and mock route tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.schemas import CandidateProfile

client = TestClient(app)


def test_health_returns_success() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_root_returns_service_info() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "CareerPilot AI"


def test_parse_resume_matches_candidate_profile() -> None:
    files = {"file": ("resume.pdf", b"%PDF-mock-resume", "application/pdf")}
    response = client.post("/api/parse-resume", files=files)
    assert response.status_code == 200
    payload = response.json()
    candidate = CandidateProfile.model_validate(payload["candidate"])
    assert candidate.name
    assert isinstance(candidate.skills, list)

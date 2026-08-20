"""Tests for Candidate Profile Agent extraction, grounding, and API wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base, engine
from backend.db.models import Candidate
from backend.main import app
from backend.schemas.schemas import CandidateProfile
from backend.services.candidate_profile_agent import (
    MAX_UPLOAD_BYTES,
    OCRUnavailableError,
    ProfileExtractionError,
    build_candidate_profile_from_upload,
    extract_candidate_profile_with_llm,
    extract_resume_text,
    persist_candidate_profile,
    validate_and_ground_profile,
    validate_pdf_upload,
)
from tests.pdf_fixtures import (
    SAMPLE_RESUME_TEXT,
    build_image_only_pdf,
    build_simple_text_pdf,
    write_simple_text_pdf,
)

client = TestClient(app)


def _grounded_llm_payload() -> dict:
    return {
        "name": "Alex Rivera",
        "email": "alex.rivera@example.com",
        "phone": "+1-555-0142",
        "skills": ["Python", "FastAPI", "SQL"],
        "projects": [
            {
                "name": "Campus Connect",
                "description": "Student-org discovery platform with search and event RSVP.",
                "technologies": ["Python", "FastAPI", "React"],
                "url": "https://github.com/example/campus-connect",
            }
        ],
        "experience": [
            {
                "title": "Software Engineering Intern",
                "company": "Northstar Labs",
                "start_date": "2025-05",
                "end_date": "2025-08",
                "highlights": ["Shipped an internal API used by 4 product teams."],
            }
        ],
        "education": [
            {
                "institution": "State University",
                "degree": "B.S.",
                "field": "Computer Science",
                "graduation_year": "2027",
            }
        ],
        "certifications": ["AWS Cloud Practitioner"],
        "strengths": ["Backend APIs"],
        "evidence_links": ["https://github.com/example/campus-connect"],
    }


def test_text_pdf_extraction_uses_pdfplumber(tmp_path: Path) -> None:
    pdf_path = write_simple_text_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_TEXT)
    result = extract_resume_text(pdf_path)
    assert result.method == "pdfplumber"
    assert "Alex Rivera" in result.text
    assert "Python" in result.text


def test_near_empty_extraction_triggers_ocr_path(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(build_image_only_pdf())

    with (
        patch(
            "backend.services.candidate_profile_agent.extract_with_pdfplumber",
            return_value="",
        ),
        patch(
            "backend.services.candidate_profile_agent.extract_with_ocr",
            return_value=SAMPLE_RESUME_TEXT,
        ) as ocr_mock,
    ):
        result = extract_resume_text(pdf_path)

    assert result.method == "ocr"
    assert "Alex Rivera" in result.text
    ocr_mock.assert_called_once()


def test_ocr_unavailable_error_is_clear(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(build_image_only_pdf())

    with (
        patch(
            "backend.services.candidate_profile_agent.extract_with_pdfplumber",
            return_value="",
        ),
        patch(
            "backend.services.candidate_profile_agent.is_tesseract_available",
            return_value=False,
        ),
    ):
        with pytest.raises(OCRUnavailableError, match="Tesseract"):
            extract_resume_text(pdf_path)


def test_invalid_non_pdf_upload_rejected() -> None:
    with pytest.raises(Exception, match="PDF"):
        validate_pdf_upload("resume.txt", b"not a pdf")


def test_oversized_upload_rejected() -> None:
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 10)
    with pytest.raises(Exception, match="upload limit"):
        validate_pdf_upload("resume.pdf", content)


def test_valid_structured_candidate_profile_parses() -> None:
    profile = CandidateProfile.model_validate(_grounded_llm_payload())
    assert profile.name == "Alex Rivera"
    assert "Python" in profile.skills


def test_malformed_llm_json_retries_then_fails() -> None:
    calls = {"n": 0}

    def bad_generate(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        return "not-json"

    with pytest.raises(ProfileExtractionError):
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=bad_generate)
    assert calls["n"] == 2


def test_malformed_llm_json_recovers_on_retry() -> None:
    responses = ["not-json", json.dumps(_grounded_llm_payload())]

    def flaky(_prompt: str, _system: str | None) -> str:
        return responses.pop(0)

    payload = extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=flaky)
    assert payload["name"] == "Alex Rivera"


def test_hallucinated_skill_is_removed() -> None:
    raw = _grounded_llm_payload()
    raw["skills"] = ["Python", "Quantum Teleportation"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert "Python" in profile.skills
    assert "Quantum Teleportation" not in profile.skills
    assert any("skill" in item.lower() for item in report.rejected)


def test_invented_project_is_removed() -> None:
    raw = _grounded_llm_payload()
    raw["projects"].append(
        {
            "name": "Interdimensional Mapper",
            "description": "Mapped alternate universes with 99% accuracy.",
            "technologies": ["Rust"],
            "url": None,
        }
    )
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert all(p.name != "Interdimensional Mapper" for p in profile.projects)
    assert any("project" in item.lower() for item in report.rejected)


def test_unsupported_certification_rejected() -> None:
    raw = _grounded_llm_payload()
    raw["certifications"] = ["AWS Cloud Practitioner", "Board Certified Time Traveler"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert profile.certifications == ["AWS Cloud Practitioner"]
    assert any("certification" in item.lower() for item in report.rejected)


def test_invented_metric_and_date_defense() -> None:
    raw = _grounded_llm_payload()
    raw["experience"][0]["highlights"] = [
        "Shipped an internal API used by 4 product teams.",
        "Increased revenue by 400% overnight.",
    ]
    raw["experience"][0]["start_date"] = "1999-01"
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert profile.experience[0].start_date is None
    assert all("400%" not in h for h in profile.experience[0].highlights)
    assert any("highlight" in item.lower() or "start_date" in item.lower() for item in report.rejected)


def test_grounded_real_fields_survive_validation() -> None:
    profile, report = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
    assert profile.name == "Alex Rivera"
    assert "Python" in profile.skills
    assert profile.projects[0].name == "Campus Connect"
    assert profile.experience[0].company == "Northstar Labs"
    assert profile.education[0].institution == "State University"
    assert "AWS Cloud Practitioner" in profile.certifications
    assert report.rejected == []


def test_candidate_persistence_works() -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        profile, _ = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
        stored = persist_candidate_profile(profile, db)
        assert stored.id and stored.id.startswith("cand-")
        row = db.query(Candidate).order_by(Candidate.id.desc()).first()
        assert row is not None
        assert row.name == "Alex Rivera"
        assert "Python" in row.skills
    finally:
        db.close()


def test_parse_resume_endpoint_returns_real_candidate_profile(tmp_path: Path) -> None:
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)

    def fake_generate(_prompt: str, _system: str | None) -> str:
        return json.dumps(_grounded_llm_payload())

    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        side_effect=lambda resume_text, llm=None, generate_fn=None: _grounded_llm_payload(),
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    candidate = CandidateProfile.model_validate(payload["candidate"])
    assert candidate.name == "Alex Rivera"
    assert candidate.id and candidate.id.startswith("cand-")
    assert payload.get("preferences") is None
    assert "Grounded" in payload.get("note", "")


def test_parse_resume_rejects_non_pdf() -> None:
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_build_from_upload_end_to_end(tmp_path: Path) -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = TestingSession()
    try:
        content = build_simple_text_pdf(SAMPLE_RESUME_TEXT)
        stored, extraction, report = build_candidate_profile_from_upload(
            "alex.pdf",
            content,
            db=db,
            generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
        )
        assert extraction.method == "pdfplumber"
        assert stored.name == "Alex Rivera"
        assert report.rejected == []
    finally:
        db.close()

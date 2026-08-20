"""Tests for Candidate Profile Agent extraction, grounding, and API wiring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base, engine
from backend.db.models import Candidate
from backend.main import app
from backend.schemas.schemas import CandidateProfile, TargetPreferences
from backend.services.candidate_profile_agent import (
    MAX_UPLOAD_BYTES,
    OCRUnavailableError,
    ProfileExtractionError,
    ProfileGroundingError,
    ResumeExtractionError,
    build_candidate_profile_from_upload,
    claim_supported,
    extract_candidate_profile_with_llm,
    extract_resume_text,
    extract_with_pdfplumber,
    persist_candidate_profile,
    validate_and_ground_profile,
    validate_pdf_upload,
)
from backend.services.candidate_service import mock_preferences
from backend.services.llm_client import LLMProviderError
from tests.pdf_fixtures import (
    SAMPLE_RESUME_TEXT,
    build_image_only_pdf,
    build_multipage_text_pdf,
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


def _schema_invalid_payload() -> dict:
    return {
        "name": "Alex Rivera",
        "skills": "not-a-list",
        "projects": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "strengths": [],
        "evidence_links": [],
    }


def test_text_pdf_extraction_uses_pdfplumber(tmp_path: Path) -> None:
    pdf_path = write_simple_text_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_TEXT)
    result = extract_resume_text(pdf_path)
    assert result.method == "pdfplumber"
    assert "Alex Rivera" in result.text
    assert "Python" in result.text


def test_multipage_pdf_extraction_concatenates_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "multi.pdf"
    pdf_path.write_bytes(
        build_multipage_text_pdf(
            [
                "Alex Rivera\nSkills: Python",
                "Experience\nSoftware Engineering Intern, Northstar Labs",
            ]
        )
    )
    result = extract_resume_text(pdf_path)
    assert result.method == "pdfplumber"
    assert "Alex Rivera" in result.text
    assert "Northstar Labs" in result.text


def test_page_extract_text_none_is_tolerated(tmp_path: Path) -> None:
    pdf_path = write_simple_text_pdf(tmp_path / "resume.pdf", SAMPLE_RESUME_TEXT)
    page = MagicMock()
    page.extract_text.return_value = None
    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False

    with patch("pdfplumber.open", return_value=pdf):
        text = extract_with_pdfplumber(pdf_path)
    assert text == ""


def test_corrupt_pdf_raises_resume_extraction_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "corrupt.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%not-a-real-pdf")
    with pytest.raises(ResumeExtractionError, match="could not be read"):
        extract_resume_text(pdf_path)


def test_no_usable_text_raises_clear_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(build_image_only_pdf())
    with (
        patch(
            "backend.services.candidate_profile_agent.extract_with_pdfplumber",
            return_value="",
        ),
        patch(
            "backend.services.candidate_profile_agent.is_tesseract_available",
            return_value=True,
        ),
        patch(
            "backend.services.candidate_profile_agent.extract_with_ocr",
            side_effect=ResumeExtractionError("No readable resume text was found in this PDF."),
        ),
    ):
        with pytest.raises(ResumeExtractionError, match="No readable resume text"):
            extract_resume_text(pdf_path)


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
    with pytest.raises(Exception, match="valid PDF"):
        validate_pdf_upload("resume.txt", b"not a pdf")


def test_invalid_content_type_rejected() -> None:
    with pytest.raises(Exception, match="valid PDF"):
        validate_pdf_upload(
            "resume.pdf",
            b"%PDF-1.4",
            content_type="text/plain",
        )


def test_oversized_upload_rejected() -> None:
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 10)
    with pytest.raises(Exception, match="10 MiB"):
        validate_pdf_upload("resume.pdf", content)


def test_valid_structured_candidate_profile_parses() -> None:
    profile = CandidateProfile.model_validate(_grounded_llm_payload())
    assert profile.name == "Alex Rivera"
    assert "Python" in profile.skills


def test_ordinary_json_extracts() -> None:
    payload = extract_candidate_profile_with_llm(
        SAMPLE_RESUME_TEXT,
        generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
    )
    assert payload["name"] == "Alex Rivera"


def test_fully_fenced_json_extracts() -> None:
    fenced = "```json\n" + json.dumps(_grounded_llm_payload()) + "\n```"
    payload = extract_candidate_profile_with_llm(
        SAMPLE_RESUME_TEXT,
        generate_fn=lambda _p, _s: fenced,
    )
    assert payload["name"] == "Alex Rivera"


def test_empty_output_retries_then_fails() -> None:
    calls = {"n": 0}

    def empty_generate(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        return "   "

    with pytest.raises(ProfileExtractionError) as exc_info:
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=empty_generate)
    assert calls["n"] == 2
    assert "ValidationError" not in str(exc_info.value)
    assert "   " not in str(exc_info.value)


def test_malformed_llm_json_retries_then_fails() -> None:
    calls = {"n": 0}

    def bad_generate(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        return "not-json"

    with pytest.raises(ProfileExtractionError) as exc_info:
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=bad_generate)
    assert calls["n"] == 2
    assert "not-json" not in str(exc_info.value)


def test_malformed_llm_json_recovers_on_retry() -> None:
    responses = ["not-json", json.dumps(_grounded_llm_payload())]

    def flaky(_prompt: str, _system: str | None) -> str:
        return responses.pop(0)

    payload = extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=flaky)
    assert payload["name"] == "Alex Rivera"


def test_schema_invalid_json_retries_then_fails() -> None:
    calls = {"n": 0}

    def bad_schema(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        return json.dumps(_schema_invalid_payload())

    with pytest.raises(ProfileExtractionError) as exc_info:
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=bad_schema)
    assert calls["n"] == 2
    assert "ValidationError" not in str(exc_info.value)
    assert "not-a-list" not in str(exc_info.value)


def test_schema_invalid_recovers_on_retry() -> None:
    responses = [json.dumps(_schema_invalid_payload()), json.dumps(_grounded_llm_payload())]

    def flaky(_prompt: str, _system: str | None) -> str:
        return responses.pop(0)

    payload = extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=flaky)
    assert payload["name"] == "Alex Rivera"


def test_non_object_json_retries_then_fails() -> None:
    calls = {"n": 0}

    def array_json(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        return "[]"

    with pytest.raises(ProfileExtractionError):
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=array_json)
    assert calls["n"] == 2


def test_provider_error_does_not_enter_structured_retry() -> None:
    calls = {"n": 0}

    def boom(_prompt: str, _system: str | None) -> str:
        calls["n"] += 1
        raise LLMProviderError("Gemini provider request failed.")

    with pytest.raises(ProfileExtractionError):
        extract_candidate_profile_with_llm(SAMPLE_RESUME_TEXT, generate_fn=boom)
    assert calls["n"] == 1


def test_hallucinated_skill_is_removed() -> None:
    raw = _grounded_llm_payload()
    raw["skills"] = ["Python", "Quantum Teleportation"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert "Python" in profile.skills
    assert "Quantum Teleportation" not in profile.skills
    assert report.as_counts().get("removed_skills") == 1
    assert "Quantum Teleportation" not in str(report.as_counts())
    assert "Quantum Teleportation" not in "".join(report.rejected)


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
    assert report.as_counts().get("removed_projects") == 1
    assert "Interdimensional Mapper" not in "".join(report.rejected)


def test_unsupported_project_technology_removed() -> None:
    raw = _grounded_llm_payload()
    raw["projects"][0]["technologies"] = ["Python", "BrainWaveDB"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert profile.projects[0].technologies == ["Python"]
    assert report.as_counts().get("removed_project_technologies") == 1
    assert "BrainWaveDB" not in "".join(report.rejected)


def test_unsupported_experience_company_title_removed() -> None:
    raw = _grounded_llm_payload()
    raw["experience"].append(
        {
            "title": "Chief Teleporter",
            "company": "Acme Warp Drive",
            "start_date": "2024-01",
            "end_date": "2024-06",
            "highlights": ["Invented teleportation."],
        }
    )
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert all(item.company != "Acme Warp Drive" for item in profile.experience)
    assert report.as_counts().get("removed_experience") == 1
    assert "Acme Warp Drive" not in "".join(report.rejected)
    assert "Chief Teleporter" not in "".join(report.rejected)


def test_unsupported_certification_rejected() -> None:
    raw = _grounded_llm_payload()
    raw["certifications"] = ["AWS Cloud Practitioner", "Board Certified Time Traveler"]
    profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert profile.certifications == ["AWS Cloud Practitioner"]
    assert report.as_counts().get("removed_certifications") == 1
    assert "Board Certified Time Traveler" not in "".join(report.rejected)


def test_rewritten_metric_rejected() -> None:
    source = (
        "Alex Rivera\nSoftware Engineering Intern, Northstar Labs\n"
        "Reduced latency by 20% on search endpoints."
    )
    claim = "Reduced latency by 40% on search endpoints."
    assert claim_supported(claim, source) is False

    raw = _grounded_llm_payload()
    raw["experience"][0]["highlights"] = [claim]
    profile, report = validate_and_ground_profile(raw, source + "\n" + SAMPLE_RESUME_TEXT)
    # Highlight must not survive when only the metric was rewritten.
    assert all("40%" not in h for h in profile.experience[0].highlights)
    assert report.as_counts().get("removed_highlights", 0) >= 1


def test_plain_count_cannot_support_invented_currency() -> None:
    source = "Saved 500 engineering hours."
    assert claim_supported("Saved $500 engineering hours.", source) is False


def test_plain_number_cannot_support_invented_percentage() -> None:
    source = "Improved throughput by 20 points."
    assert claim_supported("Improved throughput by 20%.", source) is False


def test_percentage_cannot_silently_become_plain_count() -> None:
    source = "Improved throughput by 20%."
    assert claim_supported("Improved throughput by 20 points.", source) is False


def test_currency_cannot_silently_become_plain_count() -> None:
    source = "Processed $100 requests."
    assert claim_supported("Processed 100 requests.", source) is False


def test_currency_comma_formatting_matches_safely() -> None:
    source = "Reduced costs by $100,000 annually."
    assert claim_supported("Reduced costs by $100000 annually.", source) is True


def test_exact_supported_percentage_accepted() -> None:
    source = "Improved throughput by 20% on checkout."
    assert claim_supported("Improved throughput by 20% on checkout.", source) is True


def test_rewritten_percentage_value_rejected() -> None:
    source = "Improved throughput by 20% on checkout."
    assert claim_supported("Improved throughput by 40% on checkout.", source) is False


def test_nearby_fabricated_date_rejected() -> None:
    source = (
        "Alex Rivera\nSoftware Engineering Intern, Northstar Labs\n"
        "2025-05 – 2025-08\nShipped an internal API used by 4 product teams."
    )
    assert claim_supported("2025-06", source) is False

    raw = _grounded_llm_payload()
    raw["experience"][0]["start_date"] = "2025-06"
    profile, report = validate_and_ground_profile(raw, source)
    assert profile.experience[0].start_date is None
    assert report.as_counts().get("removed_experience_dates") == 1


def test_unit_mismatch_grounding_report_categories_only(caplog: pytest.LogCaptureFixture) -> None:
    invented_metric = "Saved $500 engineering hours."
    source = (
        "Alex Rivera\nalex.rivera@example.com\n+1-555-0142\n"
        "Software Engineering Intern, Northstar Labs\n"
        "Saved 500 engineering hours.\n"
        "Skills: Python\n"
        "Campus Connect\nState University\nAWS Cloud Practitioner"
    )
    raw = _grounded_llm_payload()
    raw["experience"][0]["highlights"] = [invented_metric]
    with caplog.at_level(logging.INFO, logger="backend.services.candidate_profile_agent"):
        profile, report = validate_and_ground_profile(raw, source)
    assert all("$500" not in h for h in profile.experience[0].highlights)
    assert report.as_counts().get("removed_highlights", 0) >= 1
    blob = json.dumps(report.as_counts()) + "".join(report.rejected) + caplog.text
    assert "$500" not in blob
    assert invented_metric not in blob
    assert all(key.startswith("removed_") for key in report.as_counts())


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
    assert report.as_counts().get("removed_highlights") == 1
    assert report.as_counts().get("removed_experience_dates") == 1


def test_short_skill_boundaries() -> None:
    source = "Skills: Python, Go, C++, C#, C, R"
    assert claim_supported("Go", source) is True
    assert claim_supported("C++", source) is True
    assert claim_supported("C#", source) is True
    assert claim_supported("C", source) is True
    assert claim_supported("R", source) is True
    assert claim_supported("Go", "Google Cloud experience") is False


def test_grounding_report_categories_counts_only(caplog: pytest.LogCaptureFixture) -> None:
    invented = "Quantum Teleportation Framework X9"
    raw = _grounded_llm_payload()
    raw["skills"] = ["Python", invented]
    with caplog.at_level(logging.INFO, logger="backend.services.candidate_profile_agent"):
        profile, report = validate_and_ground_profile(raw, SAMPLE_RESUME_TEXT)
    assert invented not in profile.skills
    assert report.total_rejected == 1
    assert report.as_counts() == {"removed_skills": 1}
    serialized = json.dumps(report.as_counts()) + "".join(report.rejected) + str(report.as_counts())
    assert invented not in serialized
    assert invented not in caplog.text
    assert "removed_skills" in caplog.text or "rejected_total=1" in caplog.text


def test_grounded_real_fields_survive_validation() -> None:
    profile, report = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
    assert profile.name == "Alex Rivera"
    assert "Python" in profile.skills
    assert profile.projects[0].name == "Campus Connect"
    assert profile.experience[0].company == "Northstar Labs"
    assert profile.education[0].institution == "State University"
    assert "AWS Cloud Practitioner" in profile.certifications
    assert report.total_rejected == 0
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


def test_failed_extraction_creates_no_candidate_row() -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    before = db.query(Candidate).count()
    try:
        with pytest.raises(ProfileExtractionError):
            build_candidate_profile_from_upload(
                "alex.pdf",
                build_simple_text_pdf(SAMPLE_RESUME_TEXT),
                db=db,
                generate_fn=lambda _p, _s: "not-json",
            )
        assert db.query(Candidate).count() == before
    finally:
        db.close()


def test_failed_grounding_creates_no_candidate_row() -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    before = db.query(Candidate).count()
    bad = _grounded_llm_payload()
    bad["name"] = "Someone Not On Resume"
    try:
        with pytest.raises(ProfileGroundingError):
            build_candidate_profile_from_upload(
                "alex.pdf",
                build_simple_text_pdf(SAMPLE_RESUME_TEXT),
                db=db,
                generate_fn=lambda _p, _s: json.dumps(bad),
            )
        assert db.query(Candidate).count() == before
    finally:
        db.close()


def test_persistence_rollback_on_failure() -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    before = db.query(Candidate).count()
    profile, _ = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
    try:
        with patch.object(db, "commit", side_effect=RuntimeError("db down")):
            with pytest.raises(RuntimeError, match="db down"):
                persist_candidate_profile(profile, db)
        assert db.query(Candidate).count() == before
    finally:
        db.close()


def test_grounded_profile_persists_with_stored_id() -> None:
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        stored, _extraction, report = build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=db,
            generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
        )
        assert stored.id and stored.id.startswith("cand-")
        assert report.total_rejected == 0
        row = db.query(Candidate).filter(Candidate.name == "Alex Rivera").order_by(Candidate.id.desc()).first()
        assert row is not None
    finally:
        db.close()


def test_parse_resume_endpoint_returns_real_candidate_profile(tmp_path: Path) -> None:
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)

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


def test_provider_server_error_maps_to_actionable_502() -> None:
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)

    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        side_effect=ProfileExtractionError(
            "The AI extraction service could not process this resume. Please try again."
        ),
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 502
    assert "AI extraction service" in response.json()["detail"]


def test_oversized_upload_returns_413() -> None:
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 1)
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", content, "application/pdf")},
    )
    assert response.status_code == 413
    assert "10 MiB" in response.json()["detail"]


def test_preferences_accept_annual_salary() -> None:
    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Software Engineer"],
            "preferred_locations": [],
            "salary_min": 100000,
            "work_authorization": None,
            "sponsorship_required": None,
            "remote_preference": None,
            "constraints": [],
        },
    )
    assert response.status_code == 201
    assert response.json()["salary_min"] == 100000


def test_preferences_reject_hourly_sized_salary() -> None:
    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Software Engineer"],
            "preferred_locations": [],
            "salary_min": 35,
            "work_authorization": None,
            "sponsorship_required": None,
            "remote_preference": None,
            "constraints": [],
        },
    )
    assert response.status_code == 422


def test_mock_preferences_survives_annual_salary_validator() -> None:
    prefs = mock_preferences()
    assert isinstance(prefs, TargetPreferences)
    assert prefs.salary_min is None or prefs.salary_min >= 10_000


def test_parse_resume_never_returns_mock_alex_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the Day 1 canned mock path is unreachable from the production route."""
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)

    def unexpected_mock(*_args, **_kwargs):
        raise AssertionError("mock_candidate_profile must not be used")

    monkeypatch.setattr(
        "backend.services.candidate_service.mock_candidate_profile",
        unexpected_mock,
    )
    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        return_value=_grounded_llm_payload(),
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 200
    assert response.json()["preferences"] is None


def test_parse_resume_closes_upload_when_read_fails() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from backend.api.routes import candidate as candidate_routes

    upload = AsyncMock()
    upload.filename = "resume.pdf"
    upload.content_type = "application/pdf"
    upload.read = AsyncMock(side_effect=RuntimeError("read failed"))
    upload.close = AsyncMock()

    with pytest.raises(RuntimeError, match="read failed"):
        asyncio.run(candidate_routes.parse_resume(file=upload, db=MagicMock()))

    upload.close.assert_awaited_once()


def test_parse_resume_note_uses_total_rejected() -> None:
    pdf_bytes = build_simple_text_pdf(SAMPLE_RESUME_TEXT)
    raw = _grounded_llm_payload()
    raw["skills"] = ["Python", "InventedSkillXYZ"]

    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        return_value=raw,
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    note = response.json()["note"]
    assert "Rejected unsupported claims: 1." in note
    assert "InventedSkillXYZ" not in note

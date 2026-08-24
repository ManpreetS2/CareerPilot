"""Tests for Candidate Profile Agent extraction, grounding, and API wiring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from backend.db.models import Candidate, TargetPreference
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
        validate_pdf_upload("resume.txt", b"not a pdf", content_type="application/pdf")


def test_invalid_content_type_rejected() -> None:
    with pytest.raises(Exception, match="valid PDF"):
        validate_pdf_upload(
            "resume.pdf",
            b"%PDF-1.4",
            content_type="text/plain",
        )


def test_missing_content_type_rejected() -> None:
    with pytest.raises(Exception, match="valid PDF"):
        validate_pdf_upload("resume.pdf", b"%PDF-1.4", content_type=None)


def test_empty_content_type_rejected() -> None:
    with pytest.raises(Exception, match="valid PDF"):
        validate_pdf_upload("resume.pdf", b"%PDF-1.4", content_type="")


def test_allowed_pdf_content_types_accepted() -> None:
    content = b"%PDF-1.4 minimal"
    for mime in ("application/pdf", "application/x-pdf", "application/octet-stream"):
        validate_pdf_upload("resume.pdf", content, content_type=mime)


def test_oversized_upload_rejected() -> None:
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 10)
    with pytest.raises(Exception, match="10 MiB"):
        validate_pdf_upload("resume.pdf", content, content_type="application/pdf")


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


PARENT_CONTEXT_RESUME = """
Alex Rivera
alex.rivera@example.com
+1-555-0142

Skills: Python, Rust, FastAPI

Experience
Backend Engineer
Company A
2025-01 – 2025-06
- Built APIs for Company A.

Data Analyst
Company B
2024-01 – 2024-06
- Analyzed datasets for Company B.

Projects
Campus Connect
Student-org discovery platform with search and event RSVP.
Technologies: Python, FastAPI
https://github.com/example/campus-connect

Orbit Tracker
Orbital analytics dashboard.
Technologies: React

Education
State University — B.S. Computer Science, 2027
City College — A.A. General Studies, 2024
""".strip()


def test_cross_company_title_composite_rejected() -> None:
    raw = _grounded_llm_payload()
    raw["experience"] = [
        {
            "title": "Backend Engineer",
            "company": "Company B",
            "start_date": "2025-01",
            "end_date": "2025-06",
            "highlights": ["Built APIs for Company A."],
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.experience == []
    assert report.as_counts().get("removed_experience") == 1


def test_cross_job_date_nulled_inside_parent() -> None:
    raw = _grounded_llm_payload()
    raw["experience"] = [
        {
            "title": "Backend Engineer",
            "company": "Company A",
            "start_date": "2024-01",
            "end_date": "2025-06",
            "highlights": ["Built APIs for Company A."],
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert len(profile.experience) == 1
    assert profile.experience[0].start_date is None
    assert profile.experience[0].end_date == "2025-06"
    assert report.as_counts().get("removed_experience_dates") == 1


def test_cross_job_highlight_removed() -> None:
    raw = _grounded_llm_payload()
    raw["experience"] = [
        {
            "title": "Backend Engineer",
            "company": "Company A",
            "start_date": "2025-01",
            "end_date": "2025-06",
            "highlights": ["Analyzed datasets for Company B."],
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.experience[0].highlights == []
    assert report.as_counts().get("removed_highlights") == 1


def test_project_technology_from_other_section_removed() -> None:
    raw = _grounded_llm_payload()
    raw["projects"] = [
        {
            "name": "Campus Connect",
            "description": "Student-org discovery platform with search and event RSVP.",
            "technologies": ["Python", "Rust", "React"],
            "url": "https://github.com/example/campus-connect",
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.projects[0].technologies == ["Python"]
    assert report.as_counts().get("removed_project_technologies") == 2


def test_graduation_year_from_other_institution_removed() -> None:
    raw = _grounded_llm_payload()
    raw["education"] = [
        {
            "institution": "State University",
            "degree": "B.S.",
            "field": "Computer Science",
            "graduation_year": "2024",
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.education[0].graduation_year is None
    assert report.as_counts().get("removed_education_fields") == 1


def test_disjoint_name_parts_not_accepted() -> None:
    resume = "Alex\nSkills: Python\nContact: rivera.family@example.com\nNorthstar Labs"
    raw = _grounded_llm_payload()
    raw["name"] = "Alex Rivera"
    with pytest.raises(ProfileGroundingError, match="candidate name"):
        validate_and_ground_profile(raw, resume)


def test_adjacent_line_title_company_date_retained() -> None:
    resume = """
Alex Rivera
alex.rivera@example.com
+1-555-0142
Software Engineering Intern
Northstar Labs
2025-05 – 2025-08
- Shipped an internal API used by 4 product teams.
Skills: Python
Campus Connect
State University — B.S. Computer Science, 2027
AWS Cloud Practitioner
""".strip()
    raw = _grounded_llm_payload()
    raw["projects"] = []
    raw["evidence_links"] = []
    profile, report = validate_and_ground_profile(raw, resume)
    assert profile.experience[0].company == "Northstar Labs"
    assert profile.experience[0].start_date == "2025-05"
    assert profile.experience[0].highlights
    assert report.as_counts().get("removed_experience") is None


def test_previous_job_date_rejected_from_later_job() -> None:
    raw = _grounded_llm_payload()
    raw["experience"] = [
        {
            "title": "Data Analyst",
            "company": "Company B",
            "start_date": "2025-01",
            "end_date": "2024-06",
            "highlights": ["Analyzed datasets for Company B."],
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.experience[0].start_date is None
    assert profile.experience[0].end_date == "2024-06"
    assert report.as_counts().get("removed_experience_dates") == 1


def test_previous_job_highlight_rejected_from_later_job() -> None:
    raw = _grounded_llm_payload()
    raw["experience"] = [
        {
            "title": "Data Analyst",
            "company": "Company B",
            "start_date": "2024-01",
            "end_date": "2024-06",
            "highlights": ["Built APIs for Company A.", "Analyzed datasets for Company B."],
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.experience[0].highlights == ["Analyzed datasets for Company B."]
    assert report.as_counts().get("removed_highlights") == 1


def test_previous_project_technology_rejected_from_later_project() -> None:
    raw = _grounded_llm_payload()
    raw["projects"] = [
        {
            "name": "Orbit Tracker",
            "description": "Orbital analytics dashboard.",
            "technologies": ["Python", "React"],
            "url": None,
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.projects[0].technologies == ["React"]
    assert report.as_counts().get("removed_project_technologies") == 1


def test_previous_project_url_rejected_from_later_project() -> None:
    raw = _grounded_llm_payload()
    raw["projects"] = [
        {
            "name": "Orbit Tracker",
            "description": "Orbital analytics dashboard.",
            "technologies": ["React"],
            "url": "https://github.com/example/campus-connect",
        }
    ]
    profile, report = validate_and_ground_profile(raw, PARENT_CONTEXT_RESUME)
    assert profile.projects[0].url is None
    assert report.as_counts().get("removed_project_urls") == 1


def test_repeated_title_company_pairs_keep_distinct_dates() -> None:
    resume = """
Alex Rivera
Software Engineer
Acme
2024-01 – 2024-06
- First tour work.

Software Engineer
Acme
2025-01 – 2025-06
- Second tour work.
""".strip()
    raw = _grounded_llm_payload()
    raw["skills"] = []
    raw["projects"] = []
    raw["education"] = []
    raw["certifications"] = []
    raw["evidence_links"] = []
    raw["experience"] = [
        {
            "title": "Software Engineer",
            "company": "Acme",
            "start_date": "2024-01",
            "end_date": "2024-06",
            "highlights": ["First tour work."],
        },
        {
            "title": "Software Engineer",
            "company": "Acme",
            "start_date": "2025-01",
            "end_date": "2025-06",
            "highlights": ["Second tour work."],
        },
    ]
    profile, report = validate_and_ground_profile(raw, resume)
    assert len(profile.experience) == 2
    assert profile.experience[0].start_date == "2024-01"
    assert profile.experience[1].start_date == "2025-01"
    assert profile.experience[0].highlights == ["First tour work."]
    assert profile.experience[1].highlights == ["Second tour work."]
    assert report.as_counts().get("removed_experience_dates") is None


def test_company_a_does_not_match_company_alpha() -> None:
    from backend.services.candidate_profile_agent import _anchor_supported

    assert _anchor_supported("Company A", "Worked at Company A in 2024") is True
    assert _anchor_supported("Company A", "Worked at Company Alpha in 2024") is False
    assert _anchor_supported("Acme", "Acme, Inc.") is True
    assert _anchor_supported("Acme", "Acmeology Lab") is False


def _contact_only_payload(**overrides: object) -> dict:
    raw = _grounded_llm_payload()
    raw["skills"] = []
    raw["projects"] = []
    raw["experience"] = []
    raw["education"] = []
    raw["certifications"] = []
    raw["strengths"] = []
    raw["evidence_links"] = []
    raw.update(overrides)
    return raw


def test_scattered_email_parts_rejected(caplog: pytest.LogCaptureFixture) -> None:
    source = "Alex Rivera\nJohn\nPortfolio: example.com\nPython"
    assert claim_supported("john@example.com", source, min_ratio=0.9) is False
    raw = _contact_only_payload(email="john@example.com", phone=None)
    with caplog.at_level(logging.INFO, logger="backend.services.candidate_profile_agent"):
        profile, report = validate_and_ground_profile(raw, source)
    assert profile.email is None
    assert report.as_counts().get("removed_emails") == 1
    assert "john@example.com" not in caplog.text


def test_exact_email_retained() -> None:
    source = "Alex Rivera\nalex.rivera@example.com"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is True
    profile, report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email == "alex.rivera@example.com"
    assert report.as_counts().get("removed_emails") is None


def test_case_insensitive_exact_email_retained() -> None:
    source = "Alex Rivera\nAlex.Rivera@Example.COM"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is True
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email == "alex.rivera@example.com"


def test_harmless_pdf_spacing_email_retained() -> None:
    source = "Alex Rivera\nalex.rivera @ example.com"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is True
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email == "alex.rivera@example.com"


def test_username_and_domain_on_separate_lines_rejected() -> None:
    source = "Alex Rivera\nalex.rivera\nexample.com"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is False
    profile, report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email is None
    assert report.as_counts().get("removed_emails") == 1


def test_website_domain_without_email_rejected() -> None:
    source = "Alex Rivera\nhttps://example.com\nPortfolio"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is False
    profile, report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email is None
    assert report.as_counts().get("removed_emails") == 1


def test_neighboring_email_address_rejected() -> None:
    source = "Alex Rivera\njane@example.com"
    assert claim_supported("alex.rivera@example.com", source, min_ratio=0.9) is False
    profile, report = validate_and_ground_profile(
        _contact_only_payload(phone=None), source
    )
    assert profile.email is None
    assert report.as_counts().get("removed_emails") == 1


def test_concatenated_unrelated_digits_not_a_phone(caplog: pytest.LogCaptureFixture) -> None:
    source = "Alex Rivera\nGPA 3.9\nZIP 55123\nGraduated 2021"
    raw = _contact_only_payload(email=None, phone="(955) 123-2021")
    with caplog.at_level(logging.INFO, logger="backend.services.candidate_profile_agent"):
        profile, report = validate_and_ground_profile(raw, source)
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1
    assert "(955) 123-2021" not in caplog.text
    assert "9551232021" not in caplog.text


def test_exact_formatted_phone_retained() -> None:
    source = "Alex Rivera\n+1-555-0142"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="+1-555-0142"), source
    )
    assert profile.phone == "+1-555-0142"
    assert report.as_counts().get("removed_phones") is None


def test_phone_punctuation_formatting_retained() -> None:
    source = "Alex Rivera\n(555) 123-4567"
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone == "555-123-4567"


def test_phone_plus_one_equivalence_retained() -> None:
    source = "Alex Rivera\n555-123-4567"
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="+1 555-123-4567"), source
    )
    assert profile.phone == "+1 555-123-4567"


def test_phone_fragments_on_separate_lines_rejected() -> None:
    source = "Alex Rivera\n(555)\n123-4567"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="(555) 123-4567"), source
    )
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1


def test_neighboring_different_phone_rejected() -> None:
    source = "Alex Rivera\n+1-555-0142"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="+1-555-0199"), source
    )
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1


def test_exact_title_retained() -> None:
    assert claim_supported("Software Engineer", "Software Engineer") is True


def test_title_punctuation_variant_retained() -> None:
    assert claim_supported("Software Engineer,", "Software Engineer") is True
    assert claim_supported("Software Engineer", "Software Engineer.") is True


def test_senior_title_inflation_rejected() -> None:
    assert claim_supported("Senior Software Engineer", "Software Engineer") is False
    assert claim_supported("Senior Software Engineer", "Software Engineer", min_ratio=0.9) is False


def test_staff_lead_principal_title_inflation_rejected() -> None:
    source = "Software Engineer"
    assert claim_supported("Staff Software Engineer", source) is False
    assert claim_supported("Lead Software Engineer", source) is False
    assert claim_supported("Principal Software Engineer", source) is False
    assert claim_supported("Junior Software Engineer", source) is False


def test_intern_qualifier_cannot_be_added_or_removed() -> None:
    assert claim_supported("Software Engineer Intern", "Software Engineer") is False
    assert claim_supported("Software Engineer", "Software Engineer Intern") is False
    assert claim_supported("Software Engineer Intern", "Software Engineer Intern") is True


def test_company_boundary_protections_remain_intact() -> None:
    from backend.services.candidate_profile_agent import _anchor_supported

    assert _anchor_supported("Company A", "Company Alpha") is False
    assert _anchor_supported("Acme", "Acmeology Lab") is False
    assert _anchor_supported("Acme", "Acme, Inc.") is True


def test_exact_may_2025_retained() -> None:
    source = "Alex Rivera\nSoftware Engineer\nAcme\nMay 2025 – August 2025\n- Built APIs."
    assert claim_supported("May 2025", source, min_ratio=0.8) is True
    raw = _contact_only_payload(
        email=None,
        phone=None,
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "May 2025",
                "end_date": "August 2025",
                "highlights": ["Built APIs."],
            }
        ],
    )
    profile, report = validate_and_ground_profile(raw, source)
    assert profile.experience[0].start_date == "May 2025"
    assert profile.experience[0].end_date == "August 2025"
    assert report.as_counts().get("removed_experience_dates") is None


def test_case_insensitive_month_date_retained() -> None:
    assert claim_supported("May 2025", "started MAY 2025") is True


def test_month_abbreviation_equivalence_retained() -> None:
    assert claim_supported("May 2025", "May 2025") is True
    assert claim_supported("Jan 2025", "January 2025") is True
    assert claim_supported("January 2025", "Jan 2025") is True


def test_supported_month_range_retained() -> None:
    source = "May 2025 – August 2025"
    assert claim_supported("May 2025", source) is True
    assert claim_supported("August 2025", source) is True
    assert claim_supported("May 2025 – August 2025", source) is True
    assert claim_supported("May–Aug 2025", "May–Aug 2025") is True


def test_nearby_month_rewrite_rejected() -> None:
    assert claim_supported("May 2025", "June 2025") is False
    source = "Alex Rivera\nSoftware Engineer\nAcme\nJune 2025\n- Built APIs."
    raw = _contact_only_payload(
        email=None,
        phone=None,
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "May 2025",
                "end_date": None,
                "highlights": ["Built APIs."],
            }
        ],
    )
    profile, report = validate_and_ground_profile(raw, source)
    assert profile.experience[0].start_date is None
    assert report.as_counts().get("removed_experience_dates") == 1


def test_different_year_month_date_rejected() -> None:
    assert claim_supported("May 2025", "May 2024") is False


def test_month_date_from_neighboring_experience_rejected() -> None:
    resume = """
Alex Rivera
Experience
Software Engineer
Acme
May 2025 – August 2025
- First tour work.
Software Engineer
Beta Labs
June 2025 – July 2025
- Second tour work.
""".strip()
    raw = _contact_only_payload(
        email=None,
        phone=None,
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "June 2025",
                "end_date": "July 2025",
                "highlights": ["First tour work."],
            }
        ],
    )
    profile, report = validate_and_ground_profile(raw, resume)
    assert profile.experience[0].start_date is None
    assert profile.experience[0].end_date is None
    assert report.as_counts().get("removed_experience_dates") == 2


def test_iso_date_behavior_preserved() -> None:
    source = "2025-05 – 2025-08"
    assert claim_supported("2025-05", source) is True
    assert claim_supported("2025-06", source) is False
    assert claim_supported("2025-05", "May 2025") is True


def test_full_date_day_rewrite_rejected() -> None:
    assert claim_supported("2025-05-31", "2025-05-01") is False
    assert claim_supported("05/31/2025", "05/01/2025") is False


def test_full_date_month_only_granularity_mismatch_rejected() -> None:
    assert claim_supported("2025-05-31", "May 2025") is False
    assert claim_supported("May 2025", "2025-05-31") is False
    assert claim_supported("2025-05-31", "2025-05") is False


def test_safe_equivalent_full_date_formatting_retained() -> None:
    assert claim_supported("2025-05-31", "05/31/2025") is True
    assert claim_supported("05/31/2025", "2025-05-31") is True


def test_malformed_calendar_dates_rejected() -> None:
    assert claim_supported("2025-02-31", "2025-02-31") is False
    assert claim_supported("2025-13-01", "2025-13-01") is False
    assert claim_supported("02/31/2025", "02/31/2025") is False


def test_email_prefix_suffix_boundary_attacks_rejected() -> None:
    assert claim_supported("john@example.com", "john@example.com2") is False
    assert claim_supported("john@example.com", "john@example.com_extra") is False
    assert claim_supported("john@example.com", "ajohn@example.com") is False
    assert claim_supported("john@example.com", "john@example.com.extra.org") is False


def test_exact_spaced_case_insensitive_email_retained() -> None:
    assert claim_supported("john@example.com", "john@example.com") is True
    assert claim_supported("john@example.com", "John@Example.COM") is True
    assert claim_supported("john@example.com", "john @ example.com") is True


def test_phone_embedded_inside_longer_numbers_rejected() -> None:
    assert claim_supported("555-123-4567", "2555-123-4567") is False
    source = "Alex Rivera\n2555-123-4567"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1
    source = "Alex Rivera\n9555 123 4567"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone is None
    source = "Alex Rivera\n555-123-45678"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone is None


def test_non_us_country_prefix_suffix_match_rejected() -> None:
    source = "Alex Rivera\n+44 555-123-4567"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1


def test_us_plus_one_equivalence_retained() -> None:
    source = "Alex Rivera\n+1 555-123-4567"
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone == "555-123-4567"


def test_us_e164_compact_equivalence_retained() -> None:
    source = "Alex Rivera\n+15551234567"
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone == "555-123-4567"
    source = "Alex Rivera\n555-123-4567"
    profile, _report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="+15551234567"), source
    )
    assert profile.phone == "+15551234567"


def test_non_us_compact_e164_rejected_for_us_claim() -> None:
    source = "Alex Rivera\n+445551234567"
    profile, report = validate_and_ground_profile(
        _contact_only_payload(email=None, phone="555-123-4567"), source
    )
    assert profile.phone is None
    assert report.as_counts().get("removed_phones") == 1


def _experience_resume(title: str, extra: str = "2025-05\n- Built APIs.") -> str:
    return f"Alex Rivera\n{title}\nAcme\n{extra}"


def _experience_payload(title: str, **date_fields: object) -> dict:
    item = {
        "title": title,
        "company": "Acme",
        "start_date": date_fields.get("start_date", "2025-05"),
        "end_date": date_fields.get("end_date"),
        "highlights": ["Built APIs."],
    }
    return _contact_only_payload(email=None, phone=None, experience=[item])


def test_pipeline_rejects_removed_experience_qualifiers() -> None:
    cases = [
        ("Senior Software Engineer", "Software Engineer"),
        ("Staff Software Engineer", "Software Engineer"),
        ("Software Engineer Intern", "Software Engineer"),
        ("Software Engineer II", "Software Engineer"),
        ("Senior Vice President", "Vice President"),
    ]
    for source_title, claimed_title in cases:
        profile, report = validate_and_ground_profile(
            _experience_payload(claimed_title), _experience_resume(source_title)
        )
        assert profile.experience == []
        assert report.as_counts().get("removed_experience") == 1


def test_pipeline_rejects_invented_experience_qualifiers() -> None:
    cases = [
        ("Software Engineer", "Senior Software Engineer"),
        ("Software Engineer", "Staff Software Engineer"),
        ("Software Engineer", "Software Engineer Intern"),
        ("Vice President", "Senior Vice President"),
    ]
    for source_title, claimed_title in cases:
        profile, report = validate_and_ground_profile(
            _experience_payload(claimed_title), _experience_resume(source_title)
        )
        assert profile.experience == []
        assert report.as_counts().get("removed_experience") == 1


def test_pipeline_rejects_removed_multi_modifier_titles() -> None:
    cases = [
        ("Senior Staff Software Engineer", "Staff Software Engineer"),
        ("Senior Principal Software Engineer", "Principal Software Engineer"),
        ("Executive Vice President", "Vice President"),
        ("Assistant Vice President", "Vice President"),
    ]
    for source_title, claimed_title in cases:
        profile, report = validate_and_ground_profile(
            _experience_payload(claimed_title), _experience_resume(source_title)
        )
        assert profile.experience == []
        assert report.as_counts().get("removed_experience") == 1


def test_pipeline_rejects_invented_multi_modifier_titles() -> None:
    cases = [
        ("Staff Software Engineer", "Senior Staff Software Engineer"),
        ("Principal Software Engineer", "Senior Principal Software Engineer"),
        ("Vice President", "Executive Vice President"),
        ("Vice President", "Assistant Vice President"),
    ]
    for source_title, claimed_title in cases:
        profile, report = validate_and_ground_profile(
            _experience_payload(claimed_title), _experience_resume(source_title)
        )
        assert profile.experience == []
        assert report.as_counts().get("removed_experience") == 1


def test_pipeline_preserves_exact_multi_modifier_titles() -> None:
    profile, report = validate_and_ground_profile(
        _experience_payload("Senior Staff Software Engineer"),
        _experience_resume("Senior Staff Software Engineer"),
    )
    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Senior Staff Software Engineer"
    assert report.as_counts().get("removed_experience") is None


def test_pipeline_rejects_roman_or_numeric_title_level_removal() -> None:
    profile, report = validate_and_ground_profile(
        _experience_payload("Software Engineer"),
        _experience_resume("Software Engineer II"),
    )
    assert profile.experience == []
    profile, report = validate_and_ground_profile(
        _experience_payload("Software Engineer"),
        _experience_resume("Software Engineer 2"),
    )
    assert profile.experience == []
    assert report.as_counts().get("removed_experience") == 1


def test_safe_sr_senior_and_jr_junior_title_equivalence() -> None:
    profile, report = validate_and_ground_profile(
        _experience_payload("Senior Software Engineer"),
        _experience_resume("Sr. Software Engineer"),
    )
    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Senior Software Engineer"
    assert report.as_counts().get("removed_experience") is None
    profile, report = validate_and_ground_profile(
        _experience_payload("Junior Software Engineer"),
        _experience_resume("Jr. Software Engineer"),
    )
    assert len(profile.experience) == 1
    assert profile.experience[0].title == "Junior Software Engineer"


def test_standalone_natural_month_date_retained_through_pipeline() -> None:
    resume = """
Alex Rivera
Software Engineer
Acme
May 2025
- Built APIs.
""".strip()
    profile, report = validate_and_ground_profile(
        _experience_payload("Software Engineer", start_date="May 2025"), resume
    )
    assert len(profile.experience) == 1
    assert profile.experience[0].start_date == "May 2025"
    assert profile.experience[0].highlights == ["Built APIs."]
    assert report.as_counts().get("removed_experience_dates") is None
    assert report.as_counts().get("removed_highlights") is None


def test_present_and_current_ranges_retained() -> None:
    resume = """
Alex Rivera
Software Engineer
Acme
May 2025 – Present
- Built APIs.
""".strip()
    profile, report = validate_and_ground_profile(
        _experience_payload("Software Engineer", start_date="May 2025", end_date="Present"),
        resume,
    )
    assert profile.experience[0].start_date == "May 2025"
    assert profile.experience[0].end_date == "Present"
    assert profile.experience[0].highlights == ["Built APIs."]
    resume = """
Alex Rivera
Software Engineer
Acme
Jan 2024 - Current
- Built APIs.
""".strip()
    profile, report = validate_and_ground_profile(
        _experience_payload("Software Engineer", start_date="Jan 2024", end_date="Current"),
        resume,
    )
    assert profile.experience[0].start_date == "Jan 2024"
    assert profile.experience[0].end_date == "Current"


def test_neighboring_experience_isolation_with_month_dates() -> None:
    resume = """
Alex Rivera
Software Engineer
Acme
May 2025 – August 2025
- First tour work.
Software Engineer
Beta Labs
June 2025 – July 2025
- Second tour work.
""".strip()
    raw = _contact_only_payload(
        email=None,
        phone=None,
        experience=[
            {
                "title": "Software Engineer",
                "company": "Acme",
                "start_date": "June 2025",
                "end_date": "July 2025",
                "highlights": ["Second tour work."],
            }
        ],
    )
    profile, report = validate_and_ground_profile(raw, resume)
    assert profile.experience[0].start_date is None
    assert profile.experience[0].end_date is None
    assert profile.experience[0].highlights == []
    assert report.as_counts().get("removed_experience_dates") == 2
    assert report.as_counts().get("removed_highlights") == 1


def test_adversarial_grounding_logs_remain_count_only(caplog: pytest.LogCaptureFixture) -> None:
    source = "Alex Rivera\njohn@example.com2\n2555-123-4567"
    raw = _contact_only_payload(email="john@example.com", phone="555-123-4567")
    with caplog.at_level(logging.INFO, logger="backend.services.candidate_profile_agent"):
        profile, report = validate_and_ground_profile(raw, source)
    assert profile.email is None
    assert profile.phone is None
    blob = json.dumps(report.as_counts()) + "".join(report.rejected) + caplog.text
    assert "john@example.com" not in blob
    assert "555-123-4567" not in blob
    assert all(key.startswith("removed_") for key in report.as_counts())




def test_multiline_education_keeps_own_fields() -> None:
    resume = """
Alex Rivera
Education
State University
B.S.
Computer Science
2027
City College
A.A.
General Studies
2024
""".strip()
    raw = _grounded_llm_payload()
    raw["skills"] = []
    raw["projects"] = []
    raw["experience"] = []
    raw["certifications"] = []
    raw["evidence_links"] = []
    raw["education"] = [
        {
            "institution": "State University",
            "degree": "B.S.",
            "field": "Computer Science",
            "graduation_year": "2027",
        }
    ]
    profile, report = validate_and_ground_profile(raw, resume)
    assert profile.education[0].degree == "B.S."
    assert profile.education[0].field == "Computer Science"
    assert profile.education[0].graduation_year == "2027"
    assert report.as_counts().get("removed_education_fields") is None


def test_multiline_education_rejects_next_institution_year() -> None:
    resume = """
Alex Rivera
Education
State University
B.S.
Computer Science
2027
City College
A.A.
General Studies
2024
""".strip()
    raw = _grounded_llm_payload()
    raw["skills"] = []
    raw["projects"] = []
    raw["experience"] = []
    raw["certifications"] = []
    raw["evidence_links"] = []
    raw["education"] = [
        {
            "institution": "State University",
            "degree": "B.S.",
            "field": "Computer Science",
            "graduation_year": "2024",
        }
    ]
    profile, report = validate_and_ground_profile(raw, resume)
    assert profile.education[0].graduation_year is None
    assert report.as_counts().get("removed_education_fields") == 1


TEST_USER_ID = 1


def test_candidate_persistence_works(isolated_session: Session) -> None:
    db = isolated_session
    profile, _ = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
    stored = persist_candidate_profile(profile, db, TEST_USER_ID)
    assert stored.id and stored.id.startswith("cand-")
    row = db.query(Candidate).order_by(Candidate.id.desc()).first()
    assert row is not None
    assert row.name == "Alex Rivera"
    assert "Python" in row.skills


def test_failed_extraction_creates_no_candidate_row(isolated_session: Session) -> None:
    db = isolated_session
    before = db.query(Candidate).count()
    with pytest.raises(ProfileExtractionError):
        build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=db,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
            generate_fn=lambda _p, _s: "not-json",
        )
    assert db.query(Candidate).count() == before


def test_failed_grounding_creates_no_candidate_row(isolated_session: Session) -> None:
    db = isolated_session
    before = db.query(Candidate).count()
    bad = _grounded_llm_payload()
    bad["name"] = "Someone Not On Resume"
    with pytest.raises(ProfileGroundingError):
        build_candidate_profile_from_upload(
            "alex.pdf",
            build_simple_text_pdf(SAMPLE_RESUME_TEXT),
            db=db,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
            generate_fn=lambda _p, _s: json.dumps(bad),
        )
    assert db.query(Candidate).count() == before


def test_persistence_rollback_on_failure(isolated_session: Session) -> None:
    db = isolated_session
    before = db.query(Candidate).count()
    profile, _ = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
    with patch.object(db, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError, match="db down"):
            persist_candidate_profile(profile, db, TEST_USER_ID)
    assert db.query(Candidate).count() == before


def test_persist_recovers_from_a_lost_race_instead_of_erroring(isolated_session: Session) -> None:
    """Simulates two concurrent resume uploads from the same user (a
    double-submit, or two tabs): this call's own existence check misses (as
    if a concurrent upload hadn't committed yet from its point of view), but
    a winner row is already committed by the time this call's insert runs.
    Must update the winner's row with this call's data instead of raising or
    creating a second Candidate for the same user — the DB-level unique
    index on Candidate.user_id is what makes the insert fail in the first
    place."""
    db = isolated_session
    winner = Candidate(user_id=TEST_USER_ID, name="Winner Of The Race", skills=[])
    db.add(winner)
    db.commit()

    real_query = db.query
    call_count = {"n": 0}

    class _EmptyQuery:
        def filter(self, *_a, **_k):
            return self

        def first(self):
            return None

    def query_that_misses_once(model):
        if model is Candidate:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _EmptyQuery()
        return real_query(model)

    with patch.object(db, "query", side_effect=query_that_misses_once):
        profile, _ = validate_and_ground_profile(_grounded_llm_payload(), SAMPLE_RESUME_TEXT)
        stored = persist_candidate_profile(profile, db, TEST_USER_ID)

    assert stored.id == f"cand-{winner.id:03d}"
    assert db.query(Candidate).count() == 1
    row = db.query(Candidate).filter(Candidate.user_id == TEST_USER_ID).first()
    assert row.name == "Alex Rivera"  # this call's data won, not left as "Winner Of The Race"


def test_grounded_profile_persists_with_stored_id(isolated_session: Session) -> None:
    db = isolated_session
    stored, _extraction, report = build_candidate_profile_from_upload(
        "alex.pdf",
        build_simple_text_pdf(SAMPLE_RESUME_TEXT),
        db=db,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
        generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
    )
    assert stored.id and stored.id.startswith("cand-")
    assert report.total_rejected == 0
    row = db.query(Candidate).filter(Candidate.name == "Alex Rivera").order_by(Candidate.id.desc()).first()
    assert row is not None


def test_isolated_db_does_not_leak_between_tests(isolated_session: Session) -> None:
    assert isolated_session.query(Candidate).count() == 0


def test_parse_resume_endpoint_returns_real_candidate_profile(isolated_client) -> None:
    client, SessionLocal = isolated_client
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
    with SessionLocal() as db:
        assert db.query(Candidate).count() == 1


def test_parse_resume_rejects_non_pdf(isolated_client) -> None:
    client, _ = isolated_client
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_build_from_upload_end_to_end(isolated_session: Session) -> None:
    content = build_simple_text_pdf(SAMPLE_RESUME_TEXT)
    stored, extraction, report = build_candidate_profile_from_upload(
        "alex.pdf",
        content,
        db=isolated_session,
        user_id=TEST_USER_ID,
        content_type="application/pdf",
        generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
    )
    assert extraction.method == "pdfplumber"
    assert stored.name == "Alex Rivera"
    assert report.rejected == []


def test_upload_path_never_creates_named_temp_file(isolated_session: Session) -> None:
    content = build_simple_text_pdf(SAMPLE_RESUME_TEXT)

    def _boom(*_args, **_kwargs):
        raise AssertionError("NamedTemporaryFile must not be used for uploads")

    with patch("tempfile.NamedTemporaryFile", side_effect=_boom):
        stored, extraction, _report = build_candidate_profile_from_upload(
            "alex.pdf",
            content,
            db=isolated_session,
            user_id=TEST_USER_ID,
            content_type="application/pdf",
            generate_fn=lambda _p, _s: json.dumps(_grounded_llm_payload()),
        )
    assert extraction.method == "pdfplumber"
    assert stored.id


def test_in_memory_bytes_extraction() -> None:
    content = build_simple_text_pdf(SAMPLE_RESUME_TEXT)
    result = extract_resume_text(content)
    assert result.method == "pdfplumber"
    assert "Alex Rivera" in result.text


def test_provider_server_error_maps_to_actionable_502(isolated_client) -> None:
    client, _ = isolated_client
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


def test_oversized_upload_returns_413(isolated_client) -> None:
    client, _ = isolated_client
    content = b"%PDF" + b"a" * (MAX_UPLOAD_BYTES + 1)
    response = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", content, "application/pdf")},
    )
    assert response.status_code == 413
    assert "10 MiB" in response.json()["detail"]


def test_preferences_accept_annual_salary(isolated_client) -> None:
    client, SessionLocal = isolated_client
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
    with SessionLocal() as db:
        assert db.query(TargetPreference).count() == 1


def test_preferences_associates_saved_row_with_the_current_candidate(isolated_client) -> None:
    """Regression test: save_preferences used to create a TargetPreference
    row without ever setting candidate_id, so nothing that later looked up
    a candidate's preferences by candidate_id (e.g. the Form Fill agent's
    location/LinkedIn/etc. lookups) could ever find it."""
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        candidate = Candidate(user_id=client.test_user_id, name="Jordan Quill", email="jordan@example.com", skills=[], projects=[],
                               experience=[], education=[], certifications=[], strengths=[], evidence_links=[])
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        candidate_id = candidate.id

    response = client.post(
        "/api/preferences",
        json={
            "target_roles": ["Software Engineer"],
            "preferred_locations": ["Austin, TX"],
            "salary_min": None,
            "work_authorization": None,
            "sponsorship_required": None,
            "remote_preference": None,
            "constraints": [],
        },
    )
    assert response.status_code == 201
    with SessionLocal() as db:
        record = db.query(TargetPreference).order_by(TargetPreference.id.desc()).first()
        assert record.candidate_id == candidate_id


def test_preferences_round_trips_new_reusable_fields(isolated_client) -> None:
    client, SessionLocal = isolated_client
    payload = {
        "target_roles": ["Software Engineer"],
        "preferred_locations": ["Austin, TX"],
        "salary_min": None,
        "work_authorization": "US Citizen",
        "sponsorship_required": False,
        "remote_preference": None,
        "constraints": [],
        "legal_name": "Jordan A. Quill",
        "linkedin_url": "https://www.linkedin.com/in/jordanquill",
        "github_url": "https://github.com/jordanquill",
        "portfolio_url": "https://jordanquill.dev",
        "earliest_start_date": "Immediately",
        "currently_enrolled_in_program": "Yes",
        "expected_graduation": "May 2027",
        "degree_pursuing": "Bachelor's in Computer Science",
        "gender": "Non-binary",
        "race_ethnicity": "No",
        "veteran_status": "I am not a protected veteran",
        "disability_status": "No, I do not have a disability and have not had one in the past",
    }
    response = client.post("/api/preferences", json=payload)
    assert response.status_code == 201
    body = response.json()
    for key, value in payload.items():
        assert body[key] == value

    with SessionLocal() as db:
        record = db.query(TargetPreference).order_by(TargetPreference.id.desc()).first()
        assert record.legal_name == "Jordan A. Quill"
        assert record.linkedin_url == "https://www.linkedin.com/in/jordanquill"
        assert record.disability_status == payload["disability_status"]


def test_preferences_reject_hourly_sized_salary(isolated_client) -> None:
    client, _ = isolated_client
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


def test_parse_resume_never_returns_mock_alex_without_llm(
    isolated_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the Day 1 canned mock path is unreachable from the production route."""
    client, _ = isolated_client
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


def test_parse_resume_note_uses_total_rejected(isolated_client) -> None:
    client, _ = isolated_client
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

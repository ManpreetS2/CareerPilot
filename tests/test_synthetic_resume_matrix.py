"""Deterministic synthetic resume matrix tests (no live provider)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from backend.services.candidate_profile_agent import (
    claim_supported,
    extract_resume_text,
    validate_and_ground_profile,
)
from tests.synthetic_resume_matrix import (
    LAYOUT_MULTIPAGE,
    LAYOUT_TRADITIONAL,
    LAYOUT_TWO_COLUMN,
    LAYOUTS,
    build_pdf_bytes,
    evaluate_grounded_profile,
    expected_llm_payload,
    forbidden_output_tokens,
    generate_all,
    layout_ids,
    manifest_for,
    source_text,
    validate_parse_response,
)

ROOT = Path(__file__).resolve().parents[1]


def test_generator_creates_three_parseable_pdfs(tmp_path: Path) -> None:
    paths = generate_all(tmp_path)
    assert len(paths) == 3
    assert layout_ids() == [
        LAYOUT_TRADITIONAL,
        LAYOUT_TWO_COLUMN,
        LAYOUT_MULTIPAGE,
    ]
    for path in paths:
        data = path.read_bytes()
        assert data.startswith(b"%PDF")
        result = extract_resume_text(path)
        assert result.method == "pdfplumber"
        assert len(result.text) > 40


def test_generated_pdfs_have_valid_signatures(tmp_path: Path) -> None:
    for layout in LAYOUTS:
        pdf = build_pdf_bytes(layout)
        assert pdf.startswith(b"%PDF")
        assert b"%%EOF" in pdf[-32:]


def test_single_column_extraction_ordering(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_TRADITIONAL)
    path = tmp_path / "t.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    assert text.find("Skills") < text.find("Experience")
    assert text.find("Experience") < text.find("Projects")
    assert text.find("Projects") < text.find("Education")
    assert "20%" in text
    assert "2024-06" in text


def test_two_column_extraction_includes_sidebar_and_main(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_TWO_COLUMN)
    path = tmp_path / "two.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    assert "Python" in text
    assert "Cedar Ridge University" in text
    assert "Backend Engineer" in text
    assert "Maple Circuit Labs" in text
    assert "$100,000" in text or "$100000" in text
    assert "20%" in text
    assert "C" in text
    assert "Go" in text


def test_multipage_extraction_concatenates(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    path = tmp_path / "multi.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    assert "Campus Beacon" in text
    assert "Orbit Ledger" in text
    assert "State Harbor University" in text
    assert "City Harbor College" in text
    assert "2024-01" in text
    assert "2025-01" in text


def test_repeated_title_company_association(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    path = tmp_path / "multi.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    payload = expected_llm_payload(LAYOUT_MULTIPAGE)
    profile, _report = validate_and_ground_profile(payload, text)
    assert len(profile.experience) == 2
    assert profile.experience[0].start_date == "2024-01"
    assert profile.experience[1].start_date == "2025-01"
    assert profile.experience[0].highlights == ["Built APIs for Helix Harbor."]
    assert profile.experience[1].highlights == ["Second tour work at Helix Harbor."]


def test_job_evidence_isolation_on_synthetic_multipage(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    path = tmp_path / "multi.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    payload = expected_llm_payload(LAYOUT_MULTIPAGE)
    payload["experience"][1]["start_date"] = "2024-01"
    payload["experience"][1]["highlights"] = ["Built APIs for Helix Harbor."]
    profile, report = validate_and_ground_profile(payload, text)
    assert profile.experience[1].start_date is None
    assert profile.experience[1].highlights == []
    assert report.as_counts().get("removed_experience_dates") == 1
    assert report.as_counts().get("removed_highlights") == 1


def test_project_tech_and_url_isolation(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    path = tmp_path / "multi.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    payload = expected_llm_payload(LAYOUT_MULTIPAGE)
    payload["projects"][1]["technologies"] = ["Python", "React"]
    payload["projects"][1]["url"] = "https://github.com/example/campus-beacon"
    profile, report = validate_and_ground_profile(payload, text)
    orbit = next(item for item in profile.projects if item.name == "Orbit Ledger")
    assert "Python" not in orbit.technologies
    assert orbit.url is None
    assert report.as_counts().get("removed_project_technologies") == 1
    assert report.as_counts().get("removed_project_urls") == 1


def test_education_field_isolation(tmp_path: Path) -> None:
    layout = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    path = tmp_path / "multi.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    text = extract_resume_text(path).text
    payload = expected_llm_payload(LAYOUT_MULTIPAGE)
    payload["education"][0]["graduation_year"] = "2024"
    profile, report = validate_and_ground_profile(payload, text)
    harbor = next(item for item in profile.education if item.institution == "State Harbor University")
    assert harbor.graduation_year is None
    assert report.as_counts().get("removed_education_fields") == 1


def test_short_skill_boundaries_on_two_column_source() -> None:
    text = source_text(next(item for item in LAYOUTS if item["id"] == LAYOUT_TWO_COLUMN))
    assert claim_supported("C", text) is True
    assert claim_supported("R", text) is True
    assert claim_supported("Go", text) is True
    assert claim_supported("Go", "Google Cloud experience") is False
    assert claim_supported("C", "Career progression") is False
    assert claim_supported("R", "research papers") is False


def test_percent_currency_and_date_preservation(tmp_path: Path) -> None:
    trad = next(item for item in LAYOUTS if item["id"] == LAYOUT_TRADITIONAL)
    two = next(item for item in LAYOUTS if item["id"] == LAYOUT_TWO_COLUMN)
    multi = next(item for item in LAYOUTS if item["id"] == LAYOUT_MULTIPAGE)
    t_path = tmp_path / "t.pdf"
    t_path.write_bytes(build_pdf_bytes(trad))
    two_path = tmp_path / "two.pdf"
    two_path.write_bytes(build_pdf_bytes(two))
    m_path = tmp_path / "m.pdf"
    m_path.write_bytes(build_pdf_bytes(multi))
    t_text = extract_resume_text(t_path).text
    two_text = extract_resume_text(two_path).text
    m_text = extract_resume_text(m_path).text
    t_profile, _ = validate_and_ground_profile(expected_llm_payload(LAYOUT_TRADITIONAL), t_text)
    assert any("20%" in h for h in t_profile.experience[0].highlights)
    two_profile, _ = validate_and_ground_profile(expected_llm_payload(LAYOUT_TWO_COLUMN), two_text)
    assert two_profile.experience[0].start_date == "2025-01"
    assert any("$100,000" in h or "$100000" in h for h in two_profile.experience[0].highlights) or any(
        "20%" in h for h in two_profile.experience[0].highlights
    )
    m_profile, _ = validate_and_ground_profile(expected_llm_payload(LAYOUT_MULTIPAGE), m_text)
    assert m_profile.experience[0].start_date == "2024-01"
    assert m_profile.education[0].graduation_year == "2027"


def test_fabricated_numeric_unit_rejected() -> None:
    source = source_text(next(item for item in LAYOUTS if item["id"] == LAYOUT_TRADITIONAL))
    assert claim_supported("Saved $500 engineering hours.", source) is False
    assert claim_supported("Reduced p95 latency by 40% on search endpoints.", source) is False
    two = source_text(next(item for item in LAYOUTS if item["id"] == LAYOUT_TWO_COLUMN))
    assert claim_supported("Improved throughput by 20 points.", two) is False


def test_manifest_rejects_unsupported_returned_claims() -> None:
    payload = expected_llm_payload(LAYOUT_TRADITIONAL)
    payload["skills"].append("Quantum Teleportation")
    failures = evaluate_grounded_profile(payload, manifest_for(LAYOUT_TRADITIONAL))
    assert "skill_not_allowed" in failures
    assert "unsupported_claim_retained" in failures


def test_matrix_runner_stdout_is_privacy_safe(tmp_path: Path) -> None:
    generate_all(tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_candidate_profile_matrix.py"), "--synthetic"],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
    )
    stdout = result.stdout
    assert "synthetic_layouts=3" in stdout
    assert "passed=3" in stdout
    for token in forbidden_output_tokens():
        assert token not in stdout
    assert "RESUME TEXT" not in stdout
    assert "model" not in stdout.lower() or "extraction_method" in stdout


def test_inprocess_matrix_uses_isolated_db_and_preferences_null(isolated_client, tmp_path: Path) -> None:
    client, SessionLocal = isolated_client
    generate_all(tmp_path)
    pdf = tmp_path / f"{LAYOUT_TRADITIONAL}.pdf"
    payload = expected_llm_payload(LAYOUT_TRADITIONAL)
    with patch(
        "backend.services.candidate_profile_agent.extract_candidate_profile_with_llm",
        return_value=payload,
    ):
        response = client.post(
            "/api/parse-resume",
            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body.get("preferences") is None
    stored = body["candidate"]["id"]
    assert stored.startswith("cand-")
    failures = validate_parse_response(body, manifest_for(LAYOUT_TRADITIONAL))
    assert failures == []
    from backend.db.models import Candidate

    with SessionLocal() as db:
        assert db.query(Candidate).count() == 1


def test_matrix_nonzero_exit_on_unknown_layout(tmp_path: Path) -> None:
    pdf = tmp_path / "not_a_known_layout.pdf"
    pdf.write_bytes(build_pdf_bytes(LAYOUTS[0]))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_candidate_profile_matrix.py"), str(pdf)],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "failed=" in result.stdout
    for token in forbidden_output_tokens():
        assert token not in result.stdout


def test_generated_pdfs_are_not_tracked() -> None:
    listed = subprocess.check_output(["git", "ls-files"], cwd=str(ROOT), text=True)
    assert ".pdf" not in listed
    assert "local_resumes/generated" not in listed

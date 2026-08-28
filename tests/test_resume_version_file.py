"""Cookie-authenticated ResumeVersion PDF/DOCX download."""

from __future__ import annotations

from unittest.mock import patch

from tests.test_resume_version_service import _seed_approved_for_client
from backend.services.resume_export import PDF_MIME, DOCX_MIME, ResumeExportError


def test_owner_cookie_download_returns_pdf_and_docx_bytes(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    version_id = created["id"]

    pdf = client.get(f"/api/resume-versions/{version_id}/file", params={"format": "pdf"})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith(PDF_MIME)
    assert pdf.headers["content-disposition"] == 'attachment; filename="resume-v1.pdf"'
    assert pdf.content.startswith(b"%PDF")
    assert b"%%EOF" in pdf.content[-32:]

    docx = client.get(f"/api/resume-versions/{version_id}/file", params={"format": "docx"})
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(DOCX_MIME)
    assert docx.headers["content-disposition"] == 'attachment; filename="resume-v1.docx"'
    assert docx.content.startswith(b"PK")


def test_cookie_download_requires_authentication(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    client.post("/api/auth/logout")
    response = client.get(f"/api/resume-versions/{created['id']}/file", params={"format": "pdf"})
    assert response.status_code == 401


def test_other_user_cookie_download_is_sanitized_404(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    version_id = created["id"]
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-resume-file@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    response = client.get(f"/api/resume-versions/{version_id}/file", params={"format": "pdf"})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "not found" in detail.lower()
    assert version_id not in detail
    assert "user" not in detail.lower()


def test_invalid_format_is_422_and_missing_version_is_404(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    missing = client.get("/api/resume-versions/rv-missing/file", params={"format": "pdf"})
    assert missing.status_code == 404
    invalid = client.get("/api/resume-versions/rv-missing/file", params={"format": "exe"})
    assert invalid.status_code == 422


def test_unavailable_export_is_409(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    with patch(
        "backend.api.routes.applications.export_owned_resume_version",
        side_effect=ResumeExportError(),
    ):
        response = client.get(f"/api/resume-versions/{created['id']}/file", params={"format": "pdf"})
    assert response.status_code == 409
    assert "unavailable" in response.json()["detail"].lower()

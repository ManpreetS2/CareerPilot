"""Ownership-checked ResumeVersion PDF/DOCX export for the extension."""

from __future__ import annotations

import logging

from tests.test_form_fill_service import _extension_auth_headers
from tests.test_resume_version_service import _seed_approved_for_client
from backend.services.resume_export import PDF_MIME, DOCX_MIME, parse_export_format, InvalidResumeExportFormatError


def test_parse_export_format_allowlist() -> None:
    assert parse_export_format("pdf") == "pdf"
    assert parse_export_format("DOCX") == "docx"
    try:
        parse_export_format("exe")
        raise AssertionError("expected invalid format")
    except InvalidResumeExportFormatError:
        pass


def test_owner_can_download_pdf_and_docx(isolated_client, caplog) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    version_id = created["id"]
    headers = _extension_auth_headers(client)
    client.cookies.clear()

    caplog.set_level(logging.INFO)
    pdf = client.get(
        f"/api/extension/resume-versions/{version_id}/file",
        params={"format": "pdf"},
        headers=headers,
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith(PDF_MIME)
    assert pdf.headers["content-disposition"] == 'attachment; filename="resume-v1.pdf"'
    assert pdf.content.startswith(b"%PDF")
    assert b"%%EOF" in pdf.content[-32:]

    docx = client.get(
        f"/api/extension/resume-versions/{version_id}/file",
        params={"format": "docx"},
        headers=headers,
    )
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(DOCX_MIME)
    assert docx.headers["content-disposition"] == 'attachment; filename="resume-v1.docx"'
    assert docx.content.startswith(b"PK")

    joined = " ".join(record.message for record in caplog.records)
    assert f"version_id={version_id}" in joined or version_id in joined
    assert "format=pdf" in joined or "pdf" in joined
    assert "%PDF" not in joined
    assert "Jordan Avery" not in joined
    assert "jordan@example.com" not in joined
    assert "PK\x03\x04" not in joined


def test_other_user_cannot_download_resume_file(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    version_id = created["id"]
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-resume@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        f"/api/extension/resume-versions/{version_id}/file",
        params={"format": "pdf"},
        headers=headers,
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "not found" in detail.lower()
    assert version_id not in detail
    assert "user" not in detail.lower()


def test_client_supplied_user_id_does_not_bypass_ownership(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    version_id = created["id"]
    owner_id = client.test_user_id
    client.post("/api/auth/logout")
    signup = client.post(
        "/api/auth/signup",
        json={"email": "other-resume-bypass@example.com", "password": "test-password-123"},
    )
    assert signup.status_code == 201
    headers = _extension_auth_headers(client)
    client.cookies.clear()
    response = client.get(
        f"/api/extension/resume-versions/{version_id}/file",
        params={"format": "pdf", "user_id": str(owner_id)},
        headers=headers,
    )
    assert response.status_code == 404


def test_invalid_version_and_format(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    headers = _extension_auth_headers(client)
    client.cookies.clear()
    missing = client.get(
        "/api/extension/resume-versions/rv-missing/file",
        params={"format": "pdf"},
        headers=headers,
    )
    assert missing.status_code == 404
    invalid = client.get(
        "/api/extension/resume-versions/rv-missing/file",
        params={"format": "exe"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_extension_resume_routes_reject_cookie_only_auth(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    listed = client.get("/api/extension/resume-versions")
    downloaded = client.get(f"/api/extension/resume-versions/{created['id']}/file", params={"format": "pdf"})
    assert listed.status_code == 401
    assert downloaded.status_code == 401


def test_extension_resume_list_is_metadata_only(isolated_client) -> None:
    client, SessionLocal = isolated_client
    _seed_approved_for_client(SessionLocal, user_id=client.test_user_id)
    created = client.post("/api/jobs/manual-abc123/resume-versions").json()
    headers = _extension_auth_headers(client)
    client.cookies.clear()
    listed = client.get("/api/extension/resume-versions", params={"job_id": "manual-abc123"}, headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["current_job_id"] == "manual-abc123"
    assert body["versions"][0]["id"] == created["id"]
    assert body["versions"][0]["formats"] == ["pdf", "docx"]
    assert body["versions"][0]["version_number"] == 1
    assert "tailored_bullets" not in body["versions"][0]
    assert "resume_input_snapshot" not in body["versions"][0]


def test_expired_session_is_401(isolated_client) -> None:
    client, _SessionLocal = isolated_client
    client.cookies.clear()
    response = client.get(
        "/api/extension/resume-versions",
        headers={"X-CareerPilot-Session": "not-a-real-session"},
    )
    assert response.status_code == 401

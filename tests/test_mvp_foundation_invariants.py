"""Cross-cutting regressions: existing agents stay unchanged and tests stay isolated."""

from __future__ import annotations

from datetime import date

from backend.db.models import ApplicationPackageRecord, FormFillAttemptRecord
from backend.services.job_scout_service import normalize_job
from backend.services.job_verification_service import detect_suspicious_signals
from backend.schemas.schemas import Job
from backend.services.llm_client import LLMClient


def test_job_scout_normalization_unchanged() -> None:
    job = normalize_job(
        {
            "title": "Software Engineer Intern",
            "company": {"display_name": "Aether Analytics"},
            "location": {"display_name": "San Francisco, CA"},
            "redirect_url": "https://www.adzuna.com/land/ad/1234",
            "description": "Build things.",
            "created": "2026-08-15T10:00:00Z",
            "salary_min": 40000,
            "salary_max": 60000,
        },
        "adzuna",
    )
    assert job.company == "Aether Analytics"
    assert job.date_posted == date(2026, 8, 15)
    assert job.status == "discovered"


def test_job_verification_heuristics_unchanged() -> None:
    reasons = detect_suspicious_signals(
        Job(
            title="Intern",
            company="Unknown",
            url="https://example.com/jobs/1",
            description="Apply now.",
            source="manual",
        )
    )
    assert any("Company name" in reason for reason in reasons)


def test_approval_and_form_fill_routes_unchanged(isolated_client) -> None:
    client, SessionLocal = isolated_client
    with SessionLocal() as db:
        from backend.db.models import JobRecord

        db.add(
            JobRecord(
                public_id="gate-job",
                title="Intern",
                company="Acme",
                url="https://example.com/jobs/gate-job",
                description="Build APIs.",
                source="manual",
                status="discovered",
            )
        )
        db.commit()
        from tests.mvp_helpers import insert_grounded_package, seed_materials_prerequisites

        job = db.query(JobRecord).filter_by(public_id="gate-job").one()
        seed_materials_prerequisites(db, public_id="gate-job")
        insert_grounded_package(db, job)

    generated = client.get("/api/jobs/gate-job/materials")
    assert generated.status_code == 200
    assert generated.json()["approval_status"] == "pending_review"

    unconfirmed = client.post(
        "/api/jobs/gate-job/approve",
        json={"decision": "approved", "eligibility_confirmed": False},
    )
    assert unconfirmed.status_code == 422

    approved = client.post(
        "/api/jobs/gate-job/approve",
        json={"decision": "approved", "eligibility_confirmed": True, "notes": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"

    fill = client.post("/api/jobs/gate-job/fill-application")
    assert fill.status_code == 200
    body = fill.json()
    assert body["ats_platform"] == "unsupported"
    assert body["status"] == "failed"
    with SessionLocal() as db:
        assert db.query(ApplicationPackageRecord).count() == 1
        attempts = db.query(FormFillAttemptRecord).all()
        assert len(attempts) == 1
        assert attempts[0].status == "failed"


def test_llm_generate_is_blocked_in_automated_tests(monkeypatch) -> None:
    monkeypatch.setattr("backend.core.config.settings.gemini_api_key", "test-key")
    client = LLMClient(provider="gemini")
    try:
        client.generate("hello")
        raise AssertionError("LLMClient.generate should have been blocked")
    except AssertionError as exc:
        assert "must not be called during automated tests" in str(exc)

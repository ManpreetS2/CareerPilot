"""Approval Agent tests against an isolated in-memory SQLite session."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.db.models import JobRecord
from backend.schemas.schemas import ApprovalRequest
from backend.services.application_service import apply_approval, get_or_generate_application_package


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def _seed_job(db, public_id: str = "manual-abc123") -> None:
    db.add(
        JobRecord(
            public_id=public_id,
            title="Software Engineer Intern",
            company="Acme",
            url="https://example.com/jobs/1",
            description="Build things.",
            source="manual",
        )
    )
    db.commit()


def test_generate_materials_creates_and_persists_a_package(db) -> None:
    _seed_job(db)
    package = get_or_generate_application_package(db, "manual-abc123")
    assert package.job_id == "manual-abc123"
    assert package.approval_status == "pending_review"
    assert len(package.tailored_bullets) > 0


def test_generate_materials_is_idempotent_not_regenerated(db) -> None:
    _seed_job(db)
    first = get_or_generate_application_package(db, "manual-abc123")
    second = get_or_generate_application_package(db, "manual-abc123")
    assert first.tailored_bullets == second.tailored_bullets
    assert first.cover_letter_draft == second.cover_letter_draft


def test_generate_materials_missing_job_404s(db) -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_or_generate_application_package(db, "does-not-exist")
    assert exc_info.value.status_code == 404


def test_approve_without_eligibility_confirmation_is_rejected(db) -> None:
    _seed_job(db)
    get_or_generate_application_package(db, "manual-abc123")
    with pytest.raises(HTTPException) as exc_info:
        apply_approval(db, "manual-abc123", ApprovalRequest(decision="approved"))
    assert exc_info.value.status_code == 422


def test_approve_with_eligibility_confirmation_succeeds(db) -> None:
    _seed_job(db)
    get_or_generate_application_package(db, "manual-abc123")
    result = apply_approval(
        db,
        "manual-abc123",
        ApprovalRequest(decision="approved", eligibility_confirmed=True, eligibility_notes="all good"),
    )
    assert result.approval_status == "approved"

    package = get_or_generate_application_package(db, "manual-abc123")
    assert package.approval_status == "approved"
    assert package.eligibility_confirmed is True
    assert package.eligibility_notes == "all good"


def test_reject_does_not_require_eligibility_confirmation(db) -> None:
    _seed_job(db)
    get_or_generate_application_package(db, "manual-abc123")
    result = apply_approval(db, "manual-abc123", ApprovalRequest(decision="rejected"))
    assert result.approval_status == "rejected"


def test_edit_requested_does_not_require_eligibility_confirmation(db) -> None:
    _seed_job(db)
    get_or_generate_application_package(db, "manual-abc123")
    result = apply_approval(db, "manual-abc123", ApprovalRequest(decision="edit_requested"))
    assert result.approval_status == "edit_requested"


def test_approve_without_generated_materials_conflicts(db) -> None:
    _seed_job(db)
    with pytest.raises(HTTPException) as exc_info:
        apply_approval(db, "manual-abc123", ApprovalRequest(decision="rejected"))
    assert exc_info.value.status_code == 409

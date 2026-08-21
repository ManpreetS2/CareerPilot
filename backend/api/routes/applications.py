"""Application materials + Approval Agent routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse
from backend.services.application_service import apply_approval, get_or_generate_application_package

router = APIRouter(prefix="/api", tags=["applications"])


@router.post("/jobs/{job_id}/generate-materials", response_model=ApplicationPackage)
def generate_materials(job_id: str, db: Session = Depends(get_db)) -> ApplicationPackage:
    """Return this job's persisted application package, generating one (still
    mocked pending the real Application Material Agent) if none exists yet."""
    return get_or_generate_application_package(db, job_id)


@router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
def approve_materials(
    job_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)
) -> ApprovalResponse:
    return apply_approval(db, job_id, payload)

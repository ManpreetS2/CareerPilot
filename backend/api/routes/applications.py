"""Application-materials placeholder routes."""

from __future__ import annotations

from fastapi import APIRouter

from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse
from backend.services.application_service import apply_approval, mock_application_package

router = APIRouter(prefix="/api", tags=["applications"])


@router.post("/jobs/{job_id}/generate-materials", response_model=ApplicationPackage)
def generate_materials(job_id: str) -> ApplicationPackage:
    """Day 1 mock tailored materials. Real generation is not implemented."""
    return mock_application_package(job_id)


@router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
def approve_materials(job_id: str, payload: ApprovalRequest) -> ApprovalResponse:
    return apply_approval(job_id, payload)

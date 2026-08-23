"""Application materials + Approval Agent routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import (
    ApplicationPackage,
    ApprovalRequest,
    ApprovalResponse,
    AutofillResponse,
    FormFillResult,
)
from backend.services.application_service import (
    StoredMaterialsNotFoundError,
    apply_approval,
    get_or_generate_application_package,
    get_stored_application_package,
)
from backend.services.form_fill_service import get_autofill_data, run_assisted_apply

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/jobs/{job_id}/materials", response_model=ApplicationPackage)
def get_materials(job_id: str, db: Session = Depends(get_db)) -> ApplicationPackage:
    """Return stored grounded materials. Never generates, writes, or calls a provider."""
    try:
        return get_stored_application_package(db, job_id)
    except StoredMaterialsNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/generate-materials", response_model=ApplicationPackage)
def generate_materials(
    job_id: str, request: Request, db: Session = Depends(get_db)
) -> ApplicationPackage:
    """Generate grounded application materials after an explicit user action."""
    generator = getattr(request.app.state, "application_materials_generator", None)
    return get_or_generate_application_package(db, job_id, generator=generator)


@router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
def approve_materials(
    job_id: str, payload: ApprovalRequest, db: Session = Depends(get_db)
) -> ApprovalResponse:
    return apply_approval(db, job_id, payload)


@router.post("/jobs/{job_id}/fill-application", response_model=FormFillResult)
def fill_application(job_id: str, db: Session = Depends(get_db)) -> FormFillResult:
    """Assisted apply: fills a real Greenhouse/Lever form with what can be
    confidently mapped from the approved application package, flags
    anything it can't map, and never submits. Requires the application to
    already be approved."""
    return run_assisted_apply(db, job_id)


@router.get("/extension/autofill", response_model=AutofillResponse)
def extension_autofill(url: str, db: Session = Depends(get_db)) -> AutofillResponse:
    """Field values for the browser extension's content script to fill
    directly into the real page the user is on — matched by the tab's own
    URL, since the extension has no other way to know which job this is."""
    return get_autofill_data(db, url)

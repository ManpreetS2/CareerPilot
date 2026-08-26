"""Application materials + Approval Agent routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user, get_extension_user
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.schemas import (
    ApplicationPackage,
    ApprovalRequest,
    ApprovalResponse,
    AutofillResponse,
    ExtensionPanelData,
    FormFillResult,
)
from backend.services.application_service import (
    StoredMaterialsNotFoundError,
    apply_approval,
    discard_stale_reviewed_package,
    get_or_generate_application_package,
    get_stored_application_package,
)
from backend.services.application_materials_agent import StaleApplicationMaterialsError
from backend.services.form_fill_service import get_autofill_data, get_extension_panel_data, run_assisted_apply

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/jobs/{job_id}/materials", response_model=ApplicationPackage)
def get_materials(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationPackage:
    """Return stored grounded materials. Never generates, writes, or calls a provider."""
    try:
        return get_stored_application_package(db, job_id, user.id)
    except StoredMaterialsNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StaleApplicationMaterialsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/generate-materials", response_model=ApplicationPackage)
def generate_materials(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationPackage:
    """Generate grounded application materials after an explicit user action."""
    generator = getattr(request.app.state, "application_materials_generator", None)
    return get_or_generate_application_package(db, job_id, user.id, generator=generator)


@router.post("/jobs/{job_id}/discard-stale-materials")
def discard_stale_materials(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Explicit owner-only reset of reviewed materials from a previous profile."""
    return discard_stale_reviewed_package(db, job_id, user.id)


@router.post("/jobs/{job_id}/approve", response_model=ApprovalResponse)
def approve_materials(
    job_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApprovalResponse:
    return apply_approval(db, job_id, user.id, payload)


@router.post("/jobs/{job_id}/fill-application", response_model=FormFillResult)
def fill_application(
    job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FormFillResult:
    """Assisted apply: fills a real Greenhouse/Lever form with what can be
    confidently mapped from the approved application package, flags
    anything it can't map, and never submits. Requires the application to
    already be approved."""
    return run_assisted_apply(db, job_id, user.id)


@router.get("/extension/autofill", response_model=AutofillResponse)
def extension_autofill(
    url: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> AutofillResponse:
    """Field values for the browser extension. Authenticated only via the
    extension session header, not as a general alternative to the cookie."""
    return get_autofill_data(db, url, user.id)


@router.get("/extension/panel-data", response_model=ExtensionPanelData)
def extension_panel_data(
    url: str, db: Session = Depends(get_db), user: User = Depends(get_extension_user)
) -> ExtensionPanelData:
    """Read-only job/score/materials status for the extension side panel.
    Same auth as the autofill route above — a second GET-only route inside
    the same /api/extension/ prefix does not expand what the session header
    can authorize. Unlike autofill, never requires an approved package."""
    return get_extension_panel_data(db, url, user.id)

"""Application tracker and dashboard summary routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import (
    ApplicationListItem,
    ApplicationTrackerItem,
    ApplicationTrackerUpdate,
    DashboardSummary,
)
from backend.services.application_tracker_service import (
    TrackerError,
    TrackerInvalidTransitionError,
    TrackerJobNotFoundError,
    get_dashboard_summary,
    get_tracking,
    list_applications,
    update_tracking,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tracker"])


def _http_for_tracker_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TrackerJobNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, TrackerInvalidTransitionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, TrackerError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.error("Unexpected tracker failure category=internal")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to update application tracking.",
    )


@router.get("/applications", response_model=list[ApplicationListItem])
def list_application_rows(db: Session = Depends(get_db)) -> list[ApplicationListItem]:
    """Read-only applications list. Does not create tracker rows."""
    return list_applications(db)


@router.get("/applications/{job_id}/tracking", response_model=ApplicationTrackerItem)
def get_application_tracking(job_id: str, db: Session = Depends(get_db)) -> ApplicationTrackerItem:
    """Read-only tracker lookup. Missing rows return a null status payload."""
    try:
        return get_tracking(db, job_id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_tracker_error(exc) from exc


@router.patch("/applications/{job_id}/tracking", response_model=ApplicationTrackerItem)
def patch_application_tracking(
    job_id: str,
    payload: ApplicationTrackerUpdate,
    db: Session = Depends(get_db),
) -> ApplicationTrackerItem:
    """Explicit user-triggered status update. Never called as a side effect of GET."""
    try:
        return update_tracking(db, job_id, payload)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_tracker_error(exc) from exc


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    """Read-only dashboard metrics from stored records. Empty database is zeros."""
    return get_dashboard_summary(db)

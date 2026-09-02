"""HTTP adapter for the canonical profile-readiness contract."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.services.profile_readiness import (
    DEFAULT_NEXT_ROUTE,
    PROFILE_REQUIRED_CODE,
    ProfileNotReadyError,
    ProfileReadiness,
    require_grounded_candidate,
    require_ready_profile,
)


def profile_readiness_http_detail(readiness: ProfileReadiness) -> dict[str, object]:
    return {
        "ready": False,
        "code": readiness.code or PROFILE_REQUIRED_CODE,
        "missing": list(readiness.missing),
        "next_route": readiness.next_route or DEFAULT_NEXT_ROUTE,
        "message": "Complete your profile before CareerPilot searches for matches.",
    }


def profile_not_ready_http(readiness: ProfileReadiness) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=profile_readiness_http_detail(readiness),
    )


def enforce_profile_ready(db: Session, user_id: int) -> ProfileReadiness:
    """Block discovery before the canonical profile-readiness contract is met."""
    try:
        return require_ready_profile(db, user_id)
    except ProfileNotReadyError as exc:
        raise profile_not_ready_http(exc.readiness) from exc


def enforce_grounded_candidate(db: Session, user_id: int) -> ProfileReadiness:
    """Block scoring/materials/interview before a grounded candidate exists."""
    try:
        return require_grounded_candidate(db, user_id)
    except ProfileNotReadyError as exc:
        raise profile_not_ready_http(exc.readiness) from exc

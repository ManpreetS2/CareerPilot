"""Read-only Application Conversion Analytics. Never scores, scouts, or calls a provider."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.api.profile_gate import enforce_profile_ready
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.analytics import ApplicationAnalyticsSummary
from backend.services.analytics_service import build_conversion_analytics

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/summary", response_model=ApplicationAnalyticsSummary)
def get_analytics_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationAnalyticsSummary:
    """Aggregate the user's own conversion-event log into a funnel summary."""
    enforce_profile_ready(db, user.id)
    return build_conversion_analytics(db, user.id)

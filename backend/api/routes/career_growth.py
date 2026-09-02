"""Read-only Career Growth insights. Never scores, scouts, or calls a provider."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.api.profile_gate import enforce_profile_ready
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.career_growth import CareerGrowthSummary
from backend.services.career_growth_service import build_career_growth

router = APIRouter(prefix="/api", tags=["career-growth"])


@router.get("/career-growth", response_model=CareerGrowthSummary)
def get_career_growth(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CareerGrowthSummary:
    """Aggregate current stored evidence into advisory skill-growth insights."""
    enforce_profile_ready(db, user.id)
    return build_career_growth(db, user.id)

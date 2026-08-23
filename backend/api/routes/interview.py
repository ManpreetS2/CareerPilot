"""Interview-prep placeholder routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_current_user
from backend.db.models import User
from backend.schemas.schemas import InterviewPrep
from backend.services.interview_service import mock_interview_prep

router = APIRouter(prefix="/api", tags=["interview"])


@router.post("/jobs/{job_id}/prepare-interview", response_model=InterviewPrep)
def prepare_interview(job_id: str, user: User = Depends(get_current_user)) -> InterviewPrep:
    """Day 1 mock interview prep. Real generation is not implemented."""
    return mock_interview_prep(job_id)

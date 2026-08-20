"""Job listing and discovery placeholder routes."""

from __future__ import annotations

from fastapi import APIRouter, status

from backend.schemas.schemas import Job, ScoutJobsResponse
from backend.services.job_service import get_job, list_jobs, scout_jobs

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs", response_model=list[Job])
def get_jobs() -> list[Job]:
    return list_jobs()


@router.post("/scout-jobs", response_model=ScoutJobsResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_scout() -> ScoutJobsResponse:
    """Day 1 mock: pretend a scout run completed and return dummy jobs."""
    return ScoutJobsResponse(jobs=scout_jobs())


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_by_id(job_id: str) -> Job:
    return get_job(job_id)

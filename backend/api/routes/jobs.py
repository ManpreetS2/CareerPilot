"""Job listing and discovery routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from backend.schemas.schemas import IngestJobUrlRequest, Job, ScoutJobsResponse
from backend.services.job_scout_service import JobScoutError, ingest_job_url, normalize_job, persist_jobs
from backend.services.job_service import get_job, list_jobs, scout_jobs

router = APIRouter(prefix="/api", tags=["jobs"])

DEFAULT_SCOUT_QUERY = "software engineer intern"


@router.get("/jobs", response_model=list[Job])
def get_jobs() -> list[Job]:
    return list_jobs()


@router.post("/scout-jobs", response_model=ScoutJobsResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_scout(what: str = DEFAULT_SCOUT_QUERY, where: str | None = None) -> ScoutJobsResponse:
    """Run Adzuna + RemoteOK scouts, normalize/dedupe/persist, and return the stored jobs."""
    jobs = scout_jobs(query=what, location=where)
    return ScoutJobsResponse(
        jobs=jobs,
        note=f"Scouted and stored {len(jobs)} job(s) from live sources.",
    )


@router.post("/jobs/ingest-url", response_model=Job, status_code=status.HTTP_201_CREATED)
def ingest_job_url_route(payload: IngestJobUrlRequest) -> Job:
    """Manually add a single job URL — fetches a best-effort title/description
    and stores it with source="manual" for later review/editing."""
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required")

    try:
        raw = ingest_job_url(url)
    except JobScoutError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    job = normalize_job(raw, "manual")
    stored = persist_jobs([job])
    return stored[0]


@router.get("/jobs/{job_id}", response_model=Job)
def get_job_by_id(job_id: str) -> Job:
    return get_job(job_id)

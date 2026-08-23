"""Job listing and discovery routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.schemas import (
    IngestJobUrlRequest,
    Job,
    JobVerificationResponse,
    MatchScore,
    ScoutJobsResponse,
)
from backend.services.analysis_service import list_stored_match_scores
from backend.services.job_scout_service import JobScoutError, ingest_job_url, normalize_job, persist_jobs
from backend.services.job_service import get_job, list_jobs, scout_jobs
from backend.services.job_verification_service import verify_all, verify_and_store

router = APIRouter(prefix="/api", tags=["jobs"])

DEFAULT_SCOUT_QUERY = "software engineer intern"


@router.get("/jobs", response_model=list[Job])
def get_jobs() -> list[Job]:
    return list_jobs()


@router.get("/jobs/scores", response_model=list[MatchScore])
def list_job_scores(db: Session = Depends(get_db)) -> list[MatchScore]:
    """Return stored fit scores for every job that already has one. Never scores."""
    return list_stored_match_scores(db)


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


@router.post("/jobs/verify", response_model=JobVerificationResponse)
def verify_jobs_route(status_filter: str | None = "discovered") -> JobVerificationResponse:
    """Run "still open" + suspicious-posting checks. Defaults to only newly
    discovered jobs; pass status_filter=none (or any falsy value via empty
    string) to re-verify every job in the DB."""
    target = None if not status_filter or status_filter.lower() == "none" else status_filter
    jobs = verify_all(status_filter=target)
    return JobVerificationResponse(
        jobs=jobs,
        verified=sum(1 for job in jobs if job.status == "verified"),
        flagged=sum(1 for job in jobs if job.status == "flagged"),
        stale=sum(1 for job in jobs if job.status == "stale"),
    )


@router.post("/jobs/{job_id}/verify", response_model=Job)
def verify_job_route(job_id: str) -> Job:
    return verify_and_store(job_id)

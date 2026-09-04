"""User-scoped saved jobs. Idempotent save/unsave. Jobs remain a shared catalog."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import JobRecord, SavedJobRecord
from backend.schemas.schemas import Job, JobListItem
from backend.services.analytics_service import record_event
from backend.services.job_service import record_to_job


class SavedJobNotFoundError(LookupError):
    def __init__(self) -> None:
        super().__init__("Saved job not found.")


def _job_or_404(db: Session, job_public_id: str) -> JobRecord:
    record = db.query(JobRecord).filter(JobRecord.public_id == job_public_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return record


def list_saved_job_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(SavedJobRecord.job_id).filter(SavedJobRecord.user_id == user_id).all()
    return {row[0] for row in rows}


def list_saved_jobs(db: Session, user_id: int) -> list[Job]:
    rows = (
        db.query(JobRecord, SavedJobRecord)
        .join(SavedJobRecord, SavedJobRecord.job_id == JobRecord.id)
        .filter(SavedJobRecord.user_id == user_id)
        .order_by(SavedJobRecord.created_at.desc())
        .all()
    )
    jobs: list[Job] = []
    for job_row, _saved in rows:
        job = record_to_job(job_row)
        job.saved = True
        jobs.append(job)
    return jobs


def save_job(db: Session, user_id: int, job_public_id: str) -> JobListItem:
    job_row = _job_or_404(db, job_public_id)
    existing = (
        db.query(SavedJobRecord)
        .filter(SavedJobRecord.user_id == user_id, SavedJobRecord.job_id == job_row.id)
        .first()
    )
    if existing is None:
        db.add(SavedJobRecord(user_id=user_id, job_id=job_row.id))
        record_event(db, job_pk=job_row.id, user_id=user_id, event_type="saved")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    job = record_to_job(job_row)
    job.saved = True
    return JobListItem(job=job, saved=True)


def unsave_job(db: Session, user_id: int, job_public_id: str) -> None:
    job_row = _job_or_404(db, job_public_id)
    db.query(SavedJobRecord).filter(
        SavedJobRecord.user_id == user_id, SavedJobRecord.job_id == job_row.id
    ).delete()
    db.commit()

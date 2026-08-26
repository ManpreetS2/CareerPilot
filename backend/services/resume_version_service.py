"""Immutable per-job resume versions.

CareerPilot's application package is one mutable row per job/user. This
service snapshots approved tailored bullets into append-only resume versions
so later export can target a stable opaque identifier.

Future boundary (not implemented here):
- A later Developer A PR will render one immutable resume version to PDF/DOCX
  and return an authenticated download plus an opaque artifact identifier.
- Developer B may later consume that artifact from the extension only after
  the user explicitly selects and approves a version. The extension must never
  auto-choose or auto-upload a resume version.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord, ResumeVersionRecord
from backend.schemas.schemas import ResumeVersion
from backend.services.application_materials_agent import is_package_ready_for_apply
from backend.services.candidate_provenance import (
    build_resume_input_snapshot,
    canonical_string_list,
    hash_approved_materials,
    hash_resume_input_snapshot,
    version_content_hash,
)

logger = logging.getLogger(__name__)


class ResumeVersionNotFoundError(Exception):
    def __init__(self, message: str = "Resume version not found.") -> None:
        super().__init__(message)


class ResumeVersionConflictError(Exception):
    def __init__(self, message: str = "Approved application materials are not ready to version.") -> None:
        super().__init__(message)


class ResumeVersionPersistenceError(Exception):
    def __init__(self) -> None:
        super().__init__("Unable to save resume version.")


def _load_job(db: Session, job_public_id: str) -> JobRecord:
    job = db.query(JobRecord).filter(JobRecord.public_id == job_public_id).first()
    if job is None:
        raise ResumeVersionNotFoundError("Job not found.")
    return job


def _current_candidate(db: Session, user_id: int, *, refresh: bool = False) -> Candidate | None:
    query = db.query(Candidate).filter(Candidate.user_id == user_id)
    if refresh:
        query = query.populate_existing()
    return query.first()


def _owned_package(db: Session, job: JobRecord, user_id: int) -> ApplicationPackageRecord | None:
    return (
        db.query(ApplicationPackageRecord)
        .filter(
            ApplicationPackageRecord.job_id == job.id,
            ApplicationPackageRecord.user_id == user_id,
        )
        .first()
    )


def _record_to_schema(record: ResumeVersionRecord, job_public_id: str) -> ResumeVersion:
    created = record.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return ResumeVersion(
        id=record.public_id,
        job_id=job_public_id,
        version_number=record.version_number,
        tailored_bullets=list(record.tailored_bullets or []),
        source_traceability_notes=list(record.source_traceability_notes or []),
        created_at=created or datetime.now(timezone.utc),
    )


def _owned_version_query(db: Session, job: JobRecord, user_id: int):
    return db.query(ResumeVersionRecord).filter(
        ResumeVersionRecord.job_id == job.id,
        ResumeVersionRecord.user_id == user_id,
    )


def list_resume_versions(db: Session, job_public_id: str, user_id: int) -> list[ResumeVersion]:
    """Return the caller's versions for one job, newest first. Never writes."""
    job = _load_job(db, job_public_id)
    rows = (
        _owned_version_query(db, job, user_id)
        .order_by(ResumeVersionRecord.version_number.desc())
        .all()
    )
    return [_record_to_schema(row, job.public_id) for row in rows]


def get_resume_version(
    db: Session, job_public_id: str, version_public_id: str, user_id: int
) -> ResumeVersion:
    """Return one owned version. Cross-user access is indistinguishable from missing."""
    job = _load_job(db, job_public_id)
    row = (
        _owned_version_query(db, job, user_id)
        .filter(ResumeVersionRecord.public_id == version_public_id)
        .first()
    )
    if row is None:
        raise ResumeVersionNotFoundError()
    return _record_to_schema(row, job.public_id)


def create_resume_version(db: Session, job_public_id: str, user_id: int) -> ResumeVersion:
    version, _created = save_resume_version(db, job_public_id, user_id)
    return version


def save_resume_version(db: Session, job_public_id: str, user_id: int) -> tuple[ResumeVersion, bool]:
    """Snapshot the current approved package. Never generates materials or calls an LLM."""
    job = _load_job(db, job_public_id)
    package = _owned_package(db, job, user_id)
    if package is None:
        raise ResumeVersionNotFoundError("Approved application materials were not found.")
    if package.approval_status != "approved" or not is_package_ready_for_apply(db, package, user_id):
        raise ResumeVersionConflictError()

    candidate = _current_candidate(db, user_id, refresh=True)
    if candidate is None:
        raise ResumeVersionConflictError()

    bullets = canonical_string_list(package.tailored_bullets)
    notes = canonical_string_list(package.source_traceability_notes)
    approved_hash = getattr(package, "approved_materials_hash", None)
    if not approved_hash or approved_hash != hash_approved_materials(bullets, notes):
        raise ResumeVersionConflictError()

    snapshot = build_resume_input_snapshot(db, candidate, user_id)
    stored_fingerprint = getattr(package, "candidate_profile_fingerprint", None)
    if not stored_fingerprint or hash_resume_input_snapshot(snapshot) != stored_fingerprint:
        raise ResumeVersionConflictError()

    digest = version_content_hash(snapshot, bullets, notes)

    existing = (
        _owned_version_query(db, job, user_id)
        .filter(ResumeVersionRecord.content_hash == digest)
        .first()
    )
    if existing is not None:
        return _record_to_schema(existing, job.public_id), False

    next_number = (
        db.query(func.max(ResumeVersionRecord.version_number))
        .filter(
            ResumeVersionRecord.job_id == job.id,
            ResumeVersionRecord.user_id == user_id,
        )
        .scalar()
        or 0
    ) + 1

    record = ResumeVersionRecord(
        public_id=f"rv-{uuid.uuid4().hex}",
        job_id=job.id,
        user_id=user_id,
        candidate_id=candidate.id,
        version_number=next_number,
        tailored_bullets=bullets,
        source_traceability_notes=notes,
        resume_input_snapshot=snapshot,
        content_hash=digest,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raced = (
            _owned_version_query(db, job, user_id)
            .filter(ResumeVersionRecord.content_hash == digest)
            .first()
        )
        if raced is not None:
            return _record_to_schema(raced, job.public_id), False
        logger.error("resume version persist failed")
        raise ResumeVersionPersistenceError() from None
    db.refresh(record)
    return _record_to_schema(record, job.public_id), True

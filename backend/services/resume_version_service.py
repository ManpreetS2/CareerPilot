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
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord, ResumeVersionRecord
from backend.schemas.schemas import ResumeVersion, ResumeVersionDetail, ResumeVersionProfile, ResumeVersionSummary
from backend.services.application_materials_agent import is_package_ready_for_apply
from backend.services.candidate_provenance import (
    build_resume_input_snapshot,
    canonical_string_list,
    current_resume_input_fingerprint,
    hash_approved_materials,
    hash_resume_input_snapshot,
    version_content_hash,
)

logger = logging.getLogger(__name__)

_MAX_VERSION_ALLOCATION_ATTEMPTS = 8
_PUBLIC_HISTORICAL_PROFILE_FIELDS = (
    "name",
    "email",
    "phone",
    "skills",
    "projects",
    "experience",
    "education",
    "certifications",
    "strengths",
    "evidence_links",
    "legal_name",
    "linkedin_url",
    "github_url",
    "portfolio_url",
)


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


def _aware_created_at(record: ResumeVersionRecord) -> datetime:
    created = record.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created or datetime.now(timezone.utc)


def _public_historical_profile(snapshot: object) -> ResumeVersionProfile:
    source = snapshot if isinstance(snapshot, dict) else {}
    fields = {field: source.get(field) for field in _PUBLIC_HISTORICAL_PROFILE_FIELDS}
    return ResumeVersionProfile.model_validate(fields)


def _matches_current_profile(snapshot: object, current_fingerprint: str | None) -> bool:
    if not current_fingerprint or not isinstance(snapshot, dict) or not snapshot:
        return False
    return hash_resume_input_snapshot(snapshot) == current_fingerprint


def _record_to_summary(
    record: ResumeVersionRecord, current_fingerprint: str | None
) -> ResumeVersionSummary:
    job = record.job
    return ResumeVersionSummary(
        id=record.public_id,
        job_id=job.public_id if job is not None else "",
        job_title=job.title if job is not None else "",
        company=job.company if job is not None else "",
        version_number=record.version_number,
        created_at=_aware_created_at(record),
        bullet_count=len(list(record.tailored_bullets or [])),
        provenance_status="approved_snapshot",
        matches_current_profile=_matches_current_profile(
            record.resume_input_snapshot, current_fingerprint
        ),
    )


def _record_to_detail(
    record: ResumeVersionRecord, current_fingerprint: str | None
) -> ResumeVersionDetail:
    summary = _record_to_summary(record, current_fingerprint)
    return ResumeVersionDetail(
        **summary.model_dump(),
        tailored_bullets=list(record.tailored_bullets or []),
        source_traceability_notes=list(record.source_traceability_notes or []),
        profile=_public_historical_profile(record.resume_input_snapshot),
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


def list_user_resume_versions(db: Session, user_id: int) -> list[ResumeVersionSummary]:
    """Return the caller's versions across jobs, newest first. Never writes."""
    current = current_resume_input_fingerprint(db, user_id, refresh=True)
    rows = (
        db.query(ResumeVersionRecord)
        .options(joinedload(ResumeVersionRecord.job))
        .filter(ResumeVersionRecord.user_id == user_id)
        .order_by(ResumeVersionRecord.created_at.desc(), ResumeVersionRecord.id.desc())
        .all()
    )
    return [_record_to_summary(row, current) for row in rows]


def get_user_resume_version(db: Session, version_public_id: str, user_id: int) -> ResumeVersionDetail:
    """Return one owned historical version. Cross-user access is a sanitized 404."""
    current = current_resume_input_fingerprint(db, user_id, refresh=True)
    row = (
        db.query(ResumeVersionRecord)
        .options(joinedload(ResumeVersionRecord.job))
        .filter(
            ResumeVersionRecord.public_id == version_public_id,
            ResumeVersionRecord.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise ResumeVersionNotFoundError()
    return _record_to_detail(row, current)


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

    snapshot = build_resume_input_snapshot(db, candidate, user_id, refresh=True)
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

    for attempt in range(1, _MAX_VERSION_ALLOCATION_ATTEMPTS + 1):
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
        except IntegrityError as exc:
            db.rollback()
            raced = (
                _owned_version_query(db, job, user_id)
                .filter(ResumeVersionRecord.content_hash == digest)
                .first()
            )
            if raced is not None:
                return _record_to_schema(raced, job.public_id), False
            logger.info(
                "resume version allocation retry attempt=%s error_type=%s",
                attempt,
                type(exc).__name__,
            )
            continue
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("resume version persist failed error_type=%s", type(exc).__name__)
            raise ResumeVersionPersistenceError() from None
        db.refresh(record)
        return _record_to_schema(record, job.public_id), True
    logger.error("resume version persist failed error_type=allocation_exhausted")
    raise ResumeVersionPersistenceError()

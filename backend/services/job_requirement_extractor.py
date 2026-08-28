"""Extract, ground, cache, and persist JobRequirementProfile.

LLM output is optional. Deterministic miners always run so hard eligibility
clauses at the end of a posting cannot be dropped. Cached by
source_fingerprint + extraction_version.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.schemas.job_requirements import EXTRACTION_VERSION, JobRequirementProfile
from backend.services.job_content import canonical_from_job
from backend.services.job_requirement_llm import enrich_profile_with_llm
from backend.services.requirement_mining import mine_hard_requirements

logger = logging.getLogger(__name__)
GenerateFn = Callable[[str, str | None], str]


def profile_from_job_record(job: JobRecord) -> JobRequirementProfile:
    canonical = canonical_from_job(
        title=job.title,
        company=job.company,
        description=job.description or "",
        source=job.source,
        url=job.url or "",
        source_job_id=getattr(job, "source_job_id", None),
        posted_at=job.date_posted,
        fetched_at=job.date_scraped,
        content_status=getattr(job, "content_status", None),  # type: ignore[arg-type]
    )
    profile = mine_hard_requirements(canonical)
    profile.job_id = job.public_id
    return profile


def load_requirement_profile(db: Session, job: JobRecord) -> JobRequirementProfile | None:
    row = (
        db.query(JobRequirementProfileRecord)
        .filter(JobRequirementProfileRecord.job_id == job.id)
        .first()
    )
    if row is None:
        return None
    current = canonical_from_job(
        title=job.title,
        company=job.company,
        description=job.description or "",
        source=job.source,
        url=job.url or "",
        source_job_id=getattr(job, "source_job_id", None),
        posted_at=job.date_posted,
        fetched_at=job.date_scraped,
        content_status=getattr(job, "content_status", None),  # type: ignore[arg-type]
    )
    if row.source_fingerprint != current.source_fingerprint or row.extraction_version != EXTRACTION_VERSION:
        return None
    return JobRequirementProfile.model_validate(row.profile_json)


def persist_requirement_profile(
    db: Session,
    job: JobRecord,
    profile: JobRequirementProfile,
    *,
    provider: str | None = None,
) -> JobRequirementProfile:
    payload = profile.model_dump(mode="json")
    existing = (
        db.query(JobRequirementProfileRecord)
        .filter(JobRequirementProfileRecord.job_id == job.id)
        .first()
    )
    if existing is None:
        existing = JobRequirementProfileRecord(job_id=job.id)
        db.add(existing)
    existing.source_fingerprint = profile.source_fingerprint
    existing.extraction_version = EXTRACTION_VERSION
    existing.extraction_confidence = profile.extraction_confidence
    existing.content_status = profile.content_status
    existing.profile_json = payload
    existing.extracted_at = datetime.now(timezone.utc)
    existing.provider = provider
    db.flush()
    logger.info(
        "requirement_profile persisted job_pk=%s fingerprint=%s version=%s",
        job.id,
        profile.source_fingerprint[:12],
        EXTRACTION_VERSION,
    )
    return profile


def extract_requirement_profile(
    db: Session,
    job: JobRecord,
    *,
    generate_fn: GenerateFn | None = None,
    force: bool = False,
) -> JobRequirementProfile:
    if not force:
        cached = load_requirement_profile(db, job)
        if cached is not None:
            logger.info("requirement_profile cache_hit job_pk=%s", job.id)
            return cached
    profile = profile_from_job_record(job)
    provider = "deterministic"
    if generate_fn is not None:
        profile = enrich_profile_with_llm(profile, generate_fn=generate_fn)
        provider = "injected"
    return persist_requirement_profile(db, job, profile, provider=provider)

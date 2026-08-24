"""Coordinate explicit fit scoring with one-time requirement extraction."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import JobIntelligenceRecord
from backend.schemas.schemas import MatchScore
from backend.services.analysis_service import (
    RequirementsUnavailableError,
    load_job,
    load_latest_candidate,
    load_requirements,
    score_job,
)
from backend.services.job_intelligence_service import (
    extract_job_intelligence,
    has_usable_posting_evidence,
)

logger = logging.getLogger(__name__)
GenerateFn = Callable[[str, str | None], str]
_JOB_LOCKS = tuple(threading.Lock() for _ in range(64))


def score_job_with_intelligence(
    db: Session,
    job_public_id: str,
    user_id: int,
    *,
    generate_fn: GenerateFn | None = None,
    as_of: date | None = None,
) -> MatchScore:
    """Ensure described jobs have intelligence, then score with the same session."""
    job_lock = _JOB_LOCKS[hash(job_public_id) % len(_JOB_LOCKS)]
    with job_lock:
        job = load_job(db, job_public_id)
        # Preserve the candidate prerequisite before spending a provider request.
        load_latest_candidate(db, user_id)
        intelligence_exists = (
            db.query(JobIntelligenceRecord.id)
            .filter(JobIntelligenceRecord.job_id == job.id)
            .first()
            is not None
        )
        extracted = False
        if not intelligence_exists and has_usable_posting_evidence(job):
            try:
                extract_job_intelligence(
                    db,
                    job_public_id,
                    generate_fn=generate_fn,
                )
                intelligence_exists = True
                extracted = True
            except IntegrityError:
                db.rollback()
                intelligence_exists = (
                    db.query(JobIntelligenceRecord.id)
                    .filter(JobIntelligenceRecord.job_id == job.id)
                    .first()
                    is not None
                )
                if not intelligence_exists:
                    raise
                extracted = False

        logger.info(
            "score orchestration job_pk=%s intelligence_exists=%s extracted=%s",
            job.id,
            int(intelligence_exists),
            int(extracted),
        )
        if intelligence_exists and load_requirements(db, job).source != "intelligence":
            raise RequirementsUnavailableError()
        return score_job(db, job_public_id, user_id, as_of=as_of)

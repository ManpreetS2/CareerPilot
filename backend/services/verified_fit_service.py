"""Overlay JobRequirementProfile eligibility onto Fit V2 for Verified Fit.

Fit V2 remains the qualification engine. This module decides whether a score
may be shown as verified and whether a hard eligibility blocker overrides
a green technical score.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import JobRecord
from backend.schemas.schemas import MatchScore
from backend.services.analysis_service import (
    ScoreBreakdown,
    compute_breakdown,
    load_latest_candidate,
    load_preferences,
    load_requirements,
    persist_score,
)
from backend.services.eligibility_engine import evaluate_eligibility
from backend.services.job_requirement_extractor import extract_requirement_profile

logger = logging.getLogger(__name__)


def apply_verified_overlay(breakdown: ScoreBreakdown, report, *, content_status: str | None) -> ScoreBreakdown:
    breakdown.eligibility_status = report.status
    breakdown.watchouts = list(dict.fromkeys([*(breakdown.watchouts or []), *report.watchouts]))
    breakdown.gap_reasons = list(dict.fromkeys([*(breakdown.gap_reasons or []), *report.blockers]))
    if report.status == "likely_ineligible":
        breakdown.match_tier = "weak_match"
        breakdown.apply_recommendation = "probably_skip"
        breakdown.recommendation = "skip"
        if report.blockers:
            reason = report.blockers[0]
            breakdown.rationale = (
                f"Your technical background aligns with the role, but {reason[0].lower() + reason[1:]}"
                if reason
                else breakdown.rationale
            )
            breakdown.match_reasons = [
                *(breakdown.match_reasons or []),
                "Technical alignment is not enough while a stated hard requirement is unmet.",
            ]
    if content_status == "full":
        breakdown.score_kind = "verified"
    else:
        breakdown.score_kind = "preliminary"
    return breakdown


def score_job_verified(
    db: Session,
    job: JobRecord,
    user_id: int,
    *,
    as_of: date | None = None,
) -> MatchScore:
    candidate = load_latest_candidate(db, user_id)
    preferences = load_preferences(db, candidate)
    profile = extract_requirement_profile(db, job)
    requirements = load_requirements(db, job)
    breakdown = compute_breakdown(job, candidate, preferences, requirements, as_of=as_of)
    report = evaluate_eligibility(profile, candidate, preferences, as_of=as_of)
    apply_verified_overlay(breakdown, report, content_status=profile.content_status)
    score = persist_score(db, job, candidate, breakdown, commit=False)
    try:
        from backend.services.match_evidence_service import persist_match_evidence

        persist_match_evidence(
            db,
            user_id=user_id,
            job=job,
            candidate=candidate,
            preferences=preferences,
            profile=profile,
            report=report,
            breakdown=breakdown,
            score=score,
        )
    except Exception:
        logger.warning(
            "match evidence persist failed job_pk=%s error_type=unexpected",
            job.id,
            exc_info=True,
        )
    db.commit()
    return score


def verify_top_ranked_jobs(
    db: Session,
    user_id: int,
    job_public_ids: list[str],
    scores: list[MatchScore],
) -> int:
    """Deterministic full-posting verification for the current top N. No LLM."""
    limit = max(0, int(getattr(settings, "job_requirements_verify_top_n", 10) or 10))
    if limit == 0:
        return 0
    ranked = sorted(
        scores,
        key=lambda item: item.ranking_score if item.ranking_score is not None else -1,
        reverse=True,
    )
    verified = 0
    by_public = {
        job.public_id: job
        for job in db.query(JobRecord).filter(JobRecord.public_id.in_(job_public_ids)).all()
    }
    for item in ranked[:limit]:
        job = by_public.get(item.job_id)
        if job is None:
            continue
        status = getattr(job, "content_status", None) or "unknown"
        if status != "full":
            continue
        try:
            score_job_verified(db, job, user_id)
            verified += 1
        except Exception as exc:  # noqa: BLE001 — one job must not fail Find Jobs
            logger.warning("verified fit skipped job_id=%s error=%s", item.job_id, type(exc).__name__)
    logger.info("verified fit top_n=%s verified=%s", limit, verified)
    return verified

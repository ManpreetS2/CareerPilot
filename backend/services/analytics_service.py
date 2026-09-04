"""Application Conversion Analytics: recording and read-only aggregation.

record_event() is the only write path — a plain append to the log, called
from the handful of existing services that already mutate application state
(saved_job_service, application_service, application_tracker_service). It
only stages the row; it never commits on its own. Callers add it to their
own existing commit for the state change it describes, so the event and the
change it records land in one transaction — succeeding or failing together,
never one without the other. (get_or_generate_application_package is the one
caller with no commit of its own to fold this into; it commits explicitly
right after calling this.)

build_conversion_analytics() is pure read: no LLM call, no mutation, bounded
per-user data volume, so the aggregation is plain Python over fetched rows
rather than raw SQL date-math — the same shape as career_growth_service.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    ApplicationEventRecord,
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    JobRecord,
    MatchScoreRecord,
)
from backend.schemas.analytics import (
    FUNNEL_STAGE_LABELS,
    ApplicationAnalyticsSummary,
    BreakdownBucket,
    FunnelStage,
    FunnelStep,
)

FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    "saved",
    "materials_generated",
    "materials_approved",
    "applied",
    "interviewing",
    "offer",
)

SMALL_SAMPLE_THRESHOLD = 5

_SCORE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("Below 50", 0.0, 50.0),
    ("50-70", 50.0, 70.0),
    ("70-85", 70.0, 85.0),
    ("85+", 85.0, 101.0),  # exclusive upper bound; 100 is a valid score
)


def record_event(db: Session, *, job_pk: int, user_id: int, event_type: str) -> None:
    """Stage one event for the caller's own commit. Never raises on a
    duplicate — the log tolerates and expects repeats (e.g. a later
    interview round re-enters "interviewing")."""

    db.add(ApplicationEventRecord(job_id=job_pk, user_id=user_id, event_type=event_type))


@dataclass
class _JobEvents:
    job_id: int
    first_occurrence: dict[str, datetime]


def _load_job_events(db: Session, user_id: int) -> dict[int, _JobEvents]:
    rows = (
        db.query(ApplicationEventRecord)
        .filter(ApplicationEventRecord.user_id == user_id)
        .order_by(ApplicationEventRecord.occurred_at.asc())
        .all()
    )
    by_job: dict[int, _JobEvents] = {}
    for row in rows:
        entry = by_job.setdefault(row.job_id, _JobEvents(job_id=row.job_id, first_occurrence={}))
        # Rows are ordered ascending, so the first time we see an event_type
        # for this job is genuinely its earliest occurrence.
        entry.first_occurrence.setdefault(row.event_type, row.occurred_at)
    return by_job


def _median_days(job_events: dict[int, _JobEvents], from_stage: str, to_stage: str) -> float | None:
    deltas: list[float] = []
    for entry in job_events.values():
        start = entry.first_occurrence.get(from_stage)
        end = entry.first_occurrence.get(to_stage)
        if start is None or end is None:
            continue
        deltas.append((end - start).total_seconds() / 86400)
    if not deltas:
        return None
    return round(statistics.median(deltas), 1)


def _bucket(label: str, applied_jobs: set[int], population: set[int]) -> BreakdownBucket:
    total = len(population)
    applied = len(population & applied_jobs)
    rate = round(applied / total, 3) if total else None
    return BreakdownBucket(
        label=label,
        applied_count=applied,
        total_count=total,
        applied_rate=rate,
        small_sample=total < SMALL_SAMPLE_THRESHOLD,
    )


def _score_band_label(score: float) -> str | None:
    for label, lower, upper in _SCORE_BANDS:
        if lower <= score < upper:
            return label
    return None


def build_conversion_analytics(db: Session, user_id: int) -> ApplicationAnalyticsSummary:
    job_events = _load_job_events(db, user_id)

    stage_jobs: dict[str, set[int]] = {
        stage: {job_id for job_id, entry in job_events.items() if stage in entry.first_occurrence}
        for stage in FUNNEL_STAGES
    }
    rejected_jobs = {job_id for job_id, entry in job_events.items() if "rejected" in entry.first_occurrence}
    withdrawn_jobs = {job_id for job_id, entry in job_events.items() if "withdrawn" in entry.first_occurrence}

    funnel: list[FunnelStep] = []
    previous_jobs: set[int] | None = None
    for stage in FUNNEL_STAGES:
        jobs = stage_jobs[stage]
        conversion = None
        if previous_jobs is not None and previous_jobs:
            conversion = round(len(jobs & previous_jobs) / len(previous_jobs), 3)
        funnel.append(
            FunnelStep(
                stage=stage,
                label=FUNNEL_STAGE_LABELS[stage],
                jobs_count=len(jobs),
                conversion_from_previous=conversion,
            )
        )
        previous_jobs = jobs

    median_saved_to_applied = _median_days(job_events, "saved", "applied")
    median_applied_to_interviewing = _median_days(job_events, "applied", "interviewing")

    # Source/score-band breakdowns are scoped to jobs CareerPilot actually
    # helped save — not every tracker row (a user can log an externally-found
    # application directly), so this stays an honest "of what CareerPilot
    # surfaced, what converted" question rather than mixing in rows analytics
    # never touched.
    saved_population = stage_jobs["saved"]
    applied_jobs = stage_jobs["applied"]

    by_source: list[BreakdownBucket] = []
    if saved_population:
        jobs_by_source: dict[str, set[int]] = defaultdict(set)
        for job_id, source in (
            db.query(JobRecord.id, JobRecord.source).filter(JobRecord.id.in_(saved_population)).all()
        ):
            jobs_by_source[source].add(job_id)
        for source in sorted(jobs_by_source):
            by_source.append(_bucket(source, applied_jobs, jobs_by_source[source]))

    by_match_score_band: list[BreakdownBucket] = []
    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    if saved_population and candidate is not None:
        jobs_by_band: dict[str, set[int]] = defaultdict(set)
        scores = (
            db.query(MatchScoreRecord.job_id, MatchScoreRecord.overall_score)
            .filter(
                MatchScoreRecord.job_id.in_(saved_population),
                MatchScoreRecord.candidate_id == candidate.id,
            )
            .all()
        )
        for job_id, overall_score in scores:
            band = _score_band_label(overall_score)
            if band is not None:
                jobs_by_band[band].add(job_id)
        for label, _lower, _upper in _SCORE_BANDS:
            if label in jobs_by_band:
                by_match_score_band.append(_bucket(label, applied_jobs, jobs_by_band[label]))

    notice = None
    earliest_event = min(
        (entry.first_occurrence[etype] for entry in job_events.values() for etype in entry.first_occurrence),
        default=None,
    )
    if earliest_event is not None:
        earlier_tracker = (
            db.query(ApplicationTrackerRecord)
            .filter(ApplicationTrackerRecord.user_id == user_id, ApplicationTrackerRecord.created_at < earliest_event)
            .first()
        )
        earlier_package = (
            db.query(ApplicationPackageRecord)
            .filter(ApplicationPackageRecord.user_id == user_id, ApplicationPackageRecord.created_at < earliest_event)
            .first()
        )
        if earlier_tracker is not None or earlier_package is not None:
            notice = (
                "Some of your applications predate conversion tracking and aren't reflected below — "
                "numbers only cover activity since analytics started recording."
            )

    return ApplicationAnalyticsSummary(
        generated_at=datetime.now(timezone.utc),
        funnel=funnel,
        rejected_count=len(rejected_jobs),
        withdrawn_count=len(withdrawn_jobs),
        median_days_saved_to_applied=median_saved_to_applied,
        median_days_applied_to_interviewing=median_applied_to_interviewing,
        by_source=by_source,
        by_match_score_band=by_match_score_band,
        notice=notice,
    )

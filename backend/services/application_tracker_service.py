"""Application tracker and dashboard aggregation.

Independent of Form Fill attempts and Approval Agent decisions. Status
changes here must never rewrite packages, eligibility, or assisted-apply
rows. Reads never create or mutate tracker rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.schemas.schemas import (
    ApplicationListItem,
    ApplicationTrackerItem,
    ApplicationTrackerUpdate,
    DashboardSummary,
    TrackerStatus,
)
from backend.services.analytics_service import record_event

logger = logging.getLogger(__name__)

# Statuses the conversion funnel records as events. "saved" is already
# captured by saved_job_service.save_job's own hook, and "pending_review" /
# "approved" / "ready_to_apply" are plain Kanban statuses with no
# corresponding FUNNEL_STAGES entry in analytics_service.py — there is
# nothing for an event at those statuses to feed. A job can reach
# "ready_to_apply" without ever going through application_service's
# materials_generated/materials_approved hooks (ALLOWED_TRANSITIONS allows
# "saved" -> "ready_to_apply" directly); that's an intentional product path
# (tracking a job to apply to manually), and it shows up honestly in the
# funnel as a job present at "applied" without having passed through
# "materials_approved" — not as missing or double-counted data.
_TRACKED_EVENT_STATUSES = frozenset({"applied", "interviewing", "offer", "rejected", "withdrawn"})

TRACKER_STATUSES: tuple[str, ...] = (
    "saved",
    "pending_review",
    "approved",
    "ready_to_apply",
    "applied",
    "interviewing",
    "rejected",
    "offer",
    "withdrawn",
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "saved": frozenset({"pending_review", "approved", "ready_to_apply", "withdrawn", "rejected"}),
    "pending_review": frozenset({"saved", "approved", "rejected", "withdrawn"}),
    "approved": frozenset({"pending_review", "ready_to_apply", "rejected", "withdrawn"}),
    "ready_to_apply": frozenset({"approved", "applied", "withdrawn", "rejected"}),
    "applied": frozenset({"interviewing", "rejected", "offer", "withdrawn"}),
    "interviewing": frozenset({"applied", "offer", "rejected", "withdrawn"}),
    "rejected": frozenset({"saved", "withdrawn"}),
    "offer": frozenset({"withdrawn"}),
    "withdrawn": frozenset({"saved"}),
}


class TrackerError(Exception):
    """Sanitized tracker error. ``str(exc)`` is safe for HTTP details."""


class TrackerJobNotFoundError(TrackerError):
    def __init__(self) -> None:
        super().__init__("Job not found.")


class TrackerInvalidTransitionError(TrackerError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Cannot change tracking status from {current} to {target}.")
        self.current = current
        self.target = target


class ReminderNotSetError(TrackerError):
    def __init__(self) -> None:
        super().__init__("No follow-up date is set for this application.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def allowed_statuses_for(current: str | None) -> list[TrackerStatus]:
    """Statuses the UI may present for an explicit user selection.

    Includes the current status so a <select> can display it, plus only
    transitions the backend will accept. A missing tracker row may be created
    with any first status.
    """

    if current is None:
        allowed = set(TRACKER_STATUSES)
    else:
        allowed = {current} | set(ALLOWED_TRANSITIONS.get(current, frozenset()))
    return [status for status in TRACKER_STATUSES if status in allowed]  # type: ignore[misc]


def _get_job(db: Session, job_id: str) -> JobRecord:
    job = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job is None:
        raise TrackerJobNotFoundError()
    return job


def _record_to_item(record: ApplicationTrackerRecord, job_public_id: str) -> ApplicationTrackerItem:
    return ApplicationTrackerItem(
        job_id=job_public_id,
        status=record.status,  # type: ignore[arg-type]
        note=record.status_note,
        reminder_date=record.reminder_date,
        created_at=record.created_at,
        updated_at=record.updated_at,
        allowed_statuses=allowed_statuses_for(record.status),
    )


def _latest_candidate(db: Session, user_id: int) -> Candidate | None:
    return db.query(Candidate).filter(Candidate.user_id == user_id).first()


def _latest_match_for_job(
    db: Session,
    job_pk: int,
    candidate_id: int | None,
) -> MatchScoreRecord | None:
    if candidate_id is None:
        return None
    return (
        db.query(MatchScoreRecord)
        .filter(
            MatchScoreRecord.job_id == job_pk,
            MatchScoreRecord.candidate_id == candidate_id,
        )
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )


def latest_preference(db: Session, candidate: Candidate | None, user_id: int) -> TargetPreference | None:
    """The user's most recently saved preferences.

    Public because job discovery needs it too. Handles `candidate=None`
    because preferences can be saved before any resume upload — see the
    comment on TargetPreference.user_id in db/models.py.
    """
    linked = (
        db.query(TargetPreference)
        .filter(TargetPreference.user_id == user_id)
        .order_by(TargetPreference.id.desc())
        .first()
    )
    if linked is not None:
        return linked
    if candidate is not None:
        return (
            db.query(TargetPreference)
            .filter(TargetPreference.candidate_id == candidate.id)
            .order_by(TargetPreference.id.desc())
            .first()
        )
    return None


def profile_completion_percent(
    candidate: Candidate | None,
    preferences: TargetPreference | None,
) -> int:
    """Honest stored-profile completion. Empty database is 0, never a demo constant."""

    if candidate is None:
        return 0
    checks = (
        bool((candidate.name or "").strip()),
        bool((candidate.email or "").strip()),
        bool(candidate.skills),
        bool(candidate.experience),
        bool(candidate.education),
        bool(candidate.projects),
        bool(candidate.certifications) or bool(candidate.strengths),
        bool(preferences and preferences.target_roles),
    )
    return int(round(100 * sum(1 for item in checks if item) / len(checks)))


def get_tracking(db: Session, job_id: str, user_id: int) -> ApplicationTrackerItem:
    """Read-only. Missing tracker rows return a null status payload, not a new row."""

    job = _get_job(db, job_id)
    record = (
        db.query(ApplicationTrackerRecord)
        .filter(ApplicationTrackerRecord.job_id == job.id, ApplicationTrackerRecord.user_id == user_id)
        .first()
    )
    if record is None:
        logger.info("tracker read miss job_pk=%s", job.id)
        return ApplicationTrackerItem(job_id=job_id, allowed_statuses=allowed_statuses_for(None))
    logger.info("tracker read hit job_pk=%s status=%s", job.id, record.status)
    return _record_to_item(record, job_id)


@dataclass(frozen=True)
class ReminderExportDetails:
    """Everything the .ics download route needs, in one ownership-checked read."""

    job_public_id: str
    job_title: str
    company: str
    reminder_date: date


def get_reminder_export_details(db: Session, job_id: str, user_id: int) -> ReminderExportDetails:
    """For the calendar-export route. Raises TrackerJobNotFoundError if the
    job doesn't exist, ReminderNotSetError if there's no tracker row for this
    user or no reminder_date set on it — including another user's row, which
    the job_id + user_id filter already excludes."""

    job = _get_job(db, job_id)
    record = (
        db.query(ApplicationTrackerRecord)
        .filter(ApplicationTrackerRecord.job_id == job.id, ApplicationTrackerRecord.user_id == user_id)
        .first()
    )
    if record is None or record.reminder_date is None:
        raise ReminderNotSetError()
    return ReminderExportDetails(
        job_public_id=job_id,
        job_title=job.title,
        company=job.company,
        reminder_date=record.reminder_date,
    )


def list_applications(db: Session, user_id: int) -> list[ApplicationListItem]:
    """Read-only list of stored jobs with optional tracker/package/score fields."""

    jobs = db.query(JobRecord).order_by(JobRecord.id.desc()).all()
    candidate = _latest_candidate(db, user_id)
    candidate_id = candidate.id if candidate else None
    items: list[ApplicationListItem] = []
    for job in jobs:
        tracker = (
            db.query(ApplicationTrackerRecord)
            .filter(ApplicationTrackerRecord.job_id == job.id, ApplicationTrackerRecord.user_id == user_id)
            .first()
        )
        package = (
            db.query(ApplicationPackageRecord)
            .filter(ApplicationPackageRecord.job_id == job.id, ApplicationPackageRecord.user_id == user_id)
            .first()
        )
        match = _latest_match_for_job(db, job.id, candidate_id)
        updated_at = None
        if tracker is not None:
            updated_at = tracker.updated_at
        elif package is not None:
            updated_at = package.created_at
        elif job.date_scraped is not None:
            updated_at = job.date_scraped
        items.append(
            ApplicationListItem(
                job_id=job.public_id,
                title=job.title,
                company=job.company,
                match_score=match.overall_score if match is not None else None,
                recommendation=match.recommendation if match is not None else None,  # type: ignore[arg-type]
                approval_status=package.approval_status if package is not None else None,  # type: ignore[arg-type]
                tracker_status=tracker.status if tracker is not None else None,  # type: ignore[arg-type]
                reminder_date=tracker.reminder_date if tracker is not None else None,
                updated_at=updated_at,
                allowed_statuses=allowed_statuses_for(
                    tracker.status if tracker is not None else None
                ),
            )
        )
    logger.info("tracker list count=%s", len(items))
    return items


def _transition_allowed(current: str | None, target: TrackerStatus) -> bool:
    if current is None or current == target:
        return True
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    return target in allowed


def _maybe_record_status_event(
    db: Session, *, job_pk: int, user_id: int, status: str, previous_status: str | None
) -> None:
    """Stage a conversion-funnel event for this status change, if any — call
    before the caller's own db.commit() so the event and the tracker status
    change land in the same transaction. record_event() only stages the row;
    it never commits on its own, so this can never succeed independently of
    (or fail independently of) the state change it is describing."""
    if status in _TRACKED_EVENT_STATUSES and status != previous_status:
        record_event(db, job_pk=job_pk, user_id=user_id, event_type=status)


def update_tracking(
    db: Session,
    job_id: str,
    request: ApplicationTrackerUpdate,
    user_id: int,
) -> ApplicationTrackerItem:
    """Explicit status update. Creates the unique tracker row if needed."""

    job = _get_job(db, job_id)
    record = (
        db.query(ApplicationTrackerRecord)
        .filter(ApplicationTrackerRecord.job_id == job.id, ApplicationTrackerRecord.user_id == user_id)
        .first()
    )
    current = record.status if record is not None else None
    if not _transition_allowed(current, request.status):
        logger.info(
            "tracker invalid transition job_pk=%s from=%s to=%s",
            job.id,
            current,
            request.status,
        )
        raise TrackerInvalidTransitionError(current or "unset", request.status)

    now = _now()
    if record is None:
        record = ApplicationTrackerRecord(
            job_id=job.id,
            user_id=user_id,
            status=request.status,
            status_note=request.note if "note" in request.model_fields_set else None,
            reminder_date=request.reminder_date if "reminder_date" in request.model_fields_set else None,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        _maybe_record_status_event(
            db, job_pk=job.id, user_id=user_id, status=request.status, previous_status=None
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(ApplicationTrackerRecord)
                .filter(ApplicationTrackerRecord.job_id == job.id, ApplicationTrackerRecord.user_id == user_id)
                .first()
            )
            if existing is None:
                raise
            logger.info("tracker unique conflict recovered job_pk=%s", job.id)
            if not _transition_allowed(existing.status, request.status):
                raise TrackerInvalidTransitionError(existing.status, request.status)
            previous_status = existing.status
            existing.status = request.status
            if "note" in request.model_fields_set:
                existing.status_note = request.note
            if "reminder_date" in request.model_fields_set:
                existing.reminder_date = request.reminder_date
            existing.updated_at = now
            _maybe_record_status_event(
                db, job_pk=job.id, user_id=user_id, status=request.status, previous_status=previous_status
            )
            db.commit()
            db.refresh(existing)
            return _record_to_item(existing, job_id)
        db.refresh(record)
        logger.info("tracker created job_pk=%s status=%s", job.id, record.status)
        return _record_to_item(record, job_id)

    record.status = request.status
    if "note" in request.model_fields_set:
        record.status_note = request.note
    if "reminder_date" in request.model_fields_set:
        record.reminder_date = request.reminder_date
    record.updated_at = now
    _maybe_record_status_event(
        db, job_pk=job.id, user_id=user_id, status=request.status, previous_status=current
    )
    db.commit()
    db.refresh(record)
    logger.info("tracker updated job_pk=%s status=%s", job.id, record.status)
    return _record_to_item(record, job_id)


def get_dashboard_summary(db: Session, user_id: int) -> DashboardSummary:
    """Read-only aggregates from stored rows. Empty database returns zeros."""

    jobs = db.query(JobRecord).all()
    candidate = _latest_candidate(db, user_id)
    preferences = latest_preference(db, candidate, user_id)
    trackers = db.query(ApplicationTrackerRecord).filter(ApplicationTrackerRecord.user_id == user_id).all()
    packages = db.query(ApplicationPackageRecord).filter(ApplicationPackageRecord.user_id == user_id).all()

    tracker_by_job = {row.job_id: row for row in trackers}
    package_by_job = {row.job_id: row for row in packages}

    high_matches = 0
    candidate_id = candidate.id if candidate else None
    for job in jobs:
        match = _latest_match_for_job(db, job.id, candidate_id)
        if match is not None and match.recommendation == "apply":
            high_matches += 1

    applications_saved = 0
    applications_ready = 0
    applications_applied = 0
    ready_to_apply = 0
    interview_count_jobs: set[int] = set()

    for job in jobs:
        tracker = tracker_by_job.get(job.id)
        package = package_by_job.get(job.id)
        status = tracker.status if tracker is not None else None
        approval = package.approval_status if package is not None else None
        if status == "saved":
            applications_saved += 1
        elif status is None and approval in {"draft", "pending_review", "edit_requested"}:
            applications_saved += 1
        if status in {"approved", "ready_to_apply"}:
            applications_ready += 1
        elif status is None and approval == "approved":
            applications_ready += 1
        if status == "ready_to_apply":
            ready_to_apply += 1
        elif status is None and approval == "approved":
            ready_to_apply += 1
        if status == "applied":
            applications_applied += 1
        if status == "interviewing":
            interview_count_jobs.add(job.id)

    skills_count = 0
    if candidate is not None:
        skills_count = len([item for item in (candidate.skills or []) if isinstance(item, str)])

    target_roles = list(preferences.target_roles or []) if preferences is not None else []
    preferred_location = None
    if preferences is not None and preferences.preferred_locations:
        preferred_location = preferences.preferred_locations[0]

    summary = DashboardSummary(
        profile_completion=profile_completion_percent(candidate, preferences),
        skills_count=skills_count,
        target_roles=target_roles,
        preferred_location=preferred_location,
        jobs_discovered=len(jobs),
        jobs_verified=sum(1 for job in jobs if job.status == "verified"),
        high_matches=high_matches,
        ready_to_apply=ready_to_apply,
        applications_saved=applications_saved,
        applications_ready=applications_ready,
        applications_applied=applications_applied,
        interviews=len(interview_count_jobs),
    )
    logger.info(
        "dashboard summary jobs=%s verified=%s high_matches=%s interviews=%s",
        summary.jobs_discovered,
        summary.jobs_verified,
        summary.high_matches,
        summary.interviews,
    )
    return summary

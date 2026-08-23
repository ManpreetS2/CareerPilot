"""Approval Agent — human-in-the-loop review of tailored application materials.

Materials themselves stay mocked (`_mock_materials`) until the real
Application Material Agent replaces them — this module owns persistence and
the approve/edit/reject decision, not generation quality. A package is
generated once per job and then persisted; re-requesting it returns the same
stored package rather than silently regenerating (and discarding) reviewed
content. "One package per job" is enforced by a DB-level unique index
(`ux_application_packages_job_id`, see db/models.py), not just the
check-then-insert below — two concurrent generate calls for the same job
race safely: whichever loses is caught and returns the winner's row instead
of erroring or creating a duplicate.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord
from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse

_APPROVAL_MESSAGES = {
    "approved": "Application package approved. Ready for the next step once Form Fill lands.",
    "edit_requested": "Edit requested. Package remains in review.",
    "rejected": "Application package rejected.",
}


def _get_job_record(db: Session, job_id: str) -> JobRecord:
    record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
    return record


def _get_current_candidate(db: Session, user_id: int) -> Candidate | None:
    return db.query(Candidate).filter(Candidate.user_id == user_id).first()


def _mock_materials(job: JobRecord) -> tuple[list[str], str, str, list[str]]:
    """Placeholder tailored materials. Real generation is a separate, ongoing workstream."""
    tailored_bullets = [
        f"Built Python APIs relevant to {job.company}'s intern stack.",
        "Wrote SQL-backed features with tests and documented edge cases.",
        "Collaborated across frontend and backend on a shipped campus product.",
    ]
    cover_letter_draft = (
        f"Dear {job.company} hiring team,\n\n"
        f"I am applying for the {job.title} role. This is a placeholder draft.\n"
    )
    recruiter_message = (
        f"Hi, I'm interested in the {job.title} role at {job.company}. "
        "Happy to share a tailored resume."
    )
    source_traceability_notes = [
        "Placeholder bullet — not yet grounded in a real candidate profile.",
        "Real generation with source traceability lands with the Application Material Agent.",
    ]
    return tailored_bullets, cover_letter_draft, recruiter_message, source_traceability_notes


def _record_to_package(record: ApplicationPackageRecord, job_public_id: str) -> ApplicationPackage:
    return ApplicationPackage(
        job_id=job_public_id,
        tailored_bullets=record.tailored_bullets,
        cover_letter_draft=record.cover_letter_draft,
        recruiter_message=record.recruiter_message,
        source_traceability_notes=record.source_traceability_notes,
        approval_status=record.approval_status,  # type: ignore[arg-type]
        eligibility_confirmed=record.eligibility_confirmed,
        eligibility_notes=record.eligibility_notes,
        decision_notes=record.decision_notes,
    )


def get_or_generate_application_package(db: Session, job_id: str, user_id: int) -> ApplicationPackage:
    job = _get_job_record(db, job_id)

    existing = (
        db.query(ApplicationPackageRecord)
        .filter(ApplicationPackageRecord.job_id == job.id, ApplicationPackageRecord.user_id == user_id)
        .first()
    )
    if existing is not None:
        return _record_to_package(existing, job_id)

    bullets, cover_letter, recruiter_message, notes = _mock_materials(job)
    candidate = _get_current_candidate(db, user_id)
    record = ApplicationPackageRecord(
        job_id=job.id,
        user_id=user_id,
        candidate_id=candidate.id if candidate else None,
        tailored_bullets=bullets,
        cover_letter_draft=cover_letter,
        recruiter_message=recruiter_message,
        source_traceability_notes=notes,
        approval_status="pending_review",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent generate call for the same
        # (job, user) pair — the unique index is what actually enforces
        # "one package per job per user" here; recover the winner's row
        # instead of surfacing an error.
        db.rollback()
        existing = (
            db.query(ApplicationPackageRecord)
            .filter(ApplicationPackageRecord.job_id == job.id, ApplicationPackageRecord.user_id == user_id)
            .first()
        )
        if existing is not None:
            return _record_to_package(existing, job_id)
        raise

    # Built from the values just inserted rather than db.refresh(record):
    # a session's default expire-on-commit behavior means reading record's
    # attributes right after commit() would trigger an implicit reload
    # anyway, so there's no free lunch from skipping an explicit refresh
    # unless the response is built from what's already known in Python.
    return ApplicationPackage(
        job_id=job_id,
        tailored_bullets=bullets,
        cover_letter_draft=cover_letter,
        recruiter_message=recruiter_message,
        source_traceability_notes=notes,
        approval_status="pending_review",
        eligibility_confirmed=False,
        eligibility_notes=None,
        decision_notes=None,
    )


def apply_approval(db: Session, job_id: str, user_id: int, request: ApprovalRequest) -> ApprovalResponse:
    job = _get_job_record(db, job_id)

    record = (
        db.query(ApplicationPackageRecord)
        .filter(ApplicationPackageRecord.job_id == job.id, ApplicationPackageRecord.user_id == user_id)
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generate application materials before recording an approval decision.",
        )

    if request.decision == "approved" and not request.eligibility_confirmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Confirm work authorization, salary, and eligibility before approving.",
        )

    record.approval_status = request.decision
    # Only an approval decision carries eligibility weight (the validation
    # above is what requires it to be true). Edit/reject never touch this
    # field — a previously-recorded confirmation must never be silently
    # downgraded to False as a side effect of an unrelated decision, e.g. a
    # caller that omits eligibility_confirmed and gets the schema's False
    # default.
    if request.decision == "approved":
        record.eligibility_confirmed = True
    # Notes are freeform reviewer input, not a confirmation, so they're
    # applied regardless of decision type — but only when the caller
    # actually sent the field. `model_fields_set` distinguishes "field
    # omitted from the request" (leave the stored value alone) from "field
    # explicitly sent as empty/null" (clear it) — both would otherwise look
    # identical as `None` once Pydantic applies its default, which is
    # exactly what silently cleared a field on every unrelated decision
    # before this fix.
    provided = request.model_fields_set
    if "eligibility_notes" in provided:
        record.eligibility_notes = request.eligibility_notes or None
    if "notes" in provided:
        record.decision_notes = request.notes or None
    db.commit()

    return ApprovalResponse(
        job_id=job_id,
        approval_status=request.decision,
        message=_APPROVAL_MESSAGES[request.decision],
    )

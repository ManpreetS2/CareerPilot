"""Approval Agent — human-in-the-loop review of tailored application materials.

Materials themselves stay mocked (`_mock_materials`) until Manpreet's Day 5
Application Material Agent replaces them — this module owns persistence and
the approve/edit/reject decision, not generation quality. A package is
generated once per job and then persisted; re-requesting it returns the same
stored package rather than silently regenerating (and discarding) reviewed
content.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord
from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse


def _get_job_record(db: Session, job_id: str) -> JobRecord:
    record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")
    return record


def _get_current_candidate(db: Session) -> Candidate | None:
    return db.query(Candidate).order_by(Candidate.id.desc()).first()


def _mock_materials(job: JobRecord) -> tuple[list[str], str, str, list[str]]:
    """Placeholder tailored materials. Real generation is Day 5 (Developer A)."""
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
    )


def get_or_generate_application_package(db: Session, job_id: str) -> ApplicationPackage:
    job = _get_job_record(db, job_id)

    existing = db.query(ApplicationPackageRecord).filter(ApplicationPackageRecord.job_id == job.id).first()
    if existing is not None:
        return _record_to_package(existing, job_id)

    bullets, cover_letter, recruiter_message, notes = _mock_materials(job)
    candidate = _get_current_candidate(db)
    record = ApplicationPackageRecord(
        job_id=job.id,
        candidate_id=candidate.id if candidate else None,
        tailored_bullets=bullets,
        cover_letter_draft=cover_letter,
        recruiter_message=recruiter_message,
        source_traceability_notes=notes,
        approval_status="pending_review",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_to_package(record, job_id)


def apply_approval(db: Session, job_id: str, request: ApprovalRequest) -> ApprovalResponse:
    job = _get_job_record(db, job_id)

    record = db.query(ApplicationPackageRecord).filter(ApplicationPackageRecord.job_id == job.id).first()
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
    record.eligibility_confirmed = request.eligibility_confirmed
    if request.eligibility_notes is not None:
        record.eligibility_notes = request.eligibility_notes
    db.commit()

    messages = {
        "approved": "Application package approved. Ready for the next step once Form Fill lands.",
        "edit_requested": "Edit requested. Package remains in review.",
        "rejected": "Application package rejected.",
    }
    return ApprovalResponse(
        job_id=job_id,
        approval_status=request.decision,
        message=messages[request.decision],
    )

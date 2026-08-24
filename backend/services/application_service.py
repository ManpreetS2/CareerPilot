"""Approval Agent — human-in-the-loop review of tailored application materials.

Grounded generation lives in
`backend.services.application_materials_agent.generate_grounded_application_materials`.
This module owns stored-package reads, the production generate path, and the
approve/edit/reject decision. A grounded package is created once per job per
user; re-requesting it returns the stored package rather than silently
regenerating reviewed content. Approved or edit-requested packages are never
replaced except through an explicit stale-reviewed discard by the owner.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import ApplicationPackageRecord, Candidate, JobRecord
from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse
from backend.services.application_materials_agent import (
    ApplicationMaterialsConflictError,
    ApplicationMaterialsGenerateFn,
    ApplicationMaterialsGenerator,
    ApplicationMaterialsGroundingError,
    ApplicationMaterialsParseError,
    MissingCandidateError,
    MissingFitScoreError,
    MissingJobIntelligenceError,
    StaleApplicationMaterialsError,
    generate_grounded_application_materials,
    is_grounded_package_record,
    is_package_ready_for_apply,
)
from backend.services.llm_client import (
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
)

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


class StoredMaterialsNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Stored application materials not found.")


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
        grounded=bool(getattr(record, "grounded", False)) and is_grounded_package_record(record),
    )


def _owned_package(db: Session, job: JobRecord, user_id: int) -> ApplicationPackageRecord | None:
    return (
        db.query(ApplicationPackageRecord)
        .filter(
            ApplicationPackageRecord.job_id == job.id,
            ApplicationPackageRecord.user_id == user_id,
        )
        .first()
    )


def get_stored_application_package(db: Session, job_id: str, user_id: int) -> ApplicationPackage:
    """Return a stored grounded package. Never generates, writes, or calls a provider."""
    job = _get_job_record(db, job_id)
    record = _owned_package(db, job, user_id)
    if record is None or not is_grounded_package_record(record):
        raise StoredMaterialsNotFoundError()
    current = _get_current_candidate(db, user_id)
    if current is not None and record.candidate_id != current.id:
        reviewed = record.approval_status in {"approved", "edit_requested"}
        raise StaleApplicationMaterialsError(reviewed=reviewed)
    return _record_to_package(record, job_id)


def get_or_generate_application_package(
    db: Session,
    job_id: str,
    user_id: int,
    *,
    generator: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator | None = None,
) -> ApplicationPackage:
    job = _get_job_record(db, job_id)
    try:
        generate_grounded_application_materials(db, job_id, user_id, generator=generator)
    except MissingJobIntelligenceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingCandidateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissingFitScoreError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApplicationMaterialsGroundingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApplicationMaterialsConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except StaleApplicationMaterialsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApplicationMaterialsParseError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Application materials output was not valid structured JSON.",
        ) from None
    except LLMConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application materials generation is not configured.",
        ) from None
    except (LLMProviderError, LLMEmptyResponseError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model request failed.",
        ) from None

    record = _owned_package(db, job, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Application materials could not be stored.",
        )
    return _record_to_package(record, job_id)


def discard_stale_reviewed_package(db: Session, job_id: str, user_id: int) -> dict[str, str]:
    """Owner-only explicit reset of reviewed materials that belong to a previous profile.

    Never calls a provider. Invalid state returns a sanitized conflict.
    """
    job = _get_job_record(db, job_id)
    record = _owned_package(db, job, user_id)
    current = _get_current_candidate(db, user_id)
    if (
        record is None
        or current is None
        or record.candidate_id == current.id
        or record.approval_status not in {"approved", "edit_requested"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reviewed materials for a previous profile are not available to discard.",
        )
    db.delete(record)
    db.commit()
    return {"status": "discarded"}


def apply_approval(db: Session, job_id: str, user_id: int, request: ApprovalRequest) -> ApprovalResponse:
    job = _get_job_record(db, job_id)

    record = _owned_package(db, job, user_id)
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

    if request.decision == "approved" and not is_package_ready_for_apply(db, record, user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This package isn't grounded in your current candidate profile. "
                "Regenerate application materials before approving."
            ),
        )

    record.approval_status = request.decision
    if request.decision == "approved":
        record.eligibility_confirmed = True
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

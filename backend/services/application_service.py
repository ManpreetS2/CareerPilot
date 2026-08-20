"""Application-package Day 1 mocks. No real generation yet."""

from __future__ import annotations

from backend.schemas.schemas import ApplicationPackage, ApprovalRequest, ApprovalResponse
from backend.services.job_service import get_job

_APPROVAL_STATE: dict[str, str] = {}


def mock_application_package(job_id: str) -> ApplicationPackage:
    job = get_job(job_id)
    status = _APPROVAL_STATE.get(job_id, "pending_review")
    return ApplicationPackage(
        job_id=job.id or job_id,
        tailored_bullets=[
            f"Built Python APIs relevant to {job.company}'s intern stack.",
            "Wrote SQL-backed features with tests and documented edge cases.",
            "Collaborated across frontend and backend on a shipped campus product.",
        ],
        cover_letter_draft=(
            f"Dear {job.company} hiring team,\n\n"
            f"I am applying for the {job.title} role. This is a Day 1 mock draft.\n"
        ),
        recruiter_message=(
            f"Hi, I'm interested in the {job.title} role at {job.company}. "
            "Happy to share a tailored resume."
        ),
        source_traceability_notes=[
            "Bullet 1 sourced from mock project Campus Connect (not parsed from a real resume).",
            "Day 1 placeholder — no evidence graph yet.",
        ],
        approval_status=status,  # type: ignore[arg-type]
    )


def apply_approval(job_id: str, request: ApprovalRequest) -> ApprovalResponse:
    get_job(job_id)
    _APPROVAL_STATE[job_id] = request.decision
    messages = {
        "approved": "Application package marked approved (mock).",
        "edit_requested": "Edit requested. Package remains in review (mock).",
        "rejected": "Application package rejected (mock).",
    }
    return ApprovalResponse(
        job_id=job_id,
        approval_status=request.decision,
        message=messages[request.decision],
    )

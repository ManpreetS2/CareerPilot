"""Typed pipeline stages for job analysis. Not an autonomous agent framework."""

from __future__ import annotations

from backend.schemas.job_requirements import PipelineStage, PipelineStatus

PIPELINE_STAGES: tuple[PipelineStage, ...] = (
    "discovered",
    "verified_open",
    "requirements_pending",
    "requirements_ready",
    "eligibility_ready",
    "fit_ready",
    "materials_ready",
    "review_required",
    "approved",
    "autofill_ready",
)


def initial_status(job_id: str) -> PipelineStatus:
    return PipelineStatus(job_id=job_id, stage="discovered")

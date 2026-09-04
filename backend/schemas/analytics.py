"""Read-only Application Conversion Analytics contracts.

Derived entirely from the append-only ApplicationEventRecord log plus current
job/match-score data. Never mutates state, never calls a provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FunnelStage = Literal[
    "saved",
    "materials_generated",
    "materials_approved",
    "applied",
    "interviewing",
    "offer",
]

FUNNEL_STAGE_LABELS: dict[FunnelStage, str] = {
    "saved": "Saved",
    "materials_generated": "Materials generated",
    "materials_approved": "Materials approved",
    "applied": "Applied",
    "interviewing": "Interviewing",
    "offer": "Offer",
}


class FunnelStep(BaseModel):
    stage: FunnelStage
    label: str
    jobs_count: int
    conversion_from_previous: float | None = None


class BreakdownBucket(BaseModel):
    label: str
    applied_count: int
    total_count: int
    applied_rate: float | None
    small_sample: bool


class ApplicationAnalyticsSummary(BaseModel):
    generated_at: datetime
    funnel: list[FunnelStep] = Field(default_factory=list)
    rejected_count: int = 0
    withdrawn_count: int = 0
    median_days_saved_to_applied: float | None = None
    median_days_applied_to_interviewing: float | None = None
    by_source: list[BreakdownBucket] = Field(default_factory=list)
    by_match_score_band: list[BreakdownBucket] = Field(default_factory=list)
    notice: str | None = None

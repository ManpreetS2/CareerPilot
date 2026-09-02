"""Read-only Career Growth / Skills Gap contracts.

Advisory only. Never feeds Fit, ranking, eligibility, or match tier.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EvidenceState = Literal["satisfied", "partial", "unknown", "not_satisfied"]
PriorityLabel = Literal["high", "medium", "low"]
SkillImportance = Literal["required", "preferred"]


class CareerGrowthJobRef(BaseModel):
    job_id: str
    title: str
    company: str
    importance: SkillImportance
    evidence_state: EvidenceState
    saved: bool


class SkillGrowthItem(BaseModel):
    canonical_key: str
    label: str
    jobs_count: int
    denominator: int
    required_count: int
    preferred_count: int
    satisfied_count: int = 0
    partial_count: int = 0
    unknown_count: int = 0
    not_satisfied_count: int = 0
    candidate_evidence_state: EvidenceState
    candidate_evidence_count: int = 0
    priority: PriorityLabel
    reason: str
    suggested_action: str
    related_jobs: list[CareerGrowthJobRef] = Field(default_factory=list)


class CareerGrowthSummary(BaseModel):
    jobs_considered: int
    jobs_with_current_evidence: int
    saved_jobs_considered: int
    matched_jobs_considered: int
    stale_jobs_excluded: int
    unavailable_jobs_excluded: int
    generated_at: datetime
    skill_gaps: list[SkillGrowthItem] = Field(default_factory=list)
    strengths: list[SkillGrowthItem] = Field(default_factory=list)
    notice: str | None = None

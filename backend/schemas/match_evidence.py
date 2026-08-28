"""Persisted Verified Match explainability contracts.

Factors and evaluations point at evidence IDs. Exact posting/candidate text
lives once in the evidence map — never duplicated as giant blobs on every factor.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.job_requirements import RequirementStatus
from backend.schemas.schemas import MatchScore

EVIDENCE_VERSION = 1

FactorCategory = Literal[
    "skill",
    "experience",
    "responsibility",
    "education",
    "enrollment",
    "graduation",
    "academic_year",
    "work_authorization",
    "sponsorship",
    "location",
    "work_mode",
    "employment_type",
    "salary",
    "preference",
    "certification",
    "license",
    "other_requirement",
]

FactorSection = Literal[
    "required_skills",
    "preferred_skills",
    "qualifications",
    "eligibility",
    "work_location",
    "preferences",
]

EvidenceSourceType = Literal[
    "candidate_resume",
    "candidate_profile",
    "candidate_project",
    "candidate_experience",
    "candidate_education",
    "candidate_preference",
    "job_posting",
    "job_requirement",
]


class EvidenceRef(BaseModel):
    id: str
    source_type: EvidenceSourceType
    source_entity_id: str | None = None
    field: str | None = None
    exact_text: str
    locator: str | None = None


class MatchFactor(BaseModel):
    id: str
    job_id: str
    category: FactorCategory
    section: FactorSection
    label: str
    importance: str | None = None
    status: RequirementStatus
    score_contribution: float | None = None
    max_contribution: float | None = None
    rule_id: str
    rule_version: str
    explanation: str
    job_evidence_refs: list[str] = Field(default_factory=list)
    candidate_evidence_refs: list[str] = Field(default_factory=list)
    requirement_id: str | None = None
    group_id: str | None = None
    hard_blocker: bool = False
    scoring_effect: str | None = None


class RequirementEvaluation(BaseModel):
    requirement_id: str
    result: RequirementStatus
    candidate_evidence_refs: list[str] = Field(default_factory=list)
    job_evidence_refs: list[str] = Field(default_factory=list)
    explanation: str
    rule_id: str
    group_id: str | None = None


class GroupEvaluation(BaseModel):
    group_id: str
    operator: Literal["any_of", "all_of"]
    text: str
    status: RequirementStatus
    importance: str | None = None
    job_evidence_refs: list[str] = Field(default_factory=list)
    branch_ids: list[str] = Field(default_factory=list)
    explanation: str
    hard_blocker: bool = False


class MatchEvidenceProvenance(BaseModel):
    scoring_version: int
    evidence_version: int = EVIDENCE_VERSION
    score_kind: str | None = None
    candidate_fingerprint: str | None = None
    preference_fingerprint: str | None = None
    requirement_fingerprint: str | None = None
    stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)


class MatchEvidenceResponse(BaseModel):
    job_id: str
    score: MatchScore | None = None
    full_evidence: bool = False
    notice: str | None = None
    provenance: MatchEvidenceProvenance
    factors: list[MatchFactor] = Field(default_factory=list)
    evaluations: list[RequirementEvaluation] = Field(default_factory=list)
    groups: list[GroupEvaluation] = Field(default_factory=list)
    evidence: dict[str, EvidenceRef] = Field(default_factory=dict)

"""Drop extracted requirements that cannot be found in the stored posting."""

from __future__ import annotations

from backend.schemas.job_requirements import JobRequirementProfile, Requirement
from backend.services.job_content import normalize_posting_text


def evidence_is_grounded(evidence_text: str | None, posting: str) -> bool:
    evidence = normalize_posting_text(evidence_text)
    source = normalize_posting_text(posting)
    if len(evidence) < 12 or not source:
        return False
    return evidence in source


def keep_grounded_requirement(requirement: Requirement, posting: str) -> bool:
    return evidence_is_grounded(requirement.evidence_text, posting)


def filter_profile_to_grounded(profile: JobRequirementProfile, posting: str) -> JobRequirementProfile:
    kept_ids = {item.id for item in profile.requirements if keep_grounded_requirement(item, posting)}
    profile.requirements = [item for item in profile.requirements if item.id in kept_ids]
    profile.requirement_groups = [
        group
        for group in profile.requirement_groups
        if evidence_is_grounded(group.evidence_text, posting)
        and all(rid in kept_ids for rid in group.requirement_ids)
    ]
    return profile

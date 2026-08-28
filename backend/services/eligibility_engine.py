"""Compare grounded candidate facts to a JobRequirementProfile.

Never guesses missing candidate facts. Unstated job requirements are not
failures.
"""

from __future__ import annotations

from datetime import date

from backend.db.models import Candidate, TargetPreference
from backend.schemas.job_requirements import (
    EligibilityReport,
    GroupComparison,
    JobRequirementProfile,
    Requirement,
    RequirementComparison,
    RequirementStatus,
)

_ENROLLED_YES = {"yes", "true", "1", "currently enrolled"}
_ENROLLED_NO = {"no", "false", "0"}
_FINAL_YEARS = {"senior", "final_year"}


def _parse_date(value: str | None) -> date | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if len(raw) >= 7 and raw[4] == "-":
        try:
            return date(int(raw[:4]), int(raw[5:7]), 1)
        except ValueError:
            return None
    if raw[:4].isdigit():
        try:
            return date(int(raw[:4]), 6, 1)
        except ValueError:
            return None
    return None


def _graduation_date(candidate: Candidate, preferences: TargetPreference | None) -> date | None:
    if preferences and getattr(preferences, "expected_graduation", None):
        parsed = _parse_date(preferences.expected_graduation)
        if parsed:
            return parsed
    for edu in candidate.education or []:
        if not isinstance(edu, dict):
            continue
        parsed = _parse_date(str(edu.get("graduation_year") or edu.get("end_date") or ""))
        if parsed:
            return parsed
    return None


def _enrolled(preferences: TargetPreference | None) -> bool | None:
    if preferences is None:
        return None
    value = (preferences.currently_enrolled_in_program or "").strip().lower()
    if value in _ENROLLED_YES:
        return True
    if value in _ENROLLED_NO:
        return False
    return None


def _academic_year(preferences: TargetPreference | None) -> str | None:
    if preferences is None:
        return None
    year = getattr(preferences, "academic_year", None)
    if isinstance(year, str) and year.strip():
        return year.strip().lower()
    return None


def _months_between(later: date, earlier: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def evaluate_requirement(
    requirement: Requirement,
    candidate: Candidate,
    preferences: TargetPreference | None,
    as_of: date,
) -> RequirementComparison:
    kind = (requirement.structured_condition or {}).get("kind")
    if kind == "currently_enrolled":
        enrolled = _enrolled(preferences)
        if enrolled is True:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="Currently enrolled.")
        if enrolled is False:
            return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Not currently enrolled.")
        return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Enrollment status is not on the profile.")

    if kind == "final_year":
        year = _academic_year(preferences)
        if year in _FINAL_YEARS:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="Marked as final-year / senior.")
        if year in {"freshman", "sophomore", "junior"}:
            return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Not in the final year of the program.")
        enrolled = _enrolled(preferences)
        grad = _graduation_date(candidate, preferences)
        if enrolled is True and grad and 0 <= _months_between(grad, as_of) <= 12:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="Enrolled and graduating within 12 months.")
        if year or enrolled is False:
            return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Not evidenced as a final-year student.")
        return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Academic year is not on the profile.")

    if kind == "recent_graduate":
        months = int((requirement.structured_condition or {}).get("months") or 12)
        grad = _graduation_date(candidate, preferences)
        enrolled = _enrolled(preferences)
        if grad is None:
            return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Graduation date is not on the profile.")
        delta = _months_between(as_of, grad)
        if 0 <= delta <= months:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason=f"Graduated {delta} months ago.")
        if enrolled is True and delta < 0:
            return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Still pursuing the degree; not a recent graduate.")
        return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Graduation is outside the recent-graduate window.")

    if kind == "sponsorship":
        available = (requirement.structured_condition or {}).get("available")
        needs = preferences.sponsorship_required if preferences else None
        if available is False and needs is True:
            return RequirementComparison(requirement_id=requirement.id, status="not_satisfied", reason="Posting does not offer sponsorship.")
        if available is False and needs is False:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="No sponsorship needed.")
        if available is True:
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="Sponsorship is stated as available.")
        if needs is None:
            return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Candidate sponsorship need is not stated.")
        return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="No sponsorship conflict.")

    if kind == "degree":
        return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Degree completion was not independently verified here.")

    if kind == "equivalent_experience":
        return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Equivalent experience was not independently verified here.")

    if kind == "skill":
        from backend.services.analysis_service import candidate_covers_skill

        name = str((requirement.structured_condition or {}).get("name") or requirement.text or "").strip()
        if not name:
            return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Skill name was not structured.")
        if candidate_covers_skill(candidate, name):
            return RequirementComparison(
                requirement_id=requirement.id,
                status="satisfied",
                reason="Grounded candidate evidence covers this skill.",
            )
        return RequirementComparison(
            requirement_id=requirement.id,
            status="unknown",
            reason="No supporting candidate evidence found.",
        )

    if kind == "work_authorization":
        auth = (preferences.work_authorization or "").strip().lower() if preferences else ""
        if not auth:
            return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Work authorization is not on the profile.")
        region = str((requirement.structured_condition or {}).get("region") or "us")
        if region == "us" and any(token in auth for token in ("us", "united states", "citizen", "authorized")):
            return RequirementComparison(requirement_id=requirement.id, status="satisfied", reason="Profile states US work authorization.")
        return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="Work authorization could not be compared without guessing.")

    return RequirementComparison(requirement_id=requirement.id, status="unknown", reason="No structured comparison for this requirement.")


def _combine_group(statuses: list[RequirementStatus], operator: str) -> RequirementStatus:
    if operator == "any_of":
        if any(item == "satisfied" for item in statuses):
            return "satisfied"
        if all(item == "not_satisfied" for item in statuses):
            return "not_satisfied"
        if any(item == "unknown" for item in statuses) and not any(item == "satisfied" for item in statuses):
            return "unknown"
        return "not_satisfied"
    if any(item == "not_satisfied" for item in statuses):
        return "not_satisfied"
    if any(item == "unknown" for item in statuses):
        return "unknown"
    return "satisfied"


def evaluate_eligibility(
    profile: JobRequirementProfile,
    candidate: Candidate,
    preferences: TargetPreference | None,
    *,
    as_of: date | None = None,
) -> EligibilityReport:
    when = as_of or date.today()
    by_id = {item.id: item for item in profile.requirements}
    comparisons = [
        evaluate_requirement(item, candidate, preferences, when) for item in profile.requirements
    ]
    cmp_by_id = {item.requirement_id: item for item in comparisons}
    groups: list[GroupComparison] = []
    for group in profile.requirement_groups:
        statuses = [cmp_by_id[rid].status for rid in group.requirement_ids if rid in cmp_by_id]
        status = _combine_group(statuses, group.operator)
        groups.append(GroupComparison(group_id=group.id, status=status, reason=group.text))

    blockers: list[str] = []
    watchouts: list[str] = []
    hard_unknown = False
    hard_fail = False

    for group, result in zip(profile.requirement_groups, groups):
        if group.importance != "hard_required":
            continue
        if result.status == "not_satisfied":
            hard_fail = True
            blockers.append(group.text)
        elif result.status == "unknown":
            hard_unknown = True
            watchouts.append(f"Could not evaluate: {group.text}")

    grouped_ids = {rid for group in profile.requirement_groups for rid in group.requirement_ids}
    for requirement, comparison in zip(profile.requirements, comparisons):
        if requirement.id in grouped_ids:
            continue
        if requirement.importance not in {"hard_required", "required"}:
            continue
        if requirement.structured_condition and requirement.structured_condition.get("kind") == "sponsorship":
            if comparison.status == "not_satisfied":
                hard_fail = True
                blockers.append(requirement.text)
            continue
        if comparison.status == "not_satisfied" and requirement.importance == "hard_required":
            hard_fail = True
            blockers.append(requirement.text)
        elif comparison.status == "unknown" and requirement.importance == "hard_required":
            hard_unknown = True
            watchouts.append(f"Could not evaluate: {requirement.text}")

    if not any(item.structured_condition and item.structured_condition.get("kind") == "sponsorship" for item in profile.requirements):
        watchouts.append("Work authorization / sponsorship not stated.")

    if hard_fail:
        status = "likely_ineligible"
    elif hard_unknown:
        status = "eligibility_uncertain"
    else:
        status = "likely_eligible"

    return EligibilityReport(
        status=status,
        comparisons=comparisons,
        groups=groups,
        watchouts=watchouts,
        blockers=blockers,
    )

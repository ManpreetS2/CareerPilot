"""Build and read persisted Verified Match evidence.

Deterministic. No LLM. Evidence text is copied from stored candidate fields
or the canonical employer posting — never invented.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import (
    Candidate,
    JobRecord,
    MatchEvidenceRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.schemas.job_requirements import (
    EligibilityReport,
    JobRequirementProfile,
    Requirement,
    RequirementComparison,
    RequirementStatus,
)
from backend.schemas.match_evidence import (
    EVIDENCE_VERSION,
    EvidenceRef,
    FactorCategory,
    FactorSection,
    GroupEvaluation,
    MatchEvidenceProvenance,
    MatchEvidenceResponse,
    MatchFactor,
    RequirementEvaluation,
)
from backend.schemas.schemas import MatchScore
from backend.services.analysis_service import (
    JobNotFoundError,
    ScoreBreakdown,
    StoredScoreNotFoundError,
    _record_to_match_score,
    load_job,
    load_preferences,
    skill_concepts_in_label,
)
from backend.services.candidate_provenance import fingerprint_for_candidate, hash_canonical
from backend.services.fit_v2 import QUAL_PREFERRED, QUAL_REQUIRED_SKILLS
from backend.services.job_requirement_extractor import load_requirement_profile

logger = logging.getLogger(__name__)

PRELIMINARY_NOTICE = "Full requirement evidence has not been verified yet."
NOT_SATISFIED_EXPLANATION = "Evidence indicates this requirement is not met."
UNKNOWN_EXPLANATION = "CareerPilot does not have enough evidence to verify this requirement."
MISSING_CANDIDATE_EVIDENCE = UNKNOWN_EXPLANATION
STALE_NOTICE = "This evidence is stale. Calculate Fit again to refresh it."
UNSTORED_NOTICE = "Evidence for this score is not stored yet. Calculate Fit to generate it."
_JOB_SOURCE_TYPES = frozenset({"job_posting", "job_requirement"})
_CANDIDATE_SOURCE_TYPES = frozenset(
    {
        "candidate_resume",
        "candidate_profile",
        "candidate_project",
        "candidate_experience",
        "candidate_education",
        "candidate_preference",
    }
)

_CATEGORY_SECTION: dict[str, FactorSection] = {
    "skill": "required_skills",
    "experience": "qualifications",
    "responsibility": "qualifications",
    "education": "qualifications",
    "certification": "qualifications",
    "license": "qualifications",
    "enrollment": "eligibility",
    "graduation": "eligibility",
    "academic_year": "eligibility",
    "work_authorization": "eligibility",
    "sponsorship": "eligibility",
    "location": "work_location",
    "work_mode": "work_location",
    "employment_type": "preferences",
    "salary": "preferences",
    "preference": "preferences",
    "other_requirement": "qualifications",
}

_KIND_CATEGORY: dict[str, FactorCategory] = {
    "skill": "skill",
    "currently_enrolled": "enrollment",
    "final_year": "academic_year",
    "recent_graduate": "graduation",
    "sponsorship": "sponsorship",
    "degree": "education",
    "equivalent_experience": "experience",
    "work_authorization": "work_authorization",
}

_KIND_RULE: dict[str, tuple[str, str]] = {
    "skill": ("required_skills_v2", "v2"),
    "currently_enrolled": ("enrollment_eligibility_v1", "v1"),
    "final_year": ("graduation_eligibility_v1", "v1"),
    "recent_graduate": ("graduation_eligibility_v1", "v1"),
    "sponsorship": ("sponsorship_eligibility_v1", "v1"),
    "degree": ("education_eligibility_v1", "v1"),
    "work_authorization": ("work_authorization_v1", "v1"),
    "equivalent_experience": ("experience_responsibility_v2", "v2"),
}


class MatchEvidenceStore:
    def __init__(self) -> None:
        self.evidence: dict[str, EvidenceRef] = {}

    def add(
        self,
        *,
        source_type: str,
        exact_text: str,
        source_entity_id: str | None = None,
        field: str | None = None,
        locator: str | None = None,
    ) -> str:
        text = (exact_text or "").strip()
        if not text:
            return ""
        digest = hashlib.sha256(
            f"{source_type}|{source_entity_id or ''}|{field or ''}|{text}".encode("utf-8")
        ).hexdigest()[:16]
        ref_id = f"ev_{digest}"
        if ref_id not in self.evidence:
            self.evidence[ref_id] = EvidenceRef(
                id=ref_id,
                source_type=source_type,  # type: ignore[arg-type]
                source_entity_id=source_entity_id,
                field=field,
                exact_text=text,
                locator=locator,
            )
        return ref_id


def preference_fingerprint(preferences: TargetPreference | None) -> str | None:
    if preferences is None:
        return None
    return hash_canonical(
        {
            "academic_year": preferences.academic_year,
            "currently_enrolled_in_program": preferences.currently_enrolled_in_program,
            "expected_graduation": preferences.expected_graduation,
            "preferred_locations": list(preferences.preferred_locations or []),
            "relocation_willingness": preferences.relocation_willingness,
            "remote_preference": preferences.remote_preference,
            "salary_min": preferences.salary_min,
            "sponsorship_required": preferences.sponsorship_required,
            "work_authorization": preferences.work_authorization,
            "work_mode_preferences": list(preferences.work_mode_preferences or []),
        }
    )


def _line_with(text: str, needle: str) -> str | None:
    if not text or not needle:
        return None
    lowered = needle.lower()
    for raw in re.split(r"[\n.]", text):
        line = raw.strip()
        if line and lowered in line.lower():
            return line
    if lowered in text.lower():
        return text.strip()[:280]
    return None


def _stringify_item(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, list):
        return "\n".join(_stringify_item(part) for part in item if part)
    if isinstance(item, dict):
        parts: list[str] = []
        for key in ("name", "title", "company", "institution", "degree", "field", "description", "summary"):
            value = item.get(key)
            if value:
                parts.append(str(value))
        for key in ("highlights", "technologies", "skills"):
            value = item.get(key)
            if isinstance(value, list):
                parts.extend(str(part) for part in value if part)
            elif value:
                parts.append(str(value))
        for key in ("graduation_year", "end_date", "start_date"):
            value = item.get(key)
            if value:
                parts.append(str(value))
        return "\n".join(parts)
    return str(item)


def _blob_covers_skill(blob: str, skill: str) -> bool:
    if not blob.strip() or not skill.strip():
        return False
    want = set(skill_concepts_in_label(skill))
    if want:
        return bool(want & set(skill_concepts_in_label(blob)))
    return skill.strip().lower() in blob.lower()


def _snippet_for_skill(blob: str, skill: str) -> str | None:
    if not _blob_covers_skill(blob, skill):
        return None
    concepts = skill_concepts_in_label(skill)
    needle = concepts[0] if len(concepts) == 1 else skill
    return _line_with(blob, needle) or blob.strip()[:280]


def _find_one_skill_ref(store: MatchEvidenceStore, candidate: Candidate, needle: str) -> str:
    if not needle.strip():
        return ""
    for index, project in enumerate(candidate.projects or []):
        blob = _stringify_item(project)
        line = _snippet_for_skill(blob, needle)
        if not line:
            continue
        name = project.get("name") if isinstance(project, dict) else None
        return store.add(
            source_type="candidate_project",
            exact_text=line,
            source_entity_id=str(name or index),
            field="projects",
            locator=f"projects[{index}]",
        )
    for index, role in enumerate(candidate.experience or []):
        blob = _stringify_item(role)
        line = _snippet_for_skill(blob, needle)
        if not line:
            continue
        title = role.get("title") if isinstance(role, dict) else None
        return store.add(
            source_type="candidate_experience",
            exact_text=line,
            source_entity_id=str(title or index),
            field="experience",
            locator=f"experience[{index}]",
        )
    for index, item in enumerate(candidate.education or []):
        blob = _stringify_item(item)
        line = _snippet_for_skill(blob, needle)
        if not line:
            continue
        return store.add(
            source_type="candidate_education",
            exact_text=line,
            source_entity_id=str(index),
            field="education",
            locator=f"education[{index}]",
        )
    for index, cert in enumerate(candidate.certifications or []):
        blob = _stringify_item(cert)
        line = _snippet_for_skill(blob, needle)
        if not line:
            continue
        return store.add(
            source_type="candidate_profile",
            exact_text=line,
            source_entity_id=str(index),
            field="certifications",
            locator=f"certifications[{index}]",
        )
    for index, listed in enumerate(candidate.skills or []):
        if not _blob_covers_skill(str(listed), needle):
            continue
        return store.add(
            source_type="candidate_profile",
            exact_text=str(listed),
            source_entity_id="skills",
            field="skills",
            locator=f"skills[{index}]",
        )
    return ""


def _find_candidate_skill_refs(store: MatchEvidenceStore, candidate: Candidate, skill: str) -> list[str]:
    needle = skill.strip()
    if not needle:
        return []
    concepts = skill_concepts_in_label(needle)
    needles = concepts or [needle]
    refs: list[str] = []
    seen: set[str] = set()
    for item in needles:
        ref = _find_one_skill_ref(store, candidate, item)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _education_refs(store: MatchEvidenceStore, candidate: Candidate) -> list[str]:
    refs: list[str] = []
    for index, item in enumerate(candidate.education or []):
        blob = _stringify_item(item)
        if not blob.strip():
            continue
        refs.append(
            store.add(
                source_type="candidate_education",
                exact_text=blob.replace("\n", " · "),
                source_entity_id=str(index),
                field="education",
                locator=f"education[{index}]",
            )
        )
    return refs


def _preference_ref(store: MatchEvidenceStore, preferences: TargetPreference | None, field: str) -> str:
    if preferences is None:
        return ""
    value = getattr(preferences, field, None)
    if value is None or value == "" or value == []:
        return ""
    text = ", ".join(str(part) for part in value) if isinstance(value, list) else str(value)
    return store.add(
        source_type="candidate_preference",
        exact_text=text,
        source_entity_id=field,
        field=field,
        locator=f"preferences.{field}",
    )


def _job_requirement_ref(store: MatchEvidenceStore, requirement: Requirement) -> str:
    text = (requirement.evidence_text or requirement.text or "").strip()
    return store.add(
        source_type="job_requirement",
        exact_text=text,
        source_entity_id=requirement.id,
        field="evidence_text",
        locator=requirement.id,
    )


def _job_posting_ref(store: MatchEvidenceStore, job: JobRecord, needle: str, entity_id: str) -> str:
    line = _line_with(job.description or "", needle) or needle
    return store.add(
        source_type="job_posting",
        exact_text=line,
        source_entity_id=entity_id,
        field="description",
        locator=entity_id,
    )


def _skill_group_key(label: str) -> tuple[str, str]:
    concepts = skill_concepts_in_label(label)
    if len(concepts) == 1:
        return ("skill", concepts[0].lower())
    if len(concepts) >= 2:
        return ("skills", "|".join(sorted(item.lower() for item in concepts)))
    return ("phrase", re.sub(r"\s+", " ", label.strip().lower()))


def _unique_skill_labels(labels: list[str]) -> list[str]:
    seen: set[tuple[str, str]] = set()
    out: list[str] = []
    for label in labels:
        key = _skill_group_key(label)
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _label_matches_bucket(label: str, bucket: list[str]) -> bool:
    key = _skill_group_key(label)
    return any(_skill_group_key(item) == key for item in bucket)


def _combine_skill_status(statuses: list[RequirementStatus]) -> RequirementStatus:
    if any(item == "satisfied" for item in statuses):
        return "satisfied"
    if any(item == "partially_satisfied" for item in statuses):
        return "partially_satisfied"
    if statuses and all(item == "not_satisfied" for item in statuses):
        return "not_satisfied"
    return "unknown"


def _display_skill_label(kind: str, labels: list[str]) -> str:
    if kind == "skill":
        concepts = skill_concepts_in_label(labels[0])
        return concepts[0] if concepts else labels[0]
    if kind == "skills":
        return min(labels, key=len)
    return labels[0]


def _importance_bucket(value: str | None) -> str:
    if value in ("required", "hard_required"):
        return "required"
    return "preferred"


def _count_by_status(
    labels: list[str], matched: list[str], partial: list[str], missing: list[str]
) -> tuple[int, int, int, int]:
    sat = part = miss = unk = 0
    for label in _unique_skill_labels(labels):
        status = _status_from_membership(label, matched, partial, missing)
        if status == "satisfied":
            sat += 1
        elif status == "partially_satisfied":
            part += 1
        elif status == "not_satisfied":
            miss += 1
        else:
            unk += 1
    return sat, part, miss, unk


def _component_status(
    ratio: float | None,
    labels: list[str],
    matched: list[str],
    partial: list[str],
    missing: list[str],
) -> RequirementStatus:
    """Component status follows the Fit V2 ratio. Empty dimensions are N/A, never Satisfied 0/max."""
    if ratio is None:
        return "not_applicable"
    unique = _unique_skill_labels(labels)
    if not unique:
        return "not_applicable"
    if ratio >= 0.999:
        return "satisfied"
    if ratio <= 0.001:
        return "not_satisfied"
    return "partially_satisfied"


def _align_status_to_contribution(
    status: RequirementStatus,
    contribution: float | None,
    max_contribution: float | None,
) -> RequirementStatus:
    if max_contribution is None or contribution is None:
        return status
    if max_contribution <= 0:
        return "not_applicable"
    if contribution <= 0.001:
        if status == "satisfied":
            return "not_satisfied"
        return status
    if contribution >= max_contribution - 0.001:
        if status == "not_satisfied":
            return "satisfied"
        return status
    if status in {"satisfied", "not_satisfied"}:
        return "partially_satisfied"
    return status


def _find_skill_requirement(
    profile: JobRequirementProfile | None,
    labels: list[str],
    importance: str,
) -> Requirement | None:
    if profile is None:
        return None
    target = {_skill_group_key(item) for item in labels}
    want = _importance_bucket(importance)
    for requirement in profile.requirements:
        kind = (requirement.structured_condition or {}).get("kind")
        if kind != "skill":
            continue
        if _importance_bucket(requirement.importance) != want:
            continue
        name = str((requirement.structured_condition or {}).get("name") or requirement.text)
        if _skill_group_key(name) in target:
            return requirement
    return None


def _append_fit_skill_factors(
    *,
    store: MatchEvidenceStore,
    factors: list[MatchFactor],
    job: JobRecord,
    candidate: Candidate,
    profile: JobRequirementProfile | None,
    breakdown: ScoreBreakdown,
    matched: list[str],
    partial: list[str],
    missing: list[str],
) -> set[tuple[str, tuple[str, str]]]:
    public_id = job.public_id
    required_labels = _unique_skill_labels(list(breakdown.required_skill_labels or []))
    preferred_labels = _unique_skill_labels(list(breakdown.preferred_skill_labels or []))
    required_ratio = breakdown.skill_required_ratio
    preferred_ratio = breakdown.skill_preferred_ratio
    max_required = round(QUAL_REQUIRED_SKILLS * 100, 1)
    max_preferred = round(QUAL_PREFERRED * 100, 1)
    represented: set[tuple[str, tuple[str, str]]] = set()

    if required_ratio is None:
        factors.append(
            MatchFactor(
                id="factor_required_skills",
                job_id=public_id,
                category="skill",
                section="required_skills",
                label="Required skills",
                importance="required",
                status="not_applicable",
                score_contribution=None,
                max_contribution=None,
                rule_id="required_skills_v2",
                rule_version="v2",
                explanation=(
                    "No required technical skills were structured for Fit V2. "
                    "Preferred and plus skills do not count toward the Required Skills component."
                ),
                scoring_effect=(
                    "This posting has no required-skill dimension. Preferred skills do not "
                    "contribute to Required Skills."
                ),
            )
        )
    else:
        sat, _part, _miss, _unk = _count_by_status(required_labels, matched, partial, missing)
        status = _component_status(required_ratio, required_labels, matched, partial, missing)
        if status == "not_applicable":
            contribution = None
            max_contribution = None
        else:
            contribution = round(max_required * required_ratio, 1)
            max_contribution = max_required
            status = _align_status_to_contribution(status, contribution, max_contribution)
        factors.append(
            MatchFactor(
                id="factor_required_skills",
                job_id=public_id,
                category="skill",
                section="required_skills",
                label="Required skills",
                importance="required",
                status=status,
                score_contribution=contribution,
                max_contribution=max_contribution,
                rule_id="required_skills_v2",
                rule_version="v2",
                explanation=(
                    f"{sat} / {len(required_labels)} required skills matched."
                    if required_labels
                    else "Required skills were scored by Fit V2."
                ),
                scoring_effect=(
                    "This is the Fit V2 Required Skills component. Unmatched required skills "
                    "earn 0 credit here; individual skills without candidate evidence stay Unknown."
                    if required_labels
                    else "This is the Fit V2 Required Skills component."
                ),
            )
        )

    if preferred_ratio is None:
        if preferred_labels:
            factors.append(
                MatchFactor(
                    id="factor_preferred_skills",
                    job_id=public_id,
                    category="skill",
                    section="preferred_skills",
                    label="Preferred skills",
                    importance="preferred",
                    status="not_applicable",
                    rule_id="preferred_skills_v2",
                    rule_version="v2",
                    explanation="Preferred skills were listed but Fit V2 did not score a preferred-skill dimension.",
                    scoring_effect="Does not contribute to the Required Skills component.",
                )
            )
    else:
        sat, _part, _miss, _unk = _count_by_status(preferred_labels, matched, partial, missing)
        status = _component_status(preferred_ratio, preferred_labels, matched, partial, missing)
        if status == "not_applicable":
            contribution = None
            max_contribution = None
        else:
            contribution = round(max_preferred * preferred_ratio, 1)
            max_contribution = max_preferred
            status = _align_status_to_contribution(status, contribution, max_contribution)
        factors.append(
            MatchFactor(
                id="factor_preferred_skills",
                job_id=public_id,
                category="skill",
                section="preferred_skills",
                label="Preferred skills",
                importance="preferred",
                status=status,
                score_contribution=contribution,
                max_contribution=max_contribution,
                rule_id="preferred_skills_v2",
                rule_version="v2",
                explanation=(
                    f"{sat} / {len(preferred_labels)} preferred or stack skills matched. "
                    "These do not count toward the Required Skills component."
                ),
                scoring_effect="Contributes to the Fit V2 preferred-skill dimension, not Required Skills.",
            )
        )

    def _emit_rows(labels: list[str], *, importance: str, section: FactorSection, scoring_effect: str, rule_id: str) -> None:
        buckets: dict[tuple[str, str], list[str]] = {}
        for label in labels:
            buckets.setdefault(_skill_group_key(label), []).append(label)
        for key, group_labels in buckets.items():
            represented.add((_importance_bucket(importance), key))
            status = _combine_skill_status(
                [_status_from_membership(item, matched, partial, missing) for item in group_labels]
            )
            display = _display_skill_label(key[0], group_labels)
            requirement = _find_skill_requirement(profile, group_labels, importance)
            job_refs: list[str] = []
            if requirement:
                ref = _job_requirement_ref(store, requirement)
                if ref:
                    job_refs.append(ref)
            for label in group_labels:
                job_refs.append(_job_posting_ref(store, job, label, f"skill:{label}"))
            job_refs = list(dict.fromkeys(job_refs))
            cand_refs = _find_candidate_skill_refs(store, candidate, display)
            if not cand_refs:
                for label in group_labels:
                    cand_refs = _find_candidate_skill_refs(store, candidate, label)
                    if cand_refs:
                        break
            if status == "not_satisfied":
                explanation = NOT_SATISFIED_EXPLANATION
                cand_refs = []
            elif status == "unknown" or not cand_refs:
                status = "unknown"
                explanation = UNKNOWN_EXPLANATION
                cand_refs = []
            else:
                extra = ""
                if any(item.strip().lower() != display.strip().lower() for item in group_labels):
                    extra = " Employer wording: " + "; ".join(dict.fromkeys(group_labels)) + "."
                if status == "partially_satisfied":
                    explanation = f"Partial skill match against stored candidate evidence.{extra}"
                else:
                    explanation = f"Exact skill match against stored candidate evidence.{extra}"
            identity = display.lower()
            factors.append(
                MatchFactor(
                    id=f"factor_skill_{importance}_{hashlib.sha256(identity.encode()).hexdigest()[:10]}",
                    job_id=public_id,
                    category="skill",
                    section=section,
                    label=display,
                    importance=importance,
                    status=status,
                    rule_id=rule_id,
                    rule_version="v2",
                    explanation=explanation,
                    job_evidence_refs=job_refs,
                    candidate_evidence_refs=cand_refs,
                    requirement_id=requirement.id if requirement else None,
                    scoring_effect=scoring_effect,
                )
            )

    _emit_rows(
        required_labels,
        importance="required",
        section="required_skills",
        scoring_effect="Contributes to the Required Skills component. Individual skills are not assigned separate point values.",
        rule_id="required_skills_v2",
    )
    _emit_rows(
        preferred_labels,
        importance="preferred",
        section="preferred_skills",
        scoring_effect="Does not contribute to the Required Skills component. Contributes to Preferred qualifications when Fit V2 scores preferred skills.",
        rule_id="preferred_skills_v2",
    )
    return represented


def _status_from_membership(label: str, matched: list[str], partial: list[str], missing: list[str]) -> RequirementStatus:
    if _label_matches_bucket(label, matched):
        return "satisfied"
    if _label_matches_bucket(label, partial):
        return "partially_satisfied"
    if _label_matches_bucket(label, missing):
        # Fit "missing" means no supporting candidate evidence, not a proven failure.
        return "unknown"
    return "unknown"


def _evaluation_status_and_explanation(
    *,
    requirement: Requirement,
    comparison: RequirementComparison,
    matched: list[str],
    partial: list[str],
    missing: list[str],
    cand_refs: list[str],
) -> tuple[RequirementStatus, str]:
    kind = str((requirement.structured_condition or {}).get("kind") or "")
    if kind == "skill":
        name = str((requirement.structured_condition or {}).get("name") or requirement.text)
        status = _status_from_membership(name, matched, partial, missing)
        if comparison.status == "satisfied" and status == "unknown":
            status = "satisfied"
        if status == "unknown":
            return status, UNKNOWN_EXPLANATION
        if status == "not_satisfied":
            return status, NOT_SATISFIED_EXPLANATION
        if status == "partially_satisfied":
            return status, comparison.reason or "Partial skill match against stored candidate evidence."
        return status, comparison.reason or "Grounded candidate evidence covers this skill."
    status = comparison.status
    reason = (comparison.reason or "").strip()
    if status == "unknown":
        return status, reason or UNKNOWN_EXPLANATION
    if status == "not_satisfied":
        return status, reason or NOT_SATISFIED_EXPLANATION
    return status, reason or comparison.reason


def _candidate_eval_refs(
    store: MatchEvidenceStore,
    requirement: Requirement,
    candidate: Candidate,
    preferences: TargetPreference | None,
) -> list[str]:
    kind = (requirement.structured_condition or {}).get("kind")
    refs: list[str] = []
    if kind == "skill":
        name = str((requirement.structured_condition or {}).get("name") or requirement.text)
        return _find_candidate_skill_refs(store, candidate, name)
    if kind in {"final_year", "currently_enrolled"}:
        for field in ("academic_year", "currently_enrolled_in_program", "expected_graduation"):
            ref = _preference_ref(store, preferences, field)
            if ref:
                refs.append(ref)
        refs.extend(_education_refs(store, candidate))
        return refs
    if kind == "recent_graduate":
        ref = _preference_ref(store, preferences, "expected_graduation")
        if ref:
            refs.append(ref)
        refs.extend(_education_refs(store, candidate))
        return refs
    if kind == "work_authorization":
        ref = _preference_ref(store, preferences, "work_authorization")
        return [ref] if ref else []
    if kind == "sponsorship":
        ref = _preference_ref(store, preferences, "sponsorship_required")
        return [ref] if ref else []
    if kind in {"degree", "equivalent_experience"}:
        return _education_refs(store, candidate)
    return []


def build_match_evidence_payload(
    *,
    job: JobRecord,
    candidate: Candidate,
    preferences: TargetPreference | None,
    profile: JobRequirementProfile | None,
    report: EligibilityReport | None,
    breakdown: ScoreBreakdown,
    score: MatchScore,
    full: bool,
) -> dict[str, Any]:
    store = MatchEvidenceStore()
    factors: list[MatchFactor] = []
    evaluations: list[RequirementEvaluation] = []
    groups: list[GroupEvaluation] = []
    public_id = job.public_id
    matched = list(breakdown.matched or score.matched_skills)
    partial = list(breakdown.partial or score.partial_matches)
    missing = list(breakdown.missing or score.missing_skills)

    represented_skills = _append_fit_skill_factors(
        store=store,
        factors=factors,
        job=job,
        candidate=candidate,
        profile=profile,
        breakdown=breakdown,
        matched=matched,
        partial=partial,
        missing=missing,
    )

    if profile and profile.work_mode and profile.work_mode != "unknown":
        loc_text = profile.locations[0].evidence_text if profile.locations and profile.locations[0].evidence_text else None
        job_ref = store.add(
            source_type="job_posting",
            exact_text=loc_text or f"Work mode: {profile.work_mode}",
            source_entity_id="work_mode",
            field="work_mode",
            locator="work_mode",
        )
        pref_ref = _preference_ref(store, preferences, "work_mode_preferences")
        loc_ref = _preference_ref(store, preferences, "preferred_locations")
        accepted = [str(item).lower() for item in (preferences.work_mode_preferences or [])] if preferences else []
        if not accepted and preferences and preferences.remote_preference:
            accepted = [preferences.remote_preference.lower()]
        status: RequirementStatus = "unknown"
        explanation = "Employer work mode was not compared; candidate preference is not stated."
        if accepted:
            if profile.work_mode.lower() in accepted or "any" in accepted:
                status = "satisfied"
                explanation = "Preference satisfied."
            else:
                status = "not_satisfied"
                explanation = (
                    UNKNOWN_EXPLANATION
                    if not (pref_ref or loc_ref)
                    else "Work mode is outside stated preferences."
                )
                if not (pref_ref or loc_ref):
                    status = "unknown"
        cand_refs = [item for item in (pref_ref, loc_ref) if item]
        factors.append(
            MatchFactor(
                id="factor_work_mode",
                job_id=public_id,
                category="work_mode",
                section="work_location",
                label=profile.work_mode.replace("_", " ").title(),
                importance="preferred",
                status=status,
                rule_id="work_mode_preference_v1",
                rule_version="v1",
                explanation=explanation,
                job_evidence_refs=[job_ref] if job_ref else [],
                candidate_evidence_refs=cand_refs,
            )
        )

    if not full or profile is None or report is None:
        return {
            "factors": [item.model_dump() for item in factors],
            "evaluations": [],
            "groups": [],
            "evidence": {key: value.model_dump() for key, value in store.evidence.items()},
        }

    grouped_ids = {rid for group in profile.requirement_groups for rid in group.requirement_ids}
    cmp_by_id = {item.requirement_id: item for item in report.comparisons}
    req_by_id = {item.id: item for item in profile.requirements}

    for comparison in report.comparisons:
        requirement = req_by_id.get(comparison.requirement_id)
        if requirement is None:
            continue
        kind = (requirement.structured_condition or {}).get("kind") or "other"
        category = _KIND_CATEGORY.get(str(kind), "other_requirement")
        rule_id, rule_version = _KIND_RULE.get(str(kind), ("requirement_compare_v1", "v1"))
        job_ref = _job_requirement_ref(store, requirement)
        cand_refs = _candidate_eval_refs(store, requirement, candidate, preferences)
        eval_status, explanation = _evaluation_status_and_explanation(
            requirement=requirement,
            comparison=comparison,
            matched=matched,
            partial=partial,
            missing=missing,
            cand_refs=cand_refs,
        )
        group_id = next(
            (group.id for group in profile.requirement_groups if requirement.id in group.requirement_ids),
            None,
        )
        evaluations.append(
            RequirementEvaluation(
                requirement_id=requirement.id,
                result=eval_status,
                candidate_evidence_refs=cand_refs if eval_status != "not_satisfied" or cand_refs else [],
                job_evidence_refs=[job_ref] if job_ref else [],
                explanation=explanation,
                rule_id=rule_id,
                group_id=group_id,
            )
        )
        if requirement.id in grouped_ids:
            continue
        if str(kind) == "skill":
            name = str((requirement.structured_condition or {}).get("name") or requirement.text)
            key = _skill_group_key(name)
            if (_importance_bucket(requirement.importance), key) in represented_skills:
                continue
        hard = requirement.importance == "hard_required" and eval_status == "not_satisfied"
        if _importance_bucket(requirement.importance) == "preferred":
            hard = False
        section: FactorSection = _CATEGORY_SECTION.get(category, "qualifications")
        if str(kind) == "skill":
            section = "required_skills" if _importance_bucket(requirement.importance) == "required" else "preferred_skills"
        scoring_effect = None
        if str(kind) == "skill":
            scoring_effect = (
                "Contributes to the Required Skills component. Individual skills are not assigned separate point values."
                if _importance_bucket(requirement.importance) == "required"
                else "Does not contribute to the Required Skills component. Contributes to Preferred qualifications when Fit V2 scores preferred skills."
            )
        factors.append(
            MatchFactor(
                id=f"factor_req_{requirement.id}",
                job_id=public_id,
                category=category,
                section=section,
                label=requirement.text,
                importance=requirement.importance,
                status=eval_status,
                rule_id=rule_id,
                rule_version=rule_version,
                explanation=explanation,
                job_evidence_refs=[job_ref] if job_ref else [],
                candidate_evidence_refs=cand_refs,
                requirement_id=requirement.id,
                hard_blocker=hard,
                scoring_effect=scoring_effect,
            )
        )

    group_status = {item.group_id: item for item in report.groups}
    for group in profile.requirement_groups:
        result = group_status.get(group.id)
        status = result.status if result else "unknown"
        job_ref = store.add(
            source_type="job_requirement",
            exact_text=(group.evidence_text or group.text).strip(),
            source_entity_id=group.id,
            field="evidence_text",
            locator=group.id,
        )
        hard = group.importance == "hard_required" and status == "not_satisfied"
        groups.append(
            GroupEvaluation(
                group_id=group.id,
                operator=group.operator,
                text=group.text,
                status=status,
                importance=group.importance,
                job_evidence_refs=[job_ref] if job_ref else [],
                branch_ids=list(group.requirement_ids),
                explanation=result.reason if result else group.text,
                hard_blocker=hard,
            )
        )
        factors.append(
            MatchFactor(
                id=f"factor_group_{group.id}",
                job_id=public_id,
                category="academic_year" if "final year" in group.text.lower() or "graduat" in group.text.lower() else "other_requirement",
                section="eligibility",
                label=group.text,
                importance=group.importance,
                status=status,
                rule_id="graduation_eligibility_v1",
                rule_version="v1",
                explanation=(
                    "Neither branch is satisfied."
                    if status == "not_satisfied"
                    else result.reason if result else group.text
                ),
                job_evidence_refs=[job_ref] if job_ref else [],
                group_id=group.id,
                hard_blocker=hard,
            )
        )

    return {
        "factors": [item.model_dump() for item in factors],
        "evaluations": [item.model_dump() for item in evaluations],
        "groups": [item.model_dump() for item in groups],
        "evidence": {key: value.model_dump() for key, value in store.evidence.items()},
    }


class MatchEvidenceConsistencyError(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("match evidence consistency failed")


def _ref_source_type(evidence: dict[str, Any], ref: str) -> str | None:
    item = evidence.get(ref)
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get("source_type")
    return getattr(item, "source_type", None)


def validate_match_evidence_payload(
    payload: dict[str, Any],
    *,
    profile: JobRequirementProfile | None = None,
) -> None:
    reasons: list[str] = []
    factors = [MatchFactor.model_validate(item) for item in payload.get("factors") or []]
    evaluations = [RequirementEvaluation.model_validate(item) for item in payload.get("evaluations") or []]
    groups = [GroupEvaluation.model_validate(item) for item in payload.get("groups") or []]
    evidence = payload.get("evidence") or {}
    req_ids = {item.id for item in profile.requirements} if profile else set()
    req_importance = {item.id: item.importance for item in profile.requirements} if profile else {}
    seen_requirement: dict[str, str] = {}
    component_totals: dict[str, float] = {"required_skills": 0.0, "preferred_skills": 0.0}
    skill_rows: dict[tuple[str, tuple[str, str], str], list[MatchFactor]] = {}
    eval_by_req = {item.requirement_id: item for item in evaluations}
    group_by_id = {item.group_id: item for item in groups}

    def _check_refs(job_refs: list[str], candidate_refs: list[str]) -> None:
        for ref in job_refs:
            if ref not in evidence:
                reasons.append("missing_evidence_ref")
                continue
            source = _ref_source_type(evidence, ref)
            if source and source not in _JOB_SOURCE_TYPES:
                reasons.append("job_ref_wrong_source")
        for ref in candidate_refs:
            if ref not in evidence:
                reasons.append("missing_evidence_ref")
                continue
            source = _ref_source_type(evidence, ref)
            if source and source not in _CANDIDATE_SOURCE_TYPES:
                reasons.append("candidate_ref_wrong_source")

    for factor in factors:
        _check_refs(factor.job_evidence_refs, factor.candidate_evidence_refs)
        if factor.score_contribution is not None and factor.max_contribution is not None:
            if factor.score_contribution > factor.max_contribution + 0.05:
                reasons.append("contribution_exceeds_max")
            if (
                factor.status == "satisfied"
                and factor.score_contribution == 0
                and factor.max_contribution > 0
            ):
                reasons.append("satisfied_zero_contribution")
            if (
                factor.status == "not_satisfied"
                and factor.max_contribution > 0
                and factor.score_contribution >= factor.max_contribution - 0.05
            ):
                reasons.append("not_satisfied_full_credit")
            if factor.status == "partially_satisfied" and (
                factor.score_contribution <= 0.05
                or factor.score_contribution >= factor.max_contribution - 0.05
            ):
                reasons.append("partial_credit_incoherent")
        if factor.status == "not_applicable" and factor.score_contribution is not None:
            reasons.append("not_applicable_has_contribution")
        if _importance_bucket(factor.importance) == "preferred" and factor.hard_blocker:
            reasons.append("preferred_hard_blocker")
        if factor.section in component_totals and factor.score_contribution is not None:
            component_totals[factor.section] += factor.score_contribution
        if factor.requirement_id:
            previous = seen_requirement.get(factor.requirement_id)
            if previous and previous != factor.id:
                reasons.append("duplicate_requirement")
            seen_requirement[factor.requirement_id] = factor.id
            if profile is not None and factor.requirement_id not in req_ids:
                reasons.append("stale_requirement")
            if factor.requirement_id in req_importance:
                if _importance_bucket(factor.importance) != _importance_bucket(req_importance[factor.requirement_id]):
                    reasons.append("importance_mismatch")
            linked = eval_by_req.get(factor.requirement_id)
            if linked is not None and linked.result != factor.status:
                reasons.append("factor_evaluation_status_mismatch")
        if factor.group_id:
            grouped = group_by_id.get(factor.group_id)
            if grouped is not None and grouped.status != factor.status:
                reasons.append("factor_group_status_mismatch")
        if (
            factor.category == "skill"
            and factor.id not in {"factor_required_skills", "factor_preferred_skills"}
        ):
            key = (factor.section, _skill_group_key(factor.label), _importance_bucket(factor.importance))
            skill_rows.setdefault(key, []).append(factor)

    for evaluation in evaluations:
        _check_refs(evaluation.job_evidence_refs, evaluation.candidate_evidence_refs)
    for group in groups:
        _check_refs(group.job_evidence_refs, [])
        if _importance_bucket(group.importance) == "preferred" and group.hard_blocker:
            reasons.append("preferred_hard_blocker")

    if component_totals["required_skills"] > round(QUAL_REQUIRED_SKILLS * 100, 1) + 0.05:
        reasons.append("required_component_exceeds_max")
    if component_totals["preferred_skills"] > round(QUAL_PREFERRED * 100, 1) + 0.05:
        reasons.append("preferred_component_exceeds_max")
    for group in skill_rows.values():
        statuses = {item.status for item in group}
        if "satisfied" in statuses and "not_satisfied" in statuses:
            reasons.append("contradictory_skill")
        if "satisfied" in statuses and "unknown" in statuses:
            reasons.append("contradictory_skill")
        if len(group) > 1:
            reasons.append("duplicate_skill_row")

    unique = list(dict.fromkeys(reasons))
    if unique:
        raise MatchEvidenceConsistencyError(unique)


def persist_match_evidence(
    db: Session,
    *,
    user_id: int,
    job: JobRecord,
    candidate: Candidate,
    preferences: TargetPreference | None,
    profile: JobRequirementProfile | None,
    report: EligibilityReport | None,
    breakdown: ScoreBreakdown,
    score: MatchScore,
) -> MatchEvidenceRecord | None:
    score_row = (
        db.query(MatchScoreRecord)
        .filter(MatchScoreRecord.job_id == job.id, MatchScoreRecord.candidate_id == candidate.id)
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )
    if score_row is None:
        raise StoredScoreNotFoundError()
    content_status = getattr(job, "content_status", None) or (profile.content_status if profile else None)
    full = (
        score.score_kind == "verified"
        and content_status == "full"
        and profile is not None
        and report is not None
    )
    payload = build_match_evidence_payload(
        job=job,
        candidate=candidate,
        preferences=preferences,
        profile=profile,
        report=report,
        breakdown=breakdown,
        score=score,
        full=full,
    )
    try:
        validate_match_evidence_payload(payload, profile=profile)
    except MatchEvidenceConsistencyError as exc:
        logger.warning(
            "match evidence skipped job_pk=%s reasons=%s",
            job.id,
            ",".join(exc.reasons),
        )
        return (
            db.query(MatchEvidenceRecord)
            .filter(MatchEvidenceRecord.match_score_id == score_row.id)
            .first()
        )
    cand_fp = fingerprint_for_candidate(db, candidate, user_id)
    pref_fp = preference_fingerprint(preferences)
    req_fp = profile.source_fingerprint if profile else None
    existing = (
        db.query(MatchEvidenceRecord)
        .filter(MatchEvidenceRecord.match_score_id == score_row.id)
        .first()
    )
    fields = {
        "user_id": user_id,
        "job_id": job.id,
        "candidate_id": candidate.id,
        "match_score_id": score_row.id,
        "score_kind": score.score_kind,
        "scoring_version": score.scoring_version,
        "evidence_version": EVIDENCE_VERSION,
        "candidate_fingerprint": cand_fp,
        "preference_fingerprint": pref_fp,
        "requirement_fingerprint": req_fp,
        "payload_json": payload,
    }
    if existing is None:
        existing = MatchEvidenceRecord(**fields)
        db.add(existing)
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
    db.flush()
    logger.info(
        "match evidence persisted job_pk=%s candidate_pk=%s full=%s factors=%s",
        job.id,
        candidate.id,
        full,
        len(payload.get("factors") or []),
    )
    return existing


def _stale_reasons(
    row: MatchEvidenceRecord,
    *,
    candidate_fp: str | None,
    preference_fp: str | None,
    requirement_fp: str | None,
) -> list[str]:
    reasons: list[str] = []
    if row.candidate_fingerprint and candidate_fp and row.candidate_fingerprint != candidate_fp:
        reasons.append("candidate")
    if row.preference_fingerprint and preference_fp and row.preference_fingerprint != preference_fp:
        reasons.append("preferences")
    if row.requirement_fingerprint and requirement_fp and row.requirement_fingerprint != requirement_fp:
        reasons.append("job_requirements")
    if row.evidence_version != EVIDENCE_VERSION:
        reasons.append("evidence_version")
    return reasons


def get_match_evidence(db: Session, job_public_id: str, user_id: int) -> MatchEvidenceResponse:
    job = load_job(db, job_public_id)
    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    if candidate is None:
        raise StoredScoreNotFoundError()
    score_row = (
        db.query(MatchScoreRecord)
        .filter(MatchScoreRecord.job_id == job.id, MatchScoreRecord.candidate_id == candidate.id)
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )
    if score_row is None:
        raise StoredScoreNotFoundError()
    score = _record_to_match_score(score_row, job.public_id)
    profile = load_requirement_profile(db, job)
    preferences = load_preferences(db, candidate)
    candidate_fp = fingerprint_for_candidate(db, candidate, user_id)
    preference_fp = preference_fingerprint(preferences)
    requirement_fp = profile.source_fingerprint if profile else None

    row = (
        db.query(MatchEvidenceRecord)
        .filter(
            MatchEvidenceRecord.user_id == user_id,
            MatchEvidenceRecord.job_id == job.id,
            MatchEvidenceRecord.candidate_id == candidate.id,
            MatchEvidenceRecord.match_score_id == score_row.id,
        )
        .first()
    )
    verified = score.score_kind == "verified"
    if row is None:
        notice = UNSTORED_NOTICE if verified else PRELIMINARY_NOTICE
        return MatchEvidenceResponse(
            job_id=job.public_id,
            score=score,
            full_evidence=False,
            notice=notice,
            provenance=MatchEvidenceProvenance(
                scoring_version=score.scoring_version,
                evidence_version=EVIDENCE_VERSION,
                score_kind=score.score_kind,
                candidate_fingerprint=candidate_fp,
                preference_fingerprint=preference_fp,
                requirement_fingerprint=requirement_fp,
                stale=False,
                stale_reasons=[],
            ),
            factors=[
                MatchFactor(
                    id=f"factor_skill_{hashlib.sha256(label.lower().encode()).hexdigest()[:10]}",
                    job_id=job.public_id,
                    category="skill",
                    section="qualifications",
                    label=label,
                    status=_status_from_membership(
                        label, score.matched_skills, score.partial_matches, score.missing_skills
                    ),
                    rule_id="required_skills_v2",
                    rule_version="v2",
                    explanation=PRELIMINARY_NOTICE,
                )
                for label in [*score.matched_skills, *score.partial_matches, *score.missing_skills]
            ],
        )

    reasons = _stale_reasons(
        row, candidate_fp=candidate_fp, preference_fp=preference_fp, requirement_fp=requirement_fp
    )
    stale = bool(reasons)
    payload = row.payload_json if isinstance(row.payload_json, dict) else {}
    full = bool(verified and not stale and (payload.get("evaluations") or payload.get("groups")))
    notice = None
    if not verified:
        notice = PRELIMINARY_NOTICE
    elif stale:
        notice = STALE_NOTICE
    return MatchEvidenceResponse(
        job_id=job.public_id,
        score=score,
        full_evidence=full,
        notice=notice,
        provenance=MatchEvidenceProvenance(
            scoring_version=row.scoring_version or score.scoring_version,
            evidence_version=row.evidence_version,
            score_kind=row.score_kind or score.score_kind,
            candidate_fingerprint=row.candidate_fingerprint,
            preference_fingerprint=row.preference_fingerprint,
            requirement_fingerprint=row.requirement_fingerprint,
            stale=stale,
            stale_reasons=reasons,
        ),
        factors=[MatchFactor.model_validate(item) for item in payload.get("factors") or []],
        evaluations=[RequirementEvaluation.model_validate(item) for item in payload.get("evaluations") or []],
        groups=[GroupEvaluation.model_validate(item) for item in payload.get("groups") or []],
        evidence={key: EvidenceRef.model_validate(value) for key, value in (payload.get("evidence") or {}).items()},
    )


__all__ = [
    "JobNotFoundError",
    "StoredScoreNotFoundError",
    "get_match_evidence",
    "persist_match_evidence",
    "validate_match_evidence_payload",
    "MatchEvidenceConsistencyError",
    "preference_fingerprint",
]

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
)
from backend.services.candidate_provenance import fingerprint_for_candidate, hash_canonical
from backend.services.fit_v2 import QUAL_REQUIRED_SKILLS
from backend.services.job_requirement_extractor import load_requirement_profile

logger = logging.getLogger(__name__)

PRELIMINARY_NOTICE = "Full requirement evidence has not been verified yet."
MISSING_CANDIDATE_EVIDENCE = "No supporting candidate evidence found."
STALE_NOTICE = "This evidence is stale. Calculate Fit again to refresh it."
UNSTORED_NOTICE = "Evidence for this score is not stored yet. Calculate Fit to generate it."

_CATEGORY_SECTION: dict[str, FactorSection] = {
    "skill": "qualifications",
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


def _find_candidate_skill_refs(store: MatchEvidenceStore, candidate: Candidate, skill: str) -> list[str]:
    needle = skill.strip()
    if not needle:
        return []
    refs: list[str] = []
    for index, project in enumerate(candidate.projects or []):
        blob = _stringify_item(project)
        line = _line_with(blob, needle)
        if not line:
            continue
        name = project.get("name") if isinstance(project, dict) else None
        refs.append(
            store.add(
                source_type="candidate_project",
                exact_text=line,
                source_entity_id=str(name or index),
                field="projects",
                locator=f"projects[{index}]",
            )
        )
        return refs
    for index, role in enumerate(candidate.experience or []):
        blob = _stringify_item(role)
        line = _line_with(blob, needle)
        if not line:
            continue
        title = role.get("title") if isinstance(role, dict) else None
        refs.append(
            store.add(
                source_type="candidate_experience",
                exact_text=line,
                source_entity_id=str(title or index),
                field="experience",
                locator=f"experience[{index}]",
            )
        )
        return refs
    for index, listed in enumerate(candidate.skills or []):
        if needle.lower() not in str(listed).lower() and str(listed).lower() not in needle.lower():
            continue
        refs.append(
            store.add(
                source_type="candidate_profile",
                exact_text=str(listed),
                source_entity_id="skills",
                field="skills",
                locator=f"skills[{index}]",
            )
        )
        return refs
    return []


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


def _status_from_membership(label: str, matched: list[str], partial: list[str], missing: list[str]) -> RequirementStatus:
    key = label.strip().lower()
    if any(key == item.strip().lower() for item in matched):
        return "satisfied"
    if any(key == item.strip().lower() for item in partial):
        return "partially_satisfied"
    if any(key == item.strip().lower() for item in missing):
        return "not_satisfied"
    return "unknown"


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

    required_n = len((profile.required_skills if profile else []) or [])
    if required_n == 0:
        required_n = len(matched) + len(missing)
    matched_n = max(required_n - len(missing), 0) if required_n else len(matched)
    max_skills = round(QUAL_REQUIRED_SKILLS * 100, 1)
    skill_contribution = None
    if required_n:
        skill_contribution = round(max_skills * (matched_n / required_n), 1)

    factors.append(
        MatchFactor(
            id="factor_required_skills",
            job_id=public_id,
            category="skill",
            section="qualifications",
            label="Required skills",
            importance="required",
            status="satisfied" if required_n and matched_n == required_n else (
                "not_satisfied" if missing else "partially_satisfied" if matched else "unknown"
            ),
            score_contribution=skill_contribution,
            max_contribution=max_skills if required_n else None,
            rule_id="required_skills_v2",
            rule_version="v2",
            explanation=(
                f"{matched_n} / {required_n} required skills matched."
                if required_n
                else "No required skills were structured for this posting."
            ),
        )
    )

    labels = list(dict.fromkeys([*matched, *partial, *missing]))
    for label in labels:
        status = _status_from_membership(label, matched, partial, missing)
        job_refs: list[str] = []
        cand_refs = _find_candidate_skill_refs(store, candidate, label)
        if profile:
            for requirement in profile.requirements:
                kind = (requirement.structured_condition or {}).get("kind")
                name = str((requirement.structured_condition or {}).get("name") or requirement.text)
                if kind == "skill" and label.lower() in name.lower():
                    ref = _job_requirement_ref(store, requirement)
                    if ref:
                        job_refs.append(ref)
            if not job_refs and label.lower() in " ".join(profile.required_skills).lower():
                job_refs.append(_job_posting_ref(store, job, label, f"skill:{label}"))
        if not job_refs:
            job_refs.append(_job_posting_ref(store, job, label, f"skill:{label}"))
        if status == "not_satisfied":
            explanation = MISSING_CANDIDATE_EVIDENCE
            cand_refs = []
        elif not cand_refs:
            explanation = MISSING_CANDIDATE_EVIDENCE
        else:
            explanation = "Exact skill match against stored candidate evidence."
        factors.append(
            MatchFactor(
                id=f"factor_skill_{hashlib.sha256(label.lower().encode()).hexdigest()[:10]}",
                job_id=public_id,
                category="skill",
                section="qualifications",
                label=label,
                importance="required" if label in missing or label in matched else "preferred",
                status=status,
                rule_id="required_skills_v2",
                rule_version="v2",
                explanation=explanation,
                job_evidence_refs=job_refs,
                candidate_evidence_refs=cand_refs,
            )
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
                explanation = MISSING_CANDIDATE_EVIDENCE if not (pref_ref or loc_ref) else "Work mode is outside stated preferences."
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
        if comparison.status == "not_satisfied":
            explanation = comparison.reason if comparison.reason else MISSING_CANDIDATE_EVIDENCE
            if not cand_refs:
                explanation = MISSING_CANDIDATE_EVIDENCE
        elif comparison.status == "unknown":
            explanation = comparison.reason
        else:
            explanation = comparison.reason
        group_id = next(
            (group.id for group in profile.requirement_groups if requirement.id in group.requirement_ids),
            None,
        )
        evaluations.append(
            RequirementEvaluation(
                requirement_id=requirement.id,
                result=comparison.status,
                candidate_evidence_refs=cand_refs if comparison.status != "not_satisfied" or cand_refs else [],
                job_evidence_refs=[job_ref] if job_ref else [],
                explanation=explanation,
                rule_id=rule_id,
                group_id=group_id,
            )
        )
        if requirement.id in grouped_ids:
            continue
        hard = requirement.importance == "hard_required" and comparison.status == "not_satisfied"
        factors.append(
            MatchFactor(
                id=f"factor_req_{requirement.id}",
                job_id=public_id,
                category=category,
                section=_CATEGORY_SECTION.get(category, "qualifications"),
                label=requirement.text,
                importance=requirement.importance,
                status=comparison.status,
                rule_id=rule_id,
                rule_version=rule_version,
                explanation=explanation,
                job_evidence_refs=[job_ref] if job_ref else [],
                candidate_evidence_refs=cand_refs if comparison.status != "unknown" or cand_refs else cand_refs,
                requirement_id=requirement.id,
                hard_blocker=hard,
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
) -> MatchEvidenceRecord:
    score_row = (
        db.query(MatchScoreRecord)
        .filter(MatchScoreRecord.job_id == job.id, MatchScoreRecord.candidate_id == candidate.id)
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )
    if score_row is None:
        raise StoredScoreNotFoundError()
    full = score.score_kind == "verified" and profile is not None and report is not None
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
                stale=verified,
                stale_reasons=["unstored"] if verified else [],
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
    "preference_fingerprint",
]

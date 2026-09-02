"""Read-only Career Growth aggregation from stored grounded evidence.

Page load must not scout, score, extract, or call a provider.
Fit / ranking / MatchScore records are never mutated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.models import (
    JobRecord,
    JobRequirementProfileRecord,
    MatchEvidenceRecord,
    MatchScoreRecord,
    SavedJobRecord,
)
from backend.schemas.career_growth import (
    CareerGrowthJobRef,
    CareerGrowthSummary,
    EvidenceState,
    PriorityLabel,
    SkillGrowthItem,
    SkillImportance,
)
from backend.schemas.job_requirements import JobRequirementProfile
from backend.schemas.match_evidence import EVIDENCE_VERSION, MatchFactor
from backend.services.analysis_service import (
    _canonical_skill_key,
    canonicalize_skill,
    load_latest_candidate,
    load_preferences,
)
from backend.services.candidate_provenance import fingerprint_for_candidate
from backend.services.job_requirement_extractor import (
    current_posting_fingerprint,
    is_current_requirement_profile,
)
from backend.services.match_evidence_service import _stale_reasons, preference_fingerprint
from backend.services.profile_readiness import require_ready_profile

logger = logging.getLogger(__name__)

COHORT_MAX_JOBS = 25
TOP_MATCH_SUPPLEMENT = 15

_SKIP_LABELS = {"required skills", "preferred skills"}
_EXCLUDED_CATEGORIES = {
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
    "education",
    "experience",
    "responsibility",
}
_EXCLUDED_SECTIONS = {"eligibility", "work_location", "preferences"}

# Priority = 100*frequency + 40*required_fraction + 15*saved_fraction
# + evidence adjustment. High >= 70, Medium >= 40, else Low.
PRIORITY_HIGH = 70.0
PRIORITY_MEDIUM = 40.0


@dataclass
class _JobSkill:
    job_public_id: str
    title: str
    company: str
    importance: SkillImportance
    evidence_state: EvidenceState
    saved: bool
    has_candidate_refs: bool
    label: str


@dataclass
class _SkillAcc:
    canonical_key: str
    labels: list[str] = field(default_factory=list)
    jobs: dict[str, _JobSkill] = field(default_factory=dict)


def build_career_growth(db: Session, user_id: int) -> CareerGrowthSummary:
    """Compute a user-scoped, read-only growth summary. Never writes."""
    require_ready_profile(db, user_id)
    candidate = load_latest_candidate(db, user_id)
    generated_at = datetime.now(timezone.utc)

    saved_rows = (
        db.query(SavedJobRecord, JobRecord)
        .join(JobRecord, JobRecord.id == SavedJobRecord.job_id)
        .filter(SavedJobRecord.user_id == user_id)
        .order_by(SavedJobRecord.created_at.desc())
        .all()
    )
    saved_jobs = [job for _saved, job in saved_rows]
    saved_pks = {job.id for job in saved_jobs}

    latest_scores = _latest_scores_for_candidate(db, candidate.id)
    ranked_job_pks = [
        pk
        for pk, _row in sorted(
            latest_scores.items(),
            key=lambda item: (
                item[1].ranking_score if item[1].ranking_score is not None else -1.0,
                item[1].id,
            ),
            reverse=True,
        )
    ]

    cohort_pks: list[int] = []
    seen: set[int] = set()
    for job in saved_jobs:
        if job.id in seen:
            continue
        cohort_pks.append(job.id)
        seen.add(job.id)
        if len(cohort_pks) >= COHORT_MAX_JOBS:
            break
    if len(cohort_pks) < COHORT_MAX_JOBS:
        remaining = min(TOP_MATCH_SUPPLEMENT, COHORT_MAX_JOBS - len(cohort_pks))
        for pk in ranked_job_pks:
            if pk in seen:
                continue
            cohort_pks.append(pk)
            seen.add(pk)
            remaining -= 1
            if remaining <= 0 or len(cohort_pks) >= COHORT_MAX_JOBS:
                break

    if not cohort_pks:
        logger.info("career_growth empty user_pk=%s", user_id)
        return CareerGrowthSummary(
            jobs_considered=0,
            jobs_with_current_evidence=0,
            saved_jobs_considered=0,
            matched_jobs_considered=0,
            stale_jobs_excluded=0,
            unavailable_jobs_excluded=0,
            generated_at=generated_at,
            notice="Discover or save some jobs first.",
        )

    jobs_by_pk = {
        job.id: job
        for job in db.query(JobRecord).filter(JobRecord.id.in_(cohort_pks)).all()
    }
    scores_by_job = {pk: latest_scores[pk] for pk in cohort_pks if pk in latest_scores}
    evidence_by_score_id = _evidence_for_scores(db, user_id, candidate.id, scores_by_job)
    profiles_by_job = {
        row.job_id: row
        for row in db.query(JobRequirementProfileRecord)
        .filter(JobRequirementProfileRecord.job_id.in_(cohort_pks))
        .all()
    }

    preferences = load_preferences(db, candidate)
    candidate_fp = fingerprint_for_candidate(db, candidate, user_id)
    preference_fp = preference_fingerprint(preferences)

    saved_in_cohort = 0
    matched_in_cohort = 0
    stale_excluded = 0
    unavailable_excluded = 0
    analyzed: list[JobRecord] = []
    skill_acc: dict[str, _SkillAcc] = {}

    for pk in cohort_pks:
        job = jobs_by_pk.get(pk)
        if job is None:
            continue
        saved = pk in saved_pks
        if saved:
            saved_in_cohort += 1
        else:
            matched_in_cohort += 1
        score = scores_by_job.get(pk)
        profile_row = profiles_by_job.get(pk)
        profile = None
        if is_current_requirement_profile(job, profile_row) and profile_row is not None:
            profile = JobRequirementProfile.model_validate(profile_row.profile_json)
        current_fp = current_posting_fingerprint(job)
        evidence = evidence_by_score_id.get(score.id) if score is not None else None
        if evidence is not None:
            reasons = _stale_reasons(
                evidence,
                candidate_fp=candidate_fp,
                preference_fp=preference_fp,
                requirement_fp=current_fp,
            )
            if evidence.requirement_fingerprint and evidence.requirement_fingerprint != current_fp:
                if "job_requirements" not in reasons:
                    reasons.append("job_requirements")
            if reasons:
                stale_excluded += 1
                continue
            factors = _skill_factors_from_payload(evidence.payload_json or {}, job.public_id)
            if not factors:
                unavailable_excluded += 1
                continue
            analyzed.append(job)
            _accumulate_from_factors(skill_acc, job, factors, saved=saved)
            continue
        if score is not None and profile is not None:
            analyzed.append(job)
            _accumulate_from_score(skill_acc, job, score, profile, saved=saved)
            continue
        unavailable_excluded += 1

    denominator = len(analyzed)
    gaps: list[SkillGrowthItem] = []
    strengths: list[SkillGrowthItem] = []
    saved_analyzed = sum(1 for job in analyzed if job.id in saved_pks)

    for acc in skill_acc.values():
        item = _finalize_item(acc, denominator, saved_analyzed)
        if item is None:
            continue
        if item.candidate_evidence_state == "satisfied":
            strengths.append(item)
        else:
            gaps.append(item)

    gaps.sort(key=_gap_sort_key)
    strengths.sort(key=_strength_sort_key)

    notice = None
    if denominator == 0:
        notice = "Analyze jobs to build grounded growth insights."
    elif not gaps:
        notice = "CareerPilot isn't seeing repeated skill gaps in the current job set."

    logger.info(
        "career_growth user_pk=%s considered=%s analyzed=%s stale=%s unavailable=%s gaps=%s strengths=%s",
        user_id,
        len(cohort_pks),
        denominator,
        stale_excluded,
        unavailable_excluded,
        len(gaps),
        len(strengths),
    )
    return CareerGrowthSummary(
        jobs_considered=len(cohort_pks),
        jobs_with_current_evidence=denominator,
        saved_jobs_considered=saved_in_cohort,
        matched_jobs_considered=matched_in_cohort,
        stale_jobs_excluded=stale_excluded,
        unavailable_jobs_excluded=unavailable_excluded,
        generated_at=generated_at,
        skill_gaps=gaps,
        strengths=strengths,
        notice=notice,
    )


def _latest_scores_for_candidate(db: Session, candidate_id: int) -> dict[int, MatchScoreRecord]:
    rows = (
        db.query(MatchScoreRecord)
        .filter(MatchScoreRecord.candidate_id == candidate_id)
        .order_by(MatchScoreRecord.id.desc())
        .all()
    )
    latest: dict[int, MatchScoreRecord] = {}
    for row in rows:
        if row.job_id not in latest:
            latest[row.job_id] = row
    return latest


def _evidence_for_scores(
    db: Session,
    user_id: int,
    candidate_id: int,
    scores_by_job: dict[int, MatchScoreRecord],
) -> dict[int, MatchEvidenceRecord]:
    score_ids = [row.id for row in scores_by_job.values()]
    if not score_ids:
        return {}
    rows = (
        db.query(MatchEvidenceRecord)
        .filter(
            MatchEvidenceRecord.user_id == user_id,
            MatchEvidenceRecord.candidate_id == candidate_id,
            MatchEvidenceRecord.match_score_id.in_(score_ids),
        )
        .all()
    )
    return {row.match_score_id: row for row in rows}


def _skill_factors_from_payload(payload: dict, job_public_id: str) -> list[MatchFactor]:
    raw_factors = payload.get("factors") or []
    kept: list[MatchFactor] = []
    for raw in raw_factors:
        try:
            factor = raw if isinstance(raw, MatchFactor) else MatchFactor.model_validate(raw)
        except Exception:
            continue
        if factor.job_id and factor.job_id != job_public_id:
            continue
        if not _is_growth_skill_factor(factor):
            continue
        kept.append(factor)
    return kept


def _is_growth_skill_factor(factor: MatchFactor) -> bool:
    if factor.category in _EXCLUDED_CATEGORIES:
        return False
    if factor.section in _EXCLUDED_SECTIONS:
        return False
    if factor.category != "skill":
        return False
    label = (factor.label or "").strip()
    if not label or label.lower() in _SKIP_LABELS:
        return False
    if factor.status == "not_applicable":
        return False
    return True


def _importance_of(factor: MatchFactor) -> SkillImportance:
    importance = (factor.importance or "").strip().lower()
    if importance in {"hard_required", "required"} or factor.section == "required_skills":
        return "required"
    return "preferred"


def _map_status(status: str) -> EvidenceState:
    if status == "satisfied":
        return "satisfied"
    if status == "partially_satisfied":
        return "partial"
    if status == "not_satisfied":
        return "not_satisfied"
    return "unknown"


def _accumulate_from_factors(
    acc: dict[str, _SkillAcc],
    job: JobRecord,
    factors: list[MatchFactor],
    *,
    saved: bool,
) -> None:
    per_job: dict[str, _JobSkill] = {}
    for factor in factors:
        key = _canonical_skill_key(factor.label)
        importance = _importance_of(factor)
        state = _map_status(factor.status)
        existing = per_job.get(key)
        if existing is None:
            per_job[key] = _JobSkill(
                job_public_id=job.public_id,
                title=job.title,
                company=job.company,
                importance=importance,
                evidence_state=state,
                saved=saved,
                has_candidate_refs=bool(factor.candidate_evidence_refs),
                label=factor.label,
            )
            continue
        if existing.importance != "required" and importance == "required":
            existing.importance = "required"
        existing.evidence_state = _worse_state(existing.evidence_state, state)
        existing.has_candidate_refs = existing.has_candidate_refs or bool(factor.candidate_evidence_refs)
    for key, item in per_job.items():
        bucket = acc.setdefault(key, _SkillAcc(canonical_key=key))
        bucket.labels.append(item.label)
        bucket.jobs[item.job_public_id] = item


def _accumulate_from_score(
    acc: dict[str, _SkillAcc],
    job: JobRecord,
    score: MatchScoreRecord,
    profile: JobRequirementProfile,
    *,
    saved: bool,
) -> None:
    required = list(profile.required_skills or [])
    preferred = list(profile.preferred_skills or [])
    matched = list(score.matched_skills or [])
    partial = list(score.partial_matches or [])
    missing = list(score.missing_skills or [])
    required_keys = {_canonical_skill_key(label) for label in required}
    seen: set[str] = set()
    for label, importance in (
        *[(item, "required") for item in required],
        *[(item, "preferred") for item in preferred],
    ):
        key = _canonical_skill_key(label)
        if key in seen:
            continue
        seen.add(key)
        if importance == "preferred" and key in required_keys:
            continue
        state = _status_from_score_lists(label, matched, partial, missing)
        bucket = acc.setdefault(key, _SkillAcc(canonical_key=key))
        bucket.labels.append(label)
        bucket.jobs[job.public_id] = _JobSkill(
            job_public_id=job.public_id,
            title=job.title,
            company=job.company,
            importance=importance,  # type: ignore[arg-type]
            evidence_state=state,
            saved=saved,
            has_candidate_refs=state in {"satisfied", "partial"},
            label=label,
        )


def _status_from_score_lists(
    label: str,
    matched: list[str],
    partial: list[str],
    missing: list[str],
) -> EvidenceState:
    key = _canonical_skill_key(label)
    if any(_canonical_skill_key(item) == key for item in matched):
        return "satisfied"
    if any(_canonical_skill_key(item) == key for item in partial):
        return "partial"
    if any(_canonical_skill_key(item) == key for item in missing):
        return "unknown"
    return "unknown"


def _worse_state(left: EvidenceState, right: EvidenceState) -> EvidenceState:
    rank = {"satisfied": 0, "partial": 1, "unknown": 2, "not_satisfied": 3}
    return left if rank[left] >= rank[right] else right


def _best_state(states: list[EvidenceState]) -> EvidenceState:
    rank = {"satisfied": 0, "partial": 1, "unknown": 2, "not_satisfied": 3}
    return min(states, key=lambda item: rank[item]) if states else "unknown"


def _display_label(canonical_key: str, labels: list[str]) -> str:
    canonical = canonicalize_skill(canonical_key) or canonicalize_skill(labels[0] if labels else "")
    if canonical:
        return canonical
    if labels:
        return labels[0]
    return canonical_key


def _finalize_item(acc: _SkillAcc, denominator: int, saved_analyzed: int) -> SkillGrowthItem | None:
    if denominator <= 0 or not acc.jobs:
        return None
    jobs = list(acc.jobs.values())
    jobs_count = len(jobs)
    required_count = sum(1 for item in jobs if item.importance == "required")
    preferred_count = sum(1 for item in jobs if item.importance == "preferred")
    satisfied_count = sum(1 for item in jobs if item.evidence_state == "satisfied")
    partial_count = sum(1 for item in jobs if item.evidence_state == "partial")
    unknown_count = sum(1 for item in jobs if item.evidence_state == "unknown")
    not_satisfied_count = sum(1 for item in jobs if item.evidence_state == "not_satisfied")
    saved_count = sum(1 for item in jobs if item.saved)
    evidence_count = sum(1 for item in jobs if item.has_candidate_refs or item.evidence_state in {"satisfied", "partial"})
    candidate_state = _best_state([item.evidence_state for item in jobs])
    if evidence_count == 0 and candidate_state == "satisfied":
        candidate_state = "unknown"
    if evidence_count == 0 and candidate_state not in {"not_satisfied"}:
        candidate_state = "unknown"

    frequency = jobs_count / denominator
    required_frac = required_count / denominator
    saved_frac = (saved_count / saved_analyzed) if saved_analyzed else 0.0
    points = 100.0 * frequency + 40.0 * required_frac + 15.0 * saved_frac
    if candidate_state == "unknown":
        points += 25.0
    elif candidate_state == "not_satisfied":
        points += 18.0
    elif candidate_state == "partial":
        points += 12.0
    if candidate_state == "satisfied":
        points = 100.0 * frequency + 10.0 * required_frac
    priority = _priority_label(points)
    label = _display_label(acc.canonical_key, acc.labels)
    reason = _reason(
        label,
        jobs_count,
        denominator,
        required_count,
        preferred_count,
        candidate_state,
        saved_count,
    )
    action = _suggested_action(label, candidate_state, preferred_count, required_count)
    related = sorted(
        [
            CareerGrowthJobRef(
                job_id=item.job_public_id,
                title=item.title,
                company=item.company,
                importance=item.importance,
                evidence_state=item.evidence_state,
                saved=item.saved,
            )
            for item in jobs
        ],
        key=lambda item: (0 if item.importance == "required" else 1, item.title.lower(), item.job_id),
    )
    return SkillGrowthItem(
        canonical_key=acc.canonical_key,
        label=label,
        jobs_count=jobs_count,
        denominator=denominator,
        required_count=required_count,
        preferred_count=preferred_count,
        satisfied_count=satisfied_count,
        partial_count=partial_count,
        unknown_count=unknown_count,
        not_satisfied_count=not_satisfied_count,
        candidate_evidence_state=candidate_state,
        candidate_evidence_count=evidence_count,
        priority=priority,
        reason=reason,
        suggested_action=action,
        related_jobs=related,
    )


def _priority_label(points: float) -> PriorityLabel:
    if points >= PRIORITY_HIGH:
        return "high"
    if points >= PRIORITY_MEDIUM:
        return "medium"
    return "low"


def _reason(
    label: str,
    jobs_count: int,
    denominator: int,
    required_count: int,
    preferred_count: int,
    state: EvidenceState,
    saved_count: int,
) -> str:
    evidence = {
        "satisfied": f"CareerPilot has verified profile evidence for {label}.",
        "partial": f"CareerPilot has some profile evidence for {label}, but not enough for full support.",
        "unknown": f"CareerPilot does not currently have evidence for {label}.",
        "not_satisfied": f"Current grounded evaluation does not support {label} for these roles.",
    }[state]
    saved = (
        f" It appears in {saved_count} saved job{'s' if saved_count != 1 else ''}."
        if saved_count
        else ""
    )
    return (
        f"{label} appears in {jobs_count} of {denominator} analyzed jobs "
        f"({required_count} required, {preferred_count} preferred). {evidence}{saved}"
    )


def _suggested_action(
    label: str,
    state: EvidenceState,
    preferred_count: int,
    required_count: int,
) -> str:
    if state == "partial":
        return (
            f"Strengthen your existing {label} evidence with a project, responsibility, "
            "or measurable outcome. Do not invent work you have not done."
        )
    if state == "unknown":
        return (
            f"If you already use {label}, add truthful evidence to your profile. "
            f"Otherwise consider a small project demonstrating {label}."
        )
    if state == "not_satisfied":
        return (
            f"Review the jobs that list {label} and add truthful evidence only if you "
            "already have relevant work."
        )
    if preferred_count and not required_count:
        return (
            f"Optional: adding evidence for {label} could broaden alignment across "
            f"{preferred_count} role{'s' if preferred_count != 1 else ''}."
        )
    return f"{label} is already supported by current profile evidence."


def _gap_sort_key(item: SkillGrowthItem) -> tuple:
    rank = {"high": 0, "medium": 1, "low": 2}
    state_rank = {"unknown": 0, "not_satisfied": 1, "partial": 2, "satisfied": 3}
    return (
        rank[item.priority],
        -item.jobs_count,
        -item.required_count,
        state_rank[item.candidate_evidence_state],
        item.label.lower(),
        item.canonical_key,
    )


def _strength_sort_key(item: SkillGrowthItem) -> tuple:
    return (-item.jobs_count, -item.satisfied_count, item.label.lower(), item.canonical_key)

"""Grounded deterministic interview-prep baseline.

Templates are built only from stored Job Intelligence, Fit & Gap results,
and candidate evidence. This module never claims experience the candidate
does not have. LLM question-quality upgrades are an injectable boundary
and are not used on the production path.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import (
    Candidate,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
)
from backend.schemas.schemas import InterviewAnswerFeedback, InterviewPrep, JobIntelligence, MatchScore
from backend.services.application_materials_agent import candidate_record_to_profile
from backend.services.job_intelligence_service import get_stored_job_intelligence
from backend.services.job_service import record_to_job
from backend.services.llm_client import (
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
    get_llm_client,
)
from backend.services.llm_provider_sequence import (
    configured_provider_names,
    invoke_provider_generate,
    uses_injected_generator,
)

logger = logging.getLogger(__name__)

InterviewPrepImprover = Callable[["InterviewPrepContext", InterviewPrep], InterviewPrep]
InterviewAnswerGenerateFn = Callable[[str, str | None], str]


class InterviewPrepError(Exception):
    """Sanitized interview-prep error. ``str(exc)`` is safe for HTTP details."""


class InterviewJobNotFoundError(InterviewPrepError):
    def __init__(self) -> None:
        super().__init__("Job not found.")


class InterviewIntelligenceMissingError(InterviewPrepError):
    def __init__(self) -> None:
        super().__init__("Extract job requirements before preparing interview.")


class InterviewAnswerEmptyError(InterviewPrepError):
    def __init__(self) -> None:
        super().__init__("Write an answer before requesting feedback.")


class InterviewQuestionNotFoundError(InterviewPrepError):
    def __init__(self) -> None:
        super().__init__(
            "This question is not part of the stored interview prep for this job. "
            "Prepare interview first, then practice one of the listed questions."
        )


@dataclass
class InterviewPrepContext:
    job_id: str
    job_pk: int
    job_title: str
    company: str
    intelligence: JobIntelligence
    fit_score: MatchScore | None
    candidate_skills: list[str]
    candidate_has_profile: bool


def unfinished_llm_interview_improver(
    context: InterviewPrepContext,
    prep: InterviewPrep,
) -> InterviewPrep:
    """Named injectable boundary for later question-quality work.

    Do not call this from the deterministic baseline. Real LLM interview
    generation is out of scope for the foundation PR.
    """

    _ = context
    raise InterviewPrepError("LLM interview improvement is not implemented.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_job(db: Session, job_id: str) -> JobRecord:
    job = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job is None:
        raise InterviewJobNotFoundError()
    return job


def _record_to_prep(record: InterviewPrepRecord, job_public_id: str) -> InterviewPrep:
    return InterviewPrep(
        job_id=job_public_id,
        likely_questions=list(record.likely_questions or []),
        talking_points=list(record.talking_points or []),
        gaps_to_address=list(record.gaps_to_address or []),
    )


def get_interview_prep(db: Session, job_id: str, user_id: int) -> InterviewPrep | None:
    """Read-only. Does not create, generate, or call a provider."""

    job = _get_job(db, job_id)
    record = (
        db.query(InterviewPrepRecord)
        .filter(InterviewPrepRecord.job_id == job.id, InterviewPrepRecord.user_id == user_id)
        .first()
    )
    if record is None:
        logger.info("interview_prep read miss job_pk=%s", job.id)
        return None
    logger.info("interview_prep read hit job_pk=%s", job.id)
    return _record_to_prep(record, job_id)


def _latest_fit_score(db: Session, job: JobRecord, candidate: Candidate | None) -> MatchScore | None:
    if candidate is None:
        return None
    record = (
        db.query(MatchScoreRecord)
        .filter(
            MatchScoreRecord.job_id == job.id,
            MatchScoreRecord.candidate_id == candidate.id,
        )
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )
    if record is None:
        return None
    return MatchScore(
        job_id=job.public_id,
        overall_score=record.overall_score,
        skill_score=record.skill_score,
        experience_score=record.experience_score,
        education_score=record.education_score,
        location_score=record.location_score,
        preference_score=record.preference_score,
        matched_skills=list(record.matched_skills or []),
        partial_matches=list(record.partial_matches or []),
        missing_skills=list(record.missing_skills or []),
        recommendation=record.recommendation,  # type: ignore[arg-type]
        rationale=record.rationale,
    )


def load_interview_prep_context(db: Session, job_id: str, user_id: int) -> InterviewPrepContext:
    job = _get_job(db, job_id)
    intelligence_row = (
        db.query(JobIntelligenceRecord)
        .filter(JobIntelligenceRecord.job_id == job.id)
        .first()
    )
    if intelligence_row is None:
        raise InterviewIntelligenceMissingError()
    intelligence = get_stored_job_intelligence(db, job_id)
    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    skills: list[str] = []
    if candidate is not None:
        profile = candidate_record_to_profile(candidate)
        skills = list(profile.skills)
        for project in profile.projects:
            skills.extend(project.technologies)
    job_schema = record_to_job(job)
    return InterviewPrepContext(
        job_id=job.public_id,
        job_pk=job.id,
        job_title=job_schema.title,
        company=job_schema.company,
        intelligence=intelligence,
        fit_score=_latest_fit_score(db, job, candidate),
        candidate_skills=skills,
        candidate_has_profile=candidate is not None,
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not item.strip() or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _role_is_internship(title: str, seniority: str | None) -> bool:
    """True only when the stored role is explicitly an internship."""

    seniority_key = (seniority or "").strip().lower()
    if seniority_key in {"intern", "internship", "intern-level"}:
        return True
    return bool(re.search(r"\bintern(?:s|ship)?\b", title or "", flags=re.I))


def build_deterministic_interview_prep(context: InterviewPrepContext) -> InterviewPrep:
    """Deterministic templates from stored grounded records only."""

    intel = context.intelligence
    matched = list(context.fit_score.matched_skills) if context.fit_score else []
    missing = list(context.fit_score.missing_skills) if context.fit_score else []
    candidate_skill_keys = {item.strip().lower() for item in context.candidate_skills}

    if context.fit_score is None:
        for skill in [*intel.required_skills, *intel.preferred_skills, *intel.tech_stack]:
            if skill.strip().lower() in candidate_skill_keys:
                matched.append(skill)
            else:
                missing.append(skill)

    matched = _dedupe(matched)
    missing = _dedupe([skill for skill in missing if skill.strip().lower() not in {item.lower() for item in matched}])

    questions: list[str] = []
    for topic in intel.likely_interview_focus:
        questions.append(f"What would you expect to discuss about {topic} for this role?")
    role_phrase = "in this internship" if _role_is_internship(context.job_title, intel.seniority) else "for this role"
    for skill in intel.required_skills[:8]:
        questions.append(f"How would you demonstrate {skill} {role_phrase}?")
    if not questions:
        questions.append("Walk through a project from your stored profile that is relevant to this posting.")

    talking_points: list[str] = []
    if not context.candidate_has_profile:
        talking_points = []
    else:
        for skill in matched:
            talking_points.append(
                f"Use stored candidate evidence related to {skill}; do not invent additional experience."
            )

    gaps: list[str] = []
    for skill in missing:
        gaps.append(
            f"{skill} is a gap to address. It is not a current candidate strength."
        )
    if not context.candidate_has_profile:
        gaps.insert(0, "No candidate profile is stored yet. Build a profile before treating talking points as evidence.")
    if intel.years_experience:
        gaps.append(
            f"The posting asks for {intel.years_experience} years of experience. Only discuss years that appear in the stored profile."
        )

    logger.info(
        "interview_prep deterministic questions=%s talking_points=%s gaps=%s job_pk=%s",
        len(questions),
        len(talking_points),
        len(gaps),
        context.job_pk,
    )
    return InterviewPrep(
        job_id=context.job_id,
        likely_questions=_dedupe(questions),
        talking_points=_dedupe(talking_points),
        gaps_to_address=_dedupe(gaps),
    )


def generate_and_store_interview_prep(
    db: Session,
    job_id: str,
    user_id: int,
    *,
    improver: InterviewPrepImprover | None = None,
) -> InterviewPrep:
    """Explicit generate + idempotent upsert. Page load must not call this."""

    context = load_interview_prep_context(db, job_id, user_id)
    prep = build_deterministic_interview_prep(context)
    if improver is not None:
        prep = improver(context, prep)

    now = _now()
    record = (
        db.query(InterviewPrepRecord)
        .filter(InterviewPrepRecord.job_id == context.job_pk, InterviewPrepRecord.user_id == user_id)
        .first()
    )
    if record is None:
        record = InterviewPrepRecord(
            job_id=context.job_pk,
            user_id=user_id,
            likely_questions=list(prep.likely_questions),
            talking_points=list(prep.talking_points),
            gaps_to_address=list(prep.gaps_to_address),
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(InterviewPrepRecord)
                .filter(
                    InterviewPrepRecord.job_id == context.job_pk,
                    InterviewPrepRecord.user_id == user_id,
                )
                .first()
            )
            if existing is None:
                raise
            existing.likely_questions = list(prep.likely_questions)
            existing.talking_points = list(prep.talking_points)
            existing.gaps_to_address = list(prep.gaps_to_address)
            existing.updated_at = now
            db.commit()
            db.refresh(existing)
            logger.info("interview_prep unique conflict recovered job_pk=%s", context.job_pk)
            return _record_to_prep(existing, job_id)
        db.refresh(record)
    else:
        record.likely_questions = list(prep.likely_questions)
        record.talking_points = list(prep.talking_points)
        record.gaps_to_address = list(prep.gaps_to_address)
        record.updated_at = now
        db.commit()
        db.refresh(record)
    logger.info("interview_prep stored job_pk=%s", context.job_pk)
    return _record_to_prep(record, job_id)


_ANSWER_FEEDBACK_SYSTEM_PROMPT = (
    "You are a concise interview coach reviewing one practice answer. Comment only on "
    "how the answer communicates the candidate's existing experience — structure, "
    "clarity, specificity, and relevance to the question and role. Never invent, "
    "assume, or suggest experience, skills, employers, metrics, or projects the "
    "candidate did not already mention in their answer or in the background provided "
    "to you. If the answer is thin, say so and suggest what kind of detail from the "
    "candidate's own experience would strengthen it — do not supply that detail "
    "yourself. Keep the feedback to 2-4 sentences, addressed directly to the candidate."
)


def _usable_feedback_text(text: str | None) -> str:
    if not isinstance(text, str) or not text.strip():
        raise LLMEmptyResponseError("The language model returned an empty response.")
    return text.strip()


_FEEDBACK_PROVIDER_ERROR_PRIORITY: dict[type[BaseException], int] = {
    # A provider that actually ran and failed says more than one that was
    # never configured to begin with.
    LLMProviderError: 40,
    LLMEmptyResponseError: 40,
    # Lowest: with a provider order like "ollama,gemini" and no Gemini key,
    # this fires on every run and would otherwise bury the real failure,
    # reporting interview feedback as unconfigured on a system that is
    # configured and did run. Same defect previously fixed in
    # job_intelligence_service, application_materials_agent, and
    # candidate_profile_agent.
    LLMConfigurationError: 10,
}


def _should_replace_feedback_error(current: Exception | None, new: Exception) -> bool:
    if current is None:
        return True
    current_rank = _FEEDBACK_PROVIDER_ERROR_PRIORITY.get(type(current), 0)
    new_rank = _FEEDBACK_PROVIDER_ERROR_PRIORITY.get(type(new), 0)
    return new_rank > current_rank


def _generate_answer_feedback(
    prompt: str,
    generate_fn: InterviewAnswerGenerateFn | None,
    *,
    job_pk: int,
) -> str:
    if uses_injected_generator(generate_fn):
        assert generate_fn is not None
        return generate_fn(prompt, _ANSWER_FEEDBACK_SYSTEM_PROMPT)

    last_error: Exception | None = None
    for provider in configured_provider_names():
        try:
            raw = invoke_provider_generate(
                get_llm_client(provider), prompt, _ANSWER_FEEDBACK_SYSTEM_PROMPT
            )
            return _usable_feedback_text(raw)
        except (LLMProviderError, LLMEmptyResponseError, LLMConfigurationError) as exc:
            if _should_replace_feedback_error(last_error, exc):
                last_error = exc
            logger.info(
                "interview_answer_feedback provider sequence failed category=%s job_pk=%s",
                type(exc).__name__,
                job_pk,
            )
            continue
    if last_error is not None:
        raise last_error
    raise LLMProviderError("The language model request failed.")


def get_interview_answer_feedback(
    db: Session,
    job_id: str,
    user_id: int,
    question: str,
    answer: str,
    *,
    generate_fn: InterviewAnswerGenerateFn | None = None,
) -> InterviewAnswerFeedback:
    """Practice-only feedback on how a typed answer is delivered. Ephemeral —
    never persisted, unlike the stored InterviewPrepRecord. Grounded the same
    way as the rest of this module: the prompt supplies only stored candidate
    skills as background, and the system prompt forbids inventing new candidate
    facts — feedback may only speak to delivery, not assert new experience.

    `question` must be one of this job's already-generated likely_questions,
    not an arbitrary string — keeps the feature scoped to real prep instead of
    becoming a general-purpose free-text prompt to the provider.
    """

    if not answer.strip():
        raise InterviewAnswerEmptyError()

    job = _get_job(db, job_id)
    record = (
        db.query(InterviewPrepRecord)
        .filter(InterviewPrepRecord.job_id == job.id, InterviewPrepRecord.user_id == user_id)
        .first()
    )
    if record is None or question not in (record.likely_questions or []):
        raise InterviewQuestionNotFoundError()

    context = load_interview_prep_context(db, job_id, user_id)

    background = ", ".join(context.candidate_skills) or "no stored skills on file"
    prompt = (
        f"Role: {context.job_title} at {context.company}.\n"
        f"Interview question: {question}\n"
        f"Candidate's stored skills (background only, for judging relevance — do not "
        f"treat this as a checklist to grade the answer against): {background}\n"
        f"Candidate's answer:\n{answer}\n\n"
        "Give brief feedback on this answer per your instructions."
    )
    feedback_text = _generate_answer_feedback(prompt, generate_fn, job_pk=context.job_pk)

    logger.info("interview_answer_feedback generated job_pk=%s", context.job_pk)
    return InterviewAnswerFeedback(question=question, answer=answer, feedback=feedback_text.strip())

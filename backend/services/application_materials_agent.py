"""Application Materials Agent foundation.

This module is the student-owned implementation seam for grounded resume
bullets, cover-letter drafts, recruiter messages, and source-traceability
notes. It is intentionally not wired into the production generate-materials
route.

Production still uses the isolated legacy placeholder
``backend.services.application_service._mock_materials`` until
``generate_grounded_application_materials`` is implemented and a single
small integration change replaces that placeholder.

Critical invariant
------------------
No candidate skill, experience, project, certification, employer, title,
date, metric, percentage, currency value, technology, education claim, or
accomplishment may be introduced without candidate evidence.

No job requirement may be introduced without stored Job Intelligence or
posting evidence.

Numeric types and units in source evidence must be preserved exactly.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.schemas.schemas import (
    ApplicationPackage,
    CandidateProfile,
    Education,
    Experience,
    Job,
    JobIntelligence,
    MatchScore,
    Project,
    TargetPreferences,
)
from backend.services.analysis_service import _ALIAS_TO_CANONICAL, _skill_in_text
from backend.services.job_intelligence_service import get_stored_job_intelligence
from backend.services.job_service import record_to_job

logger = logging.getLogger(__name__)

ApplicationMaterialsGenerateFn = Callable[[str, str | None], str]

_STRUCTURED_FIELDS = (
    "tailored_bullets",
    "cover_letter_draft",
    "recruiter_message",
    "source_traceability_notes",
)

_NUMERIC_RE = re.compile(
    r"\$\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\d+(?:\.\d+)?|\d+(?:,\d{3})+(?:\.\d+)?%?|\d+(?:\.\d+)?%|\b\d+(?:\.\d+)?\b"
)

_JSON_SHAPE = """{
  "tailored_bullets": ["bullet grounded in candidate evidence and the job"],
  "cover_letter_draft": "short cover letter using only evidenced claims",
  "recruiter_message": "short recruiter note using only evidenced claims",
  "source_traceability_notes": ["bullet-or-sentence -> candidate or job evidence"]
}"""


class ApplicationMaterialsError(Exception):
    """Sanitized domain error. ``str(exc)`` is safe to return to clients."""


class MissingJobError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Job not found.")


class MissingCandidateError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Build a candidate profile before generating application materials.")


class MissingJobIntelligenceError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Extract job requirements before generating application materials.")


class MissingFitScoreError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Calculate a fit score before generating application materials.")


class ApplicationMaterialsParseError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Application materials output was not valid structured JSON.")


class ApplicationMaterialsGroundingError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__(
            "Application materials contained claims that are not supported by stored evidence."
        )


class ApplicationMaterialsNotImplementedError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Grounded application materials generation is not implemented yet.")


class ApplicationMaterialsGenerator(Protocol):
    """Injectable provider/generator boundary. Not called by the unfinished student function."""

    def __call__(self, prompt: str, system_prompt: str | None = None) -> str: ...


class ApplicationMaterialsStructuredOutput(BaseModel):
    """Structured-output schema the student generator must return."""

    tailored_bullets: list[str] = Field(default_factory=list)
    cover_letter_draft: str = ""
    recruiter_message: str = ""
    source_traceability_notes: list[str] = Field(default_factory=list)


@dataclass
class MaterialsGroundingReport:
    """Category-only grounding result. Never store raw provider output here."""

    accepted_claim_count: int = 0
    rejected_claim_count: int = 0
    invented_candidate_claims: int = 0
    invented_job_requirements: int = 0
    numeric_literals_rejected: int = 0
    rejected_categories: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return self.rejected_claim_count == 0 and self.numeric_literals_rejected == 0


@dataclass
class ApplicationMaterialsContext:
    job: Job
    job_pk: int
    candidate: CandidateProfile
    candidate_pk: int
    intelligence: JobIntelligence
    fit_score: MatchScore
    preferences: TargetPreferences | None
    posting_text: str


@dataclass
class ApplicationMaterialsDraft:
    job_id: str
    tailored_bullets: list[str]
    cover_letter_draft: str
    recruiter_message: str
    source_traceability_notes: list[str]
    grounding: MaterialsGroundingReport


def _preference_record_to_schema(record: TargetPreference) -> TargetPreferences:
    return TargetPreferences(
        target_roles=list(record.target_roles or []),
        preferred_locations=list(record.preferred_locations or []),
        remote_preference=record.remote_preference,
        salary_min=record.salary_min,
        work_authorization=record.work_authorization,
        sponsorship_required=record.sponsorship_required,
        constraints=list(record.constraints or []),
        legal_name=record.legal_name,
        linkedin_url=record.linkedin_url,
        github_url=record.github_url,
        portfolio_url=record.portfolio_url,
        earliest_start_date=record.earliest_start_date,
        currently_enrolled_in_program=record.currently_enrolled_in_program,
        expected_graduation=record.expected_graduation,
        degree_pursuing=record.degree_pursuing,
        gender=record.gender,
        race_ethnicity=record.race_ethnicity,
        veteran_status=record.veteran_status,
        disability_status=record.disability_status,
    )


def candidate_record_to_profile(record: Candidate) -> CandidateProfile:
    projects: list[Project] = []
    for item in record.projects or []:
        if isinstance(item, dict):
            projects.append(Project.model_validate(item))
    experience: list[Experience] = []
    for item in record.experience or []:
        if isinstance(item, dict):
            experience.append(Experience.model_validate(item))
    education: list[Education] = []
    for item in record.education or []:
        if isinstance(item, dict):
            education.append(Education.model_validate(item))
    return CandidateProfile(
        id=f"cand-{record.id:03d}",
        name=record.name,
        email=record.email,
        phone=record.phone,
        skills=[item for item in (record.skills or []) if isinstance(item, str)],
        projects=projects,
        experience=experience,
        education=education,
        certifications=[item for item in (record.certifications or []) if isinstance(item, str)],
        strengths=[item for item in (record.strengths or []) if isinstance(item, str)],
        evidence_links=[item for item in (record.evidence_links or []) if isinstance(item, str)],
    )


def _match_record_to_schema(record: MatchScoreRecord, job_public_id: str) -> MatchScore:
    return MatchScore(
        job_id=job_public_id,
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


def load_application_materials_context(db: Session, job_id: str) -> ApplicationMaterialsContext:
    """Load stored grounded records only. Never creates or mutates rows."""

    job_record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job_record is None:
        raise MissingJobError()

    candidate_record = db.query(Candidate).order_by(Candidate.id.desc()).first()
    if candidate_record is None:
        raise MissingCandidateError()

    intelligence_record = (
        db.query(JobIntelligenceRecord)
        .filter(JobIntelligenceRecord.job_id == job_record.id)
        .first()
    )
    if intelligence_record is None:
        raise MissingJobIntelligenceError()
    intelligence = get_stored_job_intelligence(db, job_id)

    score_record = (
        db.query(MatchScoreRecord)
        .filter(
            MatchScoreRecord.job_id == job_record.id,
            MatchScoreRecord.candidate_id == candidate_record.id,
        )
        .order_by(MatchScoreRecord.id.desc())
        .first()
    )
    if score_record is None:
        raise MissingFitScoreError()

    preference_record = (
        db.query(TargetPreference)
        .filter(TargetPreference.candidate_id == candidate_record.id)
        .order_by(TargetPreference.id.desc())
        .first()
    )
    if preference_record is None:
        preference_record = (
            db.query(TargetPreference)
            .filter(TargetPreference.candidate_id.is_(None))
            .order_by(TargetPreference.id.desc())
            .first()
        )

    logger.info(
        "application_materials context loaded job_pk=%s candidate_pk=%s has_preferences=%s",
        job_record.id,
        candidate_record.id,
        preference_record is not None,
    )
    return ApplicationMaterialsContext(
        job=record_to_job(job_record),
        job_pk=job_record.id,
        candidate=candidate_record_to_profile(candidate_record),
        candidate_pk=candidate_record.id,
        intelligence=intelligence,
        fit_score=_match_record_to_schema(score_record, job_id),
        preferences=_preference_record_to_schema(preference_record) if preference_record else None,
        posting_text=f"{job_record.title}\n{job_record.company}\n{job_record.description}",
    )


def build_application_materials_prompt(context: ApplicationMaterialsContext) -> tuple[str, str]:
    """Construct the grounded generation prompt. Does not call a provider."""

    system_prompt = (
        "You write application materials only from the supplied candidate evidence "
        "and stored job requirements. Never invent skills, employers, titles, dates, "
        "metrics, percentages, currency values, technologies, education, or accomplishments. "
        "Never introduce a job requirement that is not in Job Intelligence or the posting. "
        "Preserve numeric types and units exactly as written in the evidence. "
        "Return one raw JSON object only, with no markdown or commentary."
    )
    payload = {
        "job": context.job.model_dump(mode="json"),
        "candidate": context.candidate.model_dump(mode="json"),
        "job_intelligence": context.intelligence.model_dump(mode="json"),
        "fit_score": context.fit_score.model_dump(mode="json"),
        "preferences": context.preferences.model_dump(mode="json") if context.preferences else None,
        "output_schema": _JSON_SHAPE,
    }
    user_prompt = (
        "Using only the JSON context below, draft tailored resume bullets, a cover letter, "
        "a recruiter message, and source-traceability notes.\n\n"
        f"{json.dumps(payload, ensure_ascii=True, default=str)}"
    )
    return system_prompt, user_prompt


def parse_application_materials_json(raw: str) -> ApplicationMaterialsStructuredOutput:
    """Parse provider text into the structured output schema. No persistence."""

    if not raw or not str(raw).strip():
        raise ApplicationMaterialsParseError()
    text = str(raw).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ApplicationMaterialsParseError() from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ApplicationMaterialsParseError() from exc
    if not isinstance(payload, dict):
        raise ApplicationMaterialsParseError()
    unknown = set(payload) - set(_STRUCTURED_FIELDS)
    if unknown:
        raise ApplicationMaterialsParseError()
    try:
        return ApplicationMaterialsStructuredOutput.model_validate(payload)
    except ValidationError as exc:
        raise ApplicationMaterialsParseError() from exc


def _corpus_from_strings(values: list[str]) -> str:
    return "\n".join(item for item in values if item)


def candidate_evidence_corpus(candidate: CandidateProfile) -> str:
    parts: list[str] = [
        candidate.name,
        candidate.email or "",
        candidate.phone or "",
        *candidate.skills,
        *candidate.certifications,
        *candidate.strengths,
        *candidate.evidence_links,
    ]
    for project in candidate.projects:
        parts.extend([project.name, project.description or "", project.url or "", *project.technologies])
    for item in candidate.experience:
        parts.extend(
            [item.title, item.company, item.start_date or "", item.end_date or "", *item.highlights]
        )
    for item in candidate.education:
        parts.extend(
            [item.institution, item.degree or "", item.field or "", item.graduation_year or ""]
        )
    return _corpus_from_strings(parts)


def job_evidence_corpus(context: ApplicationMaterialsContext) -> str:
    intel = context.intelligence
    parts = [
        context.posting_text,
        context.job.title,
        context.job.company,
        context.job.location or "",
        context.job.salary or "",
        *intel.required_skills,
        *intel.preferred_skills,
        *intel.education_requirements,
        *intel.tech_stack,
        intel.seniority or "",
        *intel.responsibilities,
        *intel.likely_interview_focus,
        *context.fit_score.matched_skills,
        *context.fit_score.partial_matches,
        *context.fit_score.missing_skills,
        context.fit_score.rationale,
    ]
    return _corpus_from_strings(parts)


def _normalized_haystack(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _claim_supported(claim: str, corpus: str) -> bool:
    needle = _normalized_haystack(claim)
    haystack = _normalized_haystack(corpus)
    if not needle:
        return True
    if needle in haystack:
        return True
    tokens = [token for token in re.findall(r"[a-z0-9+.#/-]{3,}", needle) if token not in {"the", "and", "for", "with"}]
    if not tokens:
        return True
    return all(token in haystack for token in tokens)


def _closed_skills_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for canonical in set(_ALIAS_TO_CANONICAL.values()):
        if _skill_in_text(canonical, text):
            found.add(canonical)
    return found


def ground_application_materials(
    output: ApplicationMaterialsStructuredOutput,
    context: ApplicationMaterialsContext,
) -> MaterialsGroundingReport:
    """Reject invented candidate claims and unevidenced job requirements."""

    report = MaterialsGroundingReport()
    candidate_corpus = candidate_evidence_corpus(context.candidate)
    job_corpus = job_evidence_corpus(context)
    allowed_skills = _closed_skills_in_text(candidate_corpus)
    missing_keys = {
        item.strip().lower() for item in context.fit_score.missing_skills if item.strip()
    }
    allowed_numbers = set(_NUMERIC_RE.findall(candidate_corpus)) | set(
        _NUMERIC_RE.findall(job_corpus)
    )

    texts = [
        *output.tailored_bullets,
        output.cover_letter_draft,
        output.recruiter_message,
        *output.source_traceability_notes,
    ]
    for text in texts:
        if not text or not text.strip():
            continue
        invented_skill = False
        for skill in _closed_skills_in_text(text):
            if skill not in allowed_skills:
                invented_skill = True
                report.invented_candidate_claims += 1
                if skill.lower() in missing_keys:
                    report.rejected_categories.append("missing_skill_as_strength")
                else:
                    report.rejected_categories.append("skill")
        for literal in _NUMERIC_RE.findall(text):
            if literal not in allowed_numbers:
                report.numeric_literals_rejected += 1
                report.rejected_categories.append("numeric")
        if invented_skill:
            report.rejected_claim_count += 1
        else:
            report.accepted_claim_count += 1

    logger.info(
        "application_materials grounding accepted=%s rejected=%s numeric_rejected=%s job_pk=%s",
        report.accepted_claim_count,
        report.rejected_claim_count,
        report.numeric_literals_rejected,
        context.job_pk,
    )
    return report


def draft_from_structured_output(
    output: ApplicationMaterialsStructuredOutput,
    context: ApplicationMaterialsContext,
    grounding: MaterialsGroundingReport,
) -> ApplicationMaterialsDraft:
    return ApplicationMaterialsDraft(
        job_id=context.job.id or "",
        tailored_bullets=list(output.tailored_bullets),
        cover_letter_draft=output.cover_letter_draft,
        recruiter_message=output.recruiter_message,
        source_traceability_notes=list(output.source_traceability_notes),
        grounding=grounding,
    )


def draft_to_persistence_payload(draft: ApplicationMaterialsDraft) -> dict[str, Any]:
    """Persistence-ready field mapping. Does not write to the database."""

    return {
        "tailored_bullets": list(draft.tailored_bullets),
        "cover_letter_draft": draft.cover_letter_draft,
        "recruiter_message": draft.recruiter_message,
        "source_traceability_notes": list(draft.source_traceability_notes),
        "approval_status": "pending_review",
    }


def draft_to_application_package(draft: ApplicationMaterialsDraft) -> ApplicationPackage:
    """Convert a grounded draft into the API package shape without persisting."""

    payload = draft_to_persistence_payload(draft)
    return ApplicationPackage(
        job_id=draft.job_id,
        tailored_bullets=payload["tailored_bullets"],
        cover_letter_draft=payload["cover_letter_draft"],
        recruiter_message=payload["recruiter_message"],
        source_traceability_notes=payload["source_traceability_notes"],
        approval_status="pending_review",
        eligibility_confirmed=False,
        eligibility_notes=None,
        decision_notes=None,
    )


def generate_grounded_application_materials(
    db: Session,
    job_id: str,
    *,
    generator: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator | None = None,
) -> ApplicationMaterialsDraft:
    """STUDENT-OWNED TODO: implement grounded application-materials generation.

    Complete this function later. The expected finished flow is:

    1. ``load_application_materials_context``
    2. ``build_application_materials_prompt``
    3. call the injectable ``generator`` (or default LLM client)
    4. ``parse_application_materials_json``
    5. ``ground_application_materials`` and reject ungounded claims
    6. return a draft (persistence stays a separate, one-line integration)

    Until implemented this function:
    - loads stored context so missing inputs fail with sanitized errors
    - does not call ``generator`` or any provider
    - does not persist application packages
    - raises ``ApplicationMaterialsNotImplementedError`` without prompt or
      provider details
    """

    context = load_application_materials_context(db, job_id)
    existing_packages = (
        db.query(ApplicationPackageRecord)
        .filter(ApplicationPackageRecord.job_id == context.job_pk)
        .count()
    )
    # Deliberately ignore generator so an unfinished path cannot leak prompts
    # or silently emit fabricated provider output.
    _ = generator
    logger.info(
        "application_materials generation skipped reason=not_implemented job_pk=%s existing_packages=%s",
        context.job_pk,
        existing_packages,
    )
    raise ApplicationMaterialsNotImplementedError()

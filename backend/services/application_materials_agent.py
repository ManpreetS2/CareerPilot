"""Application Materials Agent foundation.

This module is the student-owned grounded generator for resume bullets,
cover-letter drafts, recruiter messages, and source-traceability notes.

Production `POST /api/jobs/{job_id}/generate-materials` calls
`generate_grounded_application_materials`. GET routes never generate.
Placeholder `_mock_materials` is not on the production path.

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
from sqlalchemy.exc import IntegrityError

from backend.services.job_intelligence_service import (
    _has_usable_intelligence,
    get_stored_job_intelligence,
)

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
from backend.services.llm_structured_schemas import application_materials_llm_schema

logger = logging.getLogger(__name__)

ApplicationMaterialsGenerateFn = Callable[[str, str | None], str]

_STRUCTURED_FIELDS = (
    "tailored_bullets",
    "cover_letter_draft",
    "recruiter_message",
    "source_traceability_notes",
    "claim_evidence",
)

_PARENT_KINDS = frozenset({"experience", "project", "education", "certification"})
_ORG_NAME = r"[A-Za-z][A-Za-z0-9&.\'-]*(?:\s+[A-Za-z][A-Za-z0-9&.\'-]*){0,4}"
_AT_RE = re.compile(
    rf"\b(?:(?:work(?:ed|ing)?|intern(?:ed)?|employed|joined)\s+)?(?:at|from)\s+({_ORG_NAME})"
)
_TITLE_INFLATION_RE = re.compile(
    r"\b(?:promoted to|hired as)\s+(.+?)(?:[.!?]|$)|"
    r"\b(?:senior|staff|principal|director|distinguished|fellow|vp|vice president|head of)\b",
    re.I,
)
_PRODUCT_LAUNCH_RE = re.compile(
    r"\b(?:launched|shipped|released)\s+(?:a |an |the )?.{0,80}\bproduct\b",
    re.I,
)
_PROJECT_BUILD_RE = re.compile(
    rf"\b(?:[Bb]uilt|[Cc]reated|[Dd]eveloped)\s+({_ORG_NAME}?)"
    rf"(?=\s+(?:at|for|with|using|via|from|by|in|on|as|and|to)\b|[.,;!?]|$)"
)
_LEADERSHIP_RES = (
    re.compile(r"\bled (?:a |the )?(?:global )?.{0,50}\bteam\b", re.I),
    re.compile(r"\baward[- ]winning\b", re.I),
    re.compile(r"\bleadership results\b", re.I),
    re.compile(r"\btransformed\b.{0,60}", re.I),
    re.compile(r"\bglobal engineering\b", re.I),
    re.compile(r"\bcustomer retention\b", re.I),
)
_DOMAIN_PRODUCT_RE = re.compile(r"\b(?:healthcare|payments?|fintech)\b", re.I)
_JOB_REQ_FRAME_RE = re.compile(
    r"\b(?:this (?:role|job|position|internship|posting)|the (?:role|job|position|posting)|"
    r"you (?:require|need|prefer)|(?:role|job|position) requires?|requires?|"
    r"required|preferred|must have|looking for)\b",
    re.I,
)
_JOB_INTEREST_FRAME_RE = re.compile(
    r"\b(?:applying to|interested in|this (?:role|position|job|posting)|"
    r"the (?:role|position|job) at|for the .{0,40}\brole\b)\b",
    re.I,
)
_CANDIDATE_EMPLOYMENT_RE = re.compile(
    r"\b(?:worked at|work(?:ing)? at|employed (?:at|by)|joined|interned at|"
    r"my (?:experience|background|time|accomplishments?) (?:at|as)|"
    r"experience (?:at|with)|background at|accomplishments? at|"
    r"i (?:previously )?work(?:ed)? at|i work as|i have .{0,40} experience)\b",
    re.I,
)
_CANDIDATE_SELF_TITLE_RE = re.compile(
    r"\b(?:i(?:'m| am| was)|my background as|served as|i work as|i have)\s+(?:a |an )?",
    re.I,
)
_ACHIEVEMENT_VERB_RE = re.compile(
    r"\b(?:delivered|built|shipped|reduced|led|launched|implemented|developed|"
    r"accomplished|accomplishments?|worked|working|employed|interned|joined)\b",
    re.I,
)
_MAX_BULLETS = 8
_MAX_NOTES = 8
_MAX_BULLET_CHARS = 400
_MAX_COVER_CHARS = 4000
_MAX_RECRUITER_CHARS = 1500
_MAX_NOTE_CHARS = 400
_WORD_NUMBERS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}
_WORD_MAGNITUDES = {
    "dozens": "dozens",
    "hundreds": "hundreds",
    "thousands": "thousands",
    "millions": "millions",
    "decade": "decade",
}
_QUANTITY_UNITS = r"(?:years?|months?|internships?|apis?|users?|customers?|dollars?)"
_STRENGTH_RE = re.compile(
    r"\b(?:expertise|expert|proficient|skilled|mastery|strengths?|experienced|"
    r"i (?:have|had|used|built|led|launched|ran|managed)|my (?:experience|background)|"
    r"experience (?:with|in|using)|strong (?:in|with)|in production)\b",
    re.I,
)
_GAP_RE = re.compile(
    r"\b(?:gap|missing|lack|learn(?:ing)?|not (?:a |my )?current(?: candidate)? strength|"
    r"do not have|don't have|without prior)\b",
    re.I,
)
_GENERIC_PROPER_TOKENS = frozenset(
    {
        "api",
        "apis",
        "backend",
        "software",
        "engineer",
        "engineering",
        "intern",
        "internship",
        "role",
        "job",
        "team",
        "candidate",
        "evidence",
        "skills",
        "skill",
        "endpoints",
        "latency",
        "search",
        "p95",
        "cover",
        "letter",
        "recruiter",
        "application",
        "consideration",
        "chance",
        "discuss",
        "stored",
        "using",
        "happy",
        "built",
        "reduced",
        "worked",
        "led",
        "i",
        "my",
        "we",
        "computer",
        "science",
        "hello",
        "hi",
        "dear",
        "thank",
        "thanks",
        "please",
        "this",
        "that",
        "the",
        "a",
        "an",
        "our",
        "your",
        "their",
    }
)
_SENTENCE_START_IGNORE = frozenset(
    {
        "built",
        "reduced",
        "worked",
        "led",
        "launched",
        "produced",
        "transformed",
        "happy",
        "using",
        "how",
        "what",
        "used",
        "implemented",
        "developed",
        "created",
        "improved",
        "applying",
        "stored",
        "thank",
        "thanks",
        "i",
        "we",
        "my",
        "the",
        "this",
        "a",
        "an",
        "hello",
        "hi",
        "dear",
        "please",
        "eager",
        "excited",
        "looking",
        "writing",
        "joined",
        "interned",
        "employed",
    }
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


_MATERIALS_PROVIDER_ERROR_PRIORITY: dict[type[BaseException], int] = {
    # A provider that actually ran and produced something we rejected tells
    # the user far more than one that was never configured to begin with.
    ApplicationMaterialsGroundingError: 50,
    ApplicationMaterialsParseError: 40,
    LLMProviderError: 40,
    LLMEmptyResponseError: 40,
    # Lowest: with a provider order like "ollama,gemini" and no Gemini key,
    # this fires on every run and would otherwise bury the real failure,
    # reporting "generation is not configured" for a system that is
    # configured and did run. Mirrors _PROVIDER_ERROR_PRIORITY in
    # job_intelligence_service, which had this same defect.
    LLMConfigurationError: 10,
}


def _should_replace_materials_error(current: Exception | None, new: Exception) -> bool:
    if current is None:
        return True
    current_rank = _MATERIALS_PROVIDER_ERROR_PRIORITY.get(type(current), 0)
    new_rank = _MATERIALS_PROVIDER_ERROR_PRIORITY.get(type(new), 0)
    return new_rank > current_rank


class ApplicationMaterialsConflictError(ApplicationMaterialsError):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail
            or "Existing application materials are approved or awaiting edits and were not replaced."
        )


class StaleApplicationMaterialsError(ApplicationMaterialsError):
    def __init__(self, *, reviewed: bool = False) -> None:
        self.reviewed = reviewed
        if reviewed:
            super().__init__(
                "Reviewed application materials belong to a previous candidate profile "
                "and were not replaced."
            )
        else:
            super().__init__(
                "Stored application materials belong to a previous candidate profile. "
                "Generate materials for the current profile."
            )


class ApplicationMaterialsNotImplementedError(ApplicationMaterialsError):
    def __init__(self) -> None:
        super().__init__("Grounded application materials generation is not implemented yet.")


class ApplicationMaterialsGenerator(Protocol):
    """Injectable provider/generator boundary. Not called by the unfinished student function."""

    def __call__(self, prompt: str, system_prompt: str | None = None) -> str: ...


class MaterialsClaimEvidence(BaseModel):
    """Internal provider-output ledger. Not persisted on ApplicationPackage."""

    claim_excerpt: str = ""
    evidence_kind: str
    evidence_id: str


class ApplicationMaterialsStructuredOutput(BaseModel):
    """Structured-output schema the student generator must return."""

    tailored_bullets: list[str] = Field(default_factory=list)
    cover_letter_draft: str = ""
    recruiter_message: str = ""
    source_traceability_notes: list[str] = Field(default_factory=list)
    claim_evidence: list[MaterialsClaimEvidence] = Field(default_factory=list)


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
        return (
            self.rejected_claim_count == 0
            and self.numeric_literals_rejected == 0
            and self.invented_candidate_claims == 0
            and self.invented_job_requirements == 0
        )


@dataclass
class ApplicationMaterialsContext:
    job: Job
    job_pk: int
    candidate: CandidateProfile
    candidate_pk: int
    user_id: int
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


def preference_record_to_schema(record: TargetPreference) -> TargetPreferences:
    return _preference_record_to_schema(record)


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


def load_application_materials_context(db: Session, job_id: str, user_id: int) -> ApplicationMaterialsContext:
    """Load stored grounded records only. Never creates or mutates rows."""

    job_record = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job_record is None:
        raise MissingJobError()

    candidate_record = db.query(Candidate).filter(Candidate.user_id == user_id).first()
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
            .filter(TargetPreference.user_id == user_id)
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
        user_id=user_id,
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
        parsed = ApplicationMaterialsStructuredOutput.model_validate(payload)
    except ValidationError as exc:
        raise ApplicationMaterialsParseError() from exc
    _assert_useful_structured_output(parsed)
    return parsed


def _nonblank_items(values: list[str] | None) -> list[str]:
    return [item.strip() for item in (values or []) if str(item).strip()]


def _assert_useful_structured_output(parsed: ApplicationMaterialsStructuredOutput) -> None:
    bullets = _nonblank_items(parsed.tailored_bullets)
    notes = _nonblank_items(parsed.source_traceability_notes)
    cover = (parsed.cover_letter_draft or "").strip()
    recruiter = (parsed.recruiter_message or "").strip()
    if not bullets or not cover or not recruiter or not notes:
        raise ApplicationMaterialsParseError()
    if len(bullets) > _MAX_BULLETS or len(notes) > _MAX_NOTES:
        raise ApplicationMaterialsParseError()
    if len(cover) > _MAX_COVER_CHARS or len(recruiter) > _MAX_RECRUITER_CHARS:
        raise ApplicationMaterialsParseError()
    if any(len(item) > _MAX_BULLET_CHARS for item in bullets):
        raise ApplicationMaterialsParseError()
    if any(len(item) > _MAX_NOTE_CHARS for item in notes):
        raise ApplicationMaterialsParseError()
    parsed.tailored_bullets = bullets
    parsed.cover_letter_draft = cover
    parsed.recruiter_message = recruiter
    parsed.source_traceability_notes = notes


def _package_has_useful_content(record: ApplicationPackageRecord) -> bool:
    bullets = _nonblank_items(list(record.tailored_bullets or []))
    notes = _nonblank_items(list(record.source_traceability_notes or []))
    cover = (record.cover_letter_draft or "").strip()
    recruiter = (record.recruiter_message or "").strip()
    return bool(bullets and cover and recruiter and notes)


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


def job_requirement_corpus(context: ApplicationMaterialsContext) -> str:
    """Posting and grounded Job Intelligence only. Fit-score gaps are not job evidence."""

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
    ]
    if intel.years_experience:
        parts.append(f"{intel.years_experience} years")
    return _corpus_from_strings(parts)


def _normalized_haystack(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _claim_supported(claim: str, corpus: str) -> bool:
    """True when ``claim`` is supported by a single evidence corpus.

    Token fallback stays inside that one parent; it must not assemble
    support across unrelated experience, project, or education entries.
    """

    needle = _normalized_haystack(claim)
    haystack = _normalized_haystack(corpus)
    if not needle:
        return True
    if needle in haystack:
        return True
    tokens = [
        token
        for token in re.findall(r"[a-z0-9+.#/-]{3,}", needle)
        if token not in {"the", "and", "for", "with"}
    ]
    if not tokens:
        return False
    return all(token in haystack for token in tokens)


def _closed_skills_in_text(text: str) -> set[str]:
    found: set[str] = set()
    for canonical in set(_ALIAS_TO_CANONICAL.values()):
        if _skill_in_text(canonical, text):
            found.add(canonical)
    return found


def _normalize_numeric_value(raw: str) -> str:
    text = raw.replace(",", "").strip()
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _spans_overlap(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    start, end = span
    for left, right in occupied:
        if not (end <= left or start >= right):
            return True
    return False


def _extract_numeric_facts(text: str) -> list[tuple[str, str]]:
    occupied: list[tuple[int, int]] = []
    facts: list[tuple[str, str]] = []

    def take(pattern: re.Pattern[str], kind: str, group: int = 1) -> None:
        for match in pattern.finditer(text):
            span = match.span()
            if _spans_overlap(span, occupied):
                continue
            occupied.append(span)
            facts.append((kind, _normalize_numeric_value(match.group(group))))

    take(re.compile(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"), "usd")
    take(re.compile(r"(\d+(?:\.\d+)?)%"), "percent")
    take(re.compile(r"(\d+(?:\.\d+)?)[xX]\b"), "multiplier")
    take(re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\b", re.I), "years")
    take(re.compile(r"(\d+(?:\.\d+)?)\s*months?\b", re.I), "months")
    take(re.compile(r"\b((?:19|20)\d{2}-(?:0[1-9]|1[0-2]))\b"), "date")
    take(re.compile(r"\b((?:19|20)\d{2})\b"), "date")

    word_alt = "|".join(re.escape(word) for word in sorted(_WORD_NUMBERS, key=len, reverse=True))
    for match in re.finditer(rf"\b({word_alt})\s+({_QUANTITY_UNITS})\b", text, flags=re.I):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        unit = match.group(2).lower()
        value = _WORD_NUMBERS[match.group(1).lower()]
        if unit.startswith("year"):
            kind = "years"
        elif unit.startswith("month"):
            kind = "months"
        else:
            kind = "count"
        facts.append((kind, value))

    for match in re.finditer(
        rf"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)-(one|two|three|four|five|six|seven|eight|nine)\s+({_QUANTITY_UNITS})\b",
        text,
        flags=re.I,
    ):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        value = str(int(_WORD_NUMBERS[match.group(1).lower()]) + int(_WORD_NUMBERS[match.group(2).lower()]))
        unit = match.group(3).lower()
        kind = "years" if unit.startswith("year") else "months" if unit.startswith("month") else "count"
        facts.append((kind, value))

    ones = "|".join(
        re.escape(word)
        for word in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
    )
    for match in re.finditer(
        rf"\b({ones})\s+hundred(?:\s+and)?\s+({word_alt})?\s*({_QUANTITY_UNITS})\b",
        text,
        flags=re.I,
    ):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        value = int(_WORD_NUMBERS[match.group(1).lower()]) * 100
        if match.group(2):
            value += int(_WORD_NUMBERS[match.group(2).lower()])
        unit = match.group(3).lower()
        kind = "years" if unit.startswith("year") else "months" if unit.startswith("month") else "count"
        facts.append((kind, str(value)))

    for match in re.finditer(r"\ba\s+decade\b|(?<![A-Za-z])decade(?![A-Za-z])", text, flags=re.I):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        facts.append(("years", "decade"))

    magnitude_alt = "|".join(
        re.escape(word) for word in sorted(_WORD_MAGNITUDES, key=len, reverse=True)
    )
    for match in re.finditer(rf"\b({magnitude_alt})\s+of\s+[A-Za-z]+\b", text, flags=re.I):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        facts.append(("count", _WORD_MAGNITUDES[match.group(1).lower()]))

    for match in re.finditer(
        r"\b(?:million[- ]dollar|millions? of dollars?)\b", text, flags=re.I
    ):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        facts.append(("usd", "millions"))

    for match in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
        if _spans_overlap(match.span(), occupied):
            continue
        occupied.append(match.span())
        facts.append(("untyped", _normalize_numeric_value(match.group(0))))
    return facts


@dataclass(frozen=True)
class _EvidenceContext:
    kind: str
    evidence_id: str
    names: tuple[str, ...]
    text: str
    facts: frozenset[tuple[str, str]]
    bound_skills: frozenset[str]


def _phrase_in_text(phrase: str, text: str) -> bool:
    needle = (phrase or "").strip()
    if not needle:
        return False
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", text, flags=re.I) is not None


def _split_units(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def _build_evidence_contexts(context: ApplicationMaterialsContext) -> list[_EvidenceContext]:
    candidate = context.candidate
    global_skills = _closed_skills_in_text("\n".join(candidate.skills))
    contexts: list[_EvidenceContext] = []

    for index, item in enumerate(candidate.experience):
        text = "\n".join(
            [item.title, item.company, item.start_date or "", item.end_date or "", *item.highlights]
        )
        names = tuple(value for value in (item.company, item.title) if value and value.strip())
        bound = _closed_skills_in_text(text) - global_skills
        contexts.append(
            _EvidenceContext(
                "experience",
                f"experience:{index}",
                names,
                text,
                frozenset(_extract_numeric_facts(text)),
                frozenset(bound),
            )
        )
    for index, item in enumerate(candidate.projects):
        text = "\n".join(
            [item.name, item.description or "", item.url or "", *item.technologies]
        )
        bound = _closed_skills_in_text(text) - global_skills
        contexts.append(
            _EvidenceContext(
                "project",
                f"project:{index}",
                tuple(value for value in (item.name,) if value.strip()),
                text,
                frozenset(_extract_numeric_facts(text)),
                frozenset(bound),
            )
        )
    for index, item in enumerate(candidate.education):
        text = "\n".join(
            [
                item.institution,
                item.degree or "",
                item.field or "",
                item.graduation_year or "",
            ]
        )
        names = tuple(
            value
            for value in (item.institution, item.degree, item.field)
            if value and value.strip()
        )
        contexts.append(
            _EvidenceContext(
                "education",
                f"education:{index}",
                names,
                text,
                frozenset(_extract_numeric_facts(text)),
                frozenset(),
            )
        )
    for index, cert in enumerate(candidate.certifications):
        if not str(cert).strip():
            continue
        contexts.append(
            _EvidenceContext(
                "certification",
                f"certification:{index}",
                (str(cert).strip(),),
                str(cert),
                frozenset(_extract_numeric_facts(str(cert))),
                frozenset(),
            )
        )
    skill_text = "\n".join(candidate.skills)
    contexts.append(
        _EvidenceContext(
            "skill",
            "skill:profile",
            tuple(skill for skill in candidate.skills if skill.strip()),
            skill_text,
            frozenset(),
            frozenset(),
        )
    )
    identity = "\n".join(
        [
            candidate.name,
            candidate.email or "",
            candidate.phone or "",
            *candidate.strengths,
            *candidate.evidence_links,
        ]
    )
    name_parts = tuple(part for part in candidate.name.split() if part.strip())
    contexts.append(
        _EvidenceContext(
            "candidate",
            "candidate:profile",
            (candidate.name, *name_parts),
            identity,
            frozenset(_extract_numeric_facts(identity)),
            frozenset(),
        )
    )
    job_text = job_requirement_corpus(context)
    contexts.append(
        _EvidenceContext(
            "job",
            "job:posting",
            tuple(value for value in (context.job.company, context.job.title) if value.strip()),
            job_text,
            frozenset(_extract_numeric_facts(job_text)),
            frozenset(_closed_skills_in_text(job_text)),
        )
    )
    return contexts


def _mask_names(text: str, names: list[str]) -> str:
    masked = text
    for name in sorted({item for item in names if item.strip()}, key=len, reverse=True):
        masked = re.sub(rf"(?i)(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", " ", masked)
    return masked


def _leftover_proper_tokens(text: str, known_names: list[str], skill_labels: set[str]) -> list[str]:
    masked = _mask_names(text, known_names)
    leftover: list[str] = []
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9+#./'-]*\b", masked):
        token = match.group(0)
        key = token.lower()
        if key in _GENERIC_PROPER_TOKENS or key in _SENTENCE_START_IGNORE:
            continue
        if any(_skill_in_text(skill, token) for skill in skill_labels):
            continue
        leftover.append(token)
    return leftover


def ground_application_materials(
    output: ApplicationMaterialsStructuredOutput,
    context: ApplicationMaterialsContext,
) -> MaterialsGroundingReport:
    """Reject invented candidate claims and unevidenced job requirements."""

    report = MaterialsGroundingReport()
    contexts = _build_evidence_contexts(context)
    parents = [item for item in contexts if item.kind in _PARENT_KINDS]
    job_ctx = next(item for item in contexts if item.kind == "job")
    global_skills = _closed_skills_in_text("\n".join(context.candidate.skills))
    all_closed_skills = set(_ALIAS_TO_CANONICAL.values())
    missing_skills = {
        item.strip()
        for item in context.fit_score.missing_skills
        if item.strip()
    }
    missing_keys = {item.lower() for item in missing_skills}
    candidate_names: list[str] = []
    for item in contexts:
        if item.kind != "job":
            candidate_names.extend(item.names)
    candidate_names.extend(context.candidate.skills)
    candidate_names.extend(context.candidate.certifications)
    candidate_names.extend(context.candidate.strengths)
    stored_titles = [exp.title for exp in context.candidate.experience if exp.title]
    job_title = (context.job.title or "").strip()

    by_id = {item.evidence_id: item for item in contexts}

    def reject(category: str, *, candidate: bool = False, job: bool = False, numeric: bool = False) -> None:
        report.rejected_categories.append(category)
        if candidate:
            report.invented_candidate_claims += 1
        if job:
            report.invented_job_requirements += 1
        if numeric:
            report.numeric_literals_rejected += 1

    for ref in output.claim_evidence:
        ctx = by_id.get(ref.evidence_id)
        excerpt = (ref.claim_excerpt or "").strip()
        valid = (
            ctx is not None
            and ctx.kind == ref.evidence_kind
            and excerpt
            and _claim_supported(excerpt, ctx.text)
        )
        if not valid:
            reject("invalid_evidence_ref", candidate=True)

    units: list[tuple[str, str]] = []
    for bullet in output.tailored_bullets:
        if bullet and bullet.strip():
            units.append(("strength", bullet.strip()))
    for sentence in _split_units(output.cover_letter_draft):
        units.append(("prose", sentence))
    for sentence in _split_units(output.recruiter_message):
        units.append(("prose", sentence))
    for note in output.source_traceability_notes:
        if note and note.strip():
            units.append(("note", note.strip()))

    for kind, unit in units:
        before_rejected = (
            report.invented_candidate_claims,
            report.invented_job_requirements,
            report.numeric_literals_rejected,
            len(report.rejected_categories),
        )
        named_parents: set[str] = set()
        for parent in parents:
            if any(_phrase_in_text(name, unit) for name in parent.names if name.strip()):
                named_parents.add(parent.evidence_id)
            if any(_skill_in_text(skill, unit) for skill in parent.bound_skills):
                named_parents.add(parent.evidence_id)

        job_framed = bool(_JOB_REQ_FRAME_RE.search(unit))
        job_interest = bool(_JOB_INTEREST_FRAME_RE.search(unit))
        employment_claim = bool(_CANDIDATE_EMPLOYMENT_RE.search(unit))
        strength_context = kind == "strength" or bool(_STRENGTH_RE.search(unit))
        gap_context = bool(_GAP_RE.search(unit))
        job_quantity = job_framed and not strength_context

        unit_facts = _extract_numeric_facts(unit)
        common_owners: set[str] | None = None
        for fact in unit_facts:
            if job_quantity:
                if fact not in job_ctx.facts:
                    reject("numeric", job=True, numeric=True)
                common_owners = set()
                continue
            owners = {parent.evidence_id for parent in parents if fact in parent.facts}
            if not owners:
                reject("numeric", candidate=True, numeric=True)
                common_owners = set()
                continue
            common_owners = owners if common_owners is None else common_owners & owners
        if unit_facts and not job_quantity:
            if common_owners is None:
                common_owners = set()
            if named_parents:
                if not (named_parents & common_owners):
                    reject("cross_entry", candidate=True)
            elif not common_owners:
                reject("numeric", candidate=True, numeric=True)
            elif len(common_owners) == 0:
                reject("cross_entry", candidate=True)

        if len(named_parents) > 1:
            reject("cross_entry", candidate=True)
        elif named_parents and unit_facts and common_owners is not None and not job_quantity:
            if named_parents and common_owners and not (named_parents <= common_owners or named_parents & common_owners):
                reject("cross_entry", candidate=True)

        for skill in _closed_skills_in_text(unit):
            in_profile = skill in global_skills or any(
                _skill_in_text(skill, parent.text) and skill not in parent.bound_skills
                for parent in parents
            )
            bound_parents = {parent.evidence_id for parent in parents if skill in parent.bound_skills}
            in_job = skill in job_ctx.bound_skills or _skill_in_text(skill, job_ctx.text)
            missing = skill.lower() in missing_keys or skill in missing_skills

            if bound_parents and named_parents and not (bound_parents & named_parents) and named_parents - bound_parents:
                reject("cross_entry", candidate=True)

            if job_framed and not strength_context:
                if not in_job:
                    reject("invented_job_requirement", job=True)
                continue
            if missing and strength_context and not gap_context:
                reject("missing_skill_as_strength", candidate=True)
                continue
            if not in_profile and not bound_parents:
                if in_job and job_framed and not strength_context:
                    continue
                if missing and not gap_context and (strength_context or kind != "note"):
                    reject("missing_skill_as_strength", candidate=True)
                elif not in_job or strength_context:
                    reject("skill", candidate=True)

        def _job_name_allowed() -> bool:
            # Job-interest phrasing may name the employer/title, but it must not
            # launder an unsupported achievement in the same sentence.
            if employment_claim or kind == "strength":
                return False
            if _ACHIEVEMENT_VERB_RE.search(unit):
                return False
            return bool(job_interest or job_framed)

        def _matches_job_name(value: str) -> bool:
            if _phrase_in_text(value, job_ctx.text):
                return True
            return any(
                _phrase_in_text(value, name) or _phrase_in_text(name, value)
                for name in job_ctx.names
                if name.strip()
            )

        for match in _AT_RE.finditer(unit):
            org = match.group(1).strip()
            if org.lower() in _GENERIC_PROPER_TOKENS or org.split()[0].lower() in {"this", "the", "our", "your", "a", "an"}:
                continue
            known = any(_phrase_in_text(org, name) or _phrase_in_text(name, org) for name in candidate_names)
            if known:
                continue
            if _job_name_allowed() and _matches_job_name(org):
                continue
            reject("invented_employer", candidate=True)

        if job_title:
            self_title = re.search(
                rf"\b(?:i(?:'m| am| was)|i work as|my background as|served as|i have)\s+"
                rf"(?:a |an )?{re.escape(job_title)}(?:\s+experience)?\b",
                unit,
                flags=re.I,
            )
            if self_title and not any(_phrase_in_text(job_title, title) for title in stored_titles):
                reject("invented_title", candidate=True)

        if _TITLE_INFLATION_RE.search(unit):
            title_ok = any(
                _phrase_in_text(parent.names[1] if len(parent.names) > 1 else "", unit)
                or any(_phrase_in_text(name, unit) for name in parent.names)
                for parent in parents
                if parent.kind == "experience"
            )
            if not any(_phrase_in_text(title, unit) for title in stored_titles if title):
                if not title_ok:
                    reject("invented_title", candidate=True)
            seniority_claimed = bool(
                re.search(
                    r"\b(?:senior|staff|principal|director|distinguished|fellow|vice president)\b",
                    unit,
                    flags=re.I,
                )
            )
            if seniority_claimed and not any(
                re.search(
                    r"\b(?:senior|staff|principal|director|distinguished|fellow|vice president)\b",
                    title,
                    flags=re.I,
                )
                for title in stored_titles
            ):
                reject("invented_title", candidate=True)

        project_claim_spans: list[tuple[int, int]] = []
        for match in _PROJECT_BUILD_RE.finditer(unit):
            product = match.group(1).strip()
            if product.lower() in _GENERIC_PROPER_TOKENS:
                continue
            if product.split()[0].lower() in _SENTENCE_START_IGNORE:
                continue
            project_names = [project.name for project in context.candidate.projects]
            if product and not any(
                _phrase_in_text(product, name) or _phrase_in_text(name, product) for name in project_names
            ):
                # "Python APIs" is skill + generic — only skip when every token
                # is a known skill or filler. A named product that merely
                # mentions a skill (e.g. "Campus Connect with Python") remains
                # an invented project claim.
                tokens = product.split()
                if tokens and all(
                    token.lower() in _GENERIC_PROPER_TOKENS
                    or token.lower() in {"with", "using", "via", "and", "or", "for", "in", "on", "a", "an", "the"}
                    or any(_skill_in_text(skill, token) for skill in all_closed_skills)
                    for token in tokens
                ):
                    continue
                project_claim_spans.append(match.span(1))
                reject("invented_project", candidate=True)

        if _PRODUCT_LAUNCH_RE.search(unit) or _DOMAIN_PRODUCT_RE.search(unit):
            domain_ok = _claim_supported(unit, job_ctx.text) or any(
                _claim_supported(unit, parent.text) for parent in parents
            )
            if _DOMAIN_PRODUCT_RE.search(unit):
                domain_ok = any(
                    _DOMAIN_PRODUCT_RE.search(parent.text) for parent in [*parents, job_ctx]
                )
            phrase_ok = False
            launch = _PRODUCT_LAUNCH_RE.search(unit)
            if launch is not None:
                phrase_ok = any(_claim_supported(launch.group(0), parent.text) for parent in parents)
            if not domain_ok and not phrase_ok:
                reject("invented_project", candidate=True)

        for pattern in _LEADERSHIP_RES:
            match = pattern.search(unit)
            if match is None:
                continue
            if not any(_claim_supported(match.group(0), parent.text) for parent in parents):
                reject("invented_accomplishment", candidate=True)

        leftover = _leftover_proper_tokens(unit, candidate_names, all_closed_skills)
        for token in leftover:
            if _job_name_allowed() and _matches_job_name(token):
                continue
            token_span = None
            for match in re.finditer(rf"\b{re.escape(token)}\b", unit):
                token_span = match.span()
                break
            if token_span is not None and any(
                token_span[0] >= start and token_span[1] <= end for start, end in project_claim_spans
            ):
                # Already counted as an invented project name in this unit.
                continue
            reject("invented_employer", candidate=True)

        if job_framed:
            job_skills_in_unit = _closed_skills_in_text(unit)
            for skill in job_skills_in_unit:
                if skill not in job_ctx.bound_skills and not _skill_in_text(skill, job_ctx.text):
                    reject("invented_job_requirement", job=True)

        after_rejected = (
            report.invented_candidate_claims,
            report.invented_job_requirements,
            report.numeric_literals_rejected,
            len(report.rejected_categories),
        )
        if after_rejected == before_rejected:
            report.accepted_claim_count += 1
        else:
            report.rejected_claim_count += 1

    logger.info(
        "application_materials grounding accepted=%s rejected=%s invented_candidate=%s invented_job=%s numeric_rejected=%s category_count=%s job_pk=%s",
        report.accepted_claim_count,
        report.rejected_claim_count,
        report.invented_candidate_claims,
        report.invented_job_requirements,
        report.numeric_literals_rejected,
        len(report.rejected_categories),
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


_PLACEHOLDER_MARKERS = ("placeholder bullet", "placeholder draft")


def _looks_like_placeholder(record: ApplicationPackageRecord) -> bool:
    notes = " ".join(record.source_traceability_notes or []).lower()
    cover = (record.cover_letter_draft or "").lower()
    return any(marker in notes or marker in cover for marker in _PLACEHOLDER_MARKERS)


def is_grounded_package_record(record: ApplicationPackageRecord | None) -> bool:
    if record is None:
        return False
    if _looks_like_placeholder(record):
        return False
    if not getattr(record, "grounded", False):
        return False
    return _package_has_useful_content(record)


def is_override_package_record(record: ApplicationPackageRecord | None) -> bool:
    """An unverified package the owner explicitly chose to keep. Held to
    every content check a grounded package is, minus the grounding result
    itself — the override waives verification, not substance."""
    if record is None:
        return False
    if _looks_like_placeholder(record):
        return False
    if not getattr(record, "grounding_override", False):
        return False
    return _package_has_useful_content(record)


def is_package_ready_for_apply(
    db: Session, package: ApplicationPackageRecord | None, user_id: int
) -> bool:
    """Shared gate for approval and both Assisted Apply paths.

    An explicitly overridden package is allowed through: the owner has said
    they want to apply to this job knowing the draft is not fully evidence-
    backed. Every other check below still applies, and the package stays
    marked unverified so the approval screen and the extension panel both
    say so before anything is filled into a real form.
    """
    if not (is_grounded_package_record(package) or is_override_package_record(package)):
        return False
    assert package is not None
    if package.user_id != user_id:
        return False
    if package.candidate_id is None:
        return False
    current_candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    if current_candidate is None or package.candidate_id != current_candidate.id:
        return False
    return True


_PROTECTED_APPROVAL_STATUSES = frozenset({"approved", "edit_requested"})


def _draft_from_record(record: ApplicationPackageRecord, job_id: str) -> ApplicationMaterialsDraft:
    return ApplicationMaterialsDraft(
        job_id=job_id,
        tailored_bullets=list(record.tailored_bullets or []),
        cover_letter_draft=record.cover_letter_draft or "",
        recruiter_message=record.recruiter_message or "",
        source_traceability_notes=list(record.source_traceability_notes or []),
        grounding=MaterialsGroundingReport(),
    )


def _default_materials_generator(prompt: str, system_prompt: str | None = None) -> str:
    return invoke_provider_generate(
        get_llm_client(),
        prompt,
        system_prompt,
        application_materials_llm_schema(),
    )


def _invoke_materials_generator(
    generator: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator,
    prompt: str,
    system_prompt: str,
) -> str:
    return generator(prompt, system_prompt)


def _structured_output_from_generator(
    invoke: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator,
    context: ApplicationMaterialsContext,
    user_prompt: str,
    system_prompt: str,
) -> ApplicationMaterialsStructuredOutput:
    parsed: ApplicationMaterialsStructuredOutput | None = None
    last_parse_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = _invoke_materials_generator(invoke, user_prompt, system_prompt)
        except LLMEmptyResponseError:
            last_parse_error = ApplicationMaterialsParseError()
            logger.info(
                "application_materials structured_attempt=%s outcome=empty job_pk=%s",
                attempt + 1,
                context.job_pk,
            )
            continue
        except LLMProviderError:
            logger.info(
                "application_materials structured_attempt=%s outcome=provider_exhausted job_pk=%s",
                attempt + 1,
                context.job_pk,
            )
            raise
        except LLMConfigurationError:
            raise
        except TypeError:
            logger.info(
                "application_materials structured_attempt=%s outcome=generator_typeerror job_pk=%s",
                attempt + 1,
                context.job_pk,
            )
            raise ApplicationMaterialsParseError() from None
        try:
            parsed = parse_application_materials_json(raw)
            break
        except ApplicationMaterialsParseError as exc:
            last_parse_error = exc
            logger.info(
                "application_materials structured_attempt=%s outcome=invalid_structured_output job_pk=%s",
                attempt + 1,
                context.job_pk,
            )
            continue
    if parsed is None:
        raise last_parse_error or ApplicationMaterialsParseError()
    return parsed


def _persist_grounded_draft(
    db: Session,
    context: ApplicationMaterialsContext,
    draft: ApplicationMaterialsDraft,
    existing: ApplicationPackageRecord | None = None,
    *,
    grounded: bool = True,
    unsupported_claims: list[str] | None = None,
) -> ApplicationPackageRecord:
    """grounded=False is reachable only through an explicit per-job override
    (see generate_grounded_application_materials). Such a record is stored
    with grounding_override set and the unsupported categories attached, so
    nothing downstream can mistake it for a verified package."""
    payload = draft_to_persistence_payload(draft)
    # Deduplicate while keeping first-seen order: the report lists one entry
    # per rejected claim, so a draft that invented the same employer a dozen
    # times yields a dozen identical categories. A reviewer needs the set of
    # problems, not the tally.
    unsupported = list(dict.fromkeys(unsupported_claims or []))
    same_candidate = existing is not None and existing.candidate_id == context.candidate_pk
    if existing is not None and existing.approval_status in _PROTECTED_APPROVAL_STATUSES:
        if same_candidate:
            raise ApplicationMaterialsConflictError()
        raise StaleApplicationMaterialsError(reviewed=True)
    if existing is not None and is_grounded_package_record(existing) and same_candidate:
        return existing
    if existing is not None:
        existing.candidate_id = context.candidate_pk
        existing.user_id = context.user_id
        existing.tailored_bullets = list(payload["tailored_bullets"])
        existing.cover_letter_draft = payload["cover_letter_draft"]
        existing.recruiter_message = payload["recruiter_message"]
        existing.source_traceability_notes = list(payload["source_traceability_notes"])
        existing.approval_status = "pending_review"
        existing.grounded = grounded
        existing.grounding_override = not grounded
        existing.unsupported_claims = unsupported
        record = existing
    else:
        record = ApplicationPackageRecord(
            job_id=context.job_pk,
            user_id=context.user_id,
            candidate_id=context.candidate_pk,
            tailored_bullets=list(payload["tailored_bullets"]),
            cover_letter_draft=payload["cover_letter_draft"],
            recruiter_message=payload["recruiter_message"],
            source_traceability_notes=list(payload["source_traceability_notes"]),
            approval_status="pending_review",
            grounded=grounded,
            grounding_override=not grounded,
            unsupported_claims=unsupported,
        )
        db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = (
            db.query(ApplicationPackageRecord)
            .filter(
                ApplicationPackageRecord.job_id == context.job_pk,
                ApplicationPackageRecord.user_id == context.user_id,
            )
            .first()
        )
        if (
            winner is not None
            and is_grounded_package_record(winner)
            and winner.candidate_id == context.candidate_pk
            and winner.user_id == context.user_id
        ):
            logger.info(
                "application_materials persist recovered unique_conflict job_pk=%s",
                context.job_pk,
            )
            return winner
        raise ApplicationMaterialsConflictError(
            "Stored application materials could not be recovered safely after a write conflict."
        )
    except Exception:
        db.rollback()
        raise
    logger.info("application_materials persisted job_pk=%s", context.job_pk)
    return record


def generate_grounded_application_materials(
    db: Session,
    job_id: str,
    user_id: int,
    *,
    generator: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator | None = None,
    override_grounding: bool = False,
) -> ApplicationMaterialsDraft:
    """Generate grounded application materials from stored candidate, job, and score evidence.

    override_grounding is the owner's explicit, per-job decision to keep a
    draft whose claims could not all be verified against stored evidence —
    for applying to a role they are stretching for. It never defaults on,
    is never inferred, and never persists to another job. The resulting
    record is stored with grounded=False and grounding_override=True, and
    carries the unsupported categories, so every later reader can tell it
    apart from a verified package.
    """

    context = load_application_materials_context(db, job_id, user_id)
    if not _has_usable_intelligence(context.intelligence):
        raise MissingJobIntelligenceError()

    existing = (
        db.query(ApplicationPackageRecord)
        .filter(
            ApplicationPackageRecord.job_id == context.job_pk,
            ApplicationPackageRecord.user_id == user_id,
        )
        .first()
    )
    same_candidate = existing is not None and existing.candidate_id == context.candidate_pk
    if existing is not None and existing.approval_status in _PROTECTED_APPROVAL_STATUSES:
        if same_candidate and is_grounded_package_record(existing):
            logger.info("application_materials reused protected_package job_pk=%s", context.job_pk)
            return _draft_from_record(existing, job_id)
        if not same_candidate:
            raise StaleApplicationMaterialsError(reviewed=True)
        raise ApplicationMaterialsConflictError()
    if same_candidate and is_grounded_package_record(existing):
        logger.info("application_materials reused stored_package job_pk=%s", context.job_pk)
        assert existing is not None
        return _draft_from_record(existing, job_id)

    system_prompt, user_prompt = build_application_materials_prompt(context)

    def _complete_with(invoke: ApplicationMaterialsGenerateFn | ApplicationMaterialsGenerator) -> ApplicationMaterialsDraft:
        parsed = _structured_output_from_generator(invoke, context, user_prompt, system_prompt)
        report = ground_application_materials(parsed, context)
        logger.info(
            "application_materials grounding accepted=%s rejected=%s invented_candidate=%s invented_job=%s numeric=%s job_pk=%s",
            report.accepted_claim_count,
            report.rejected_claim_count,
            report.invented_candidate_claims,
            report.invented_job_requirements,
            report.numeric_literals_rejected,
            context.job_pk,
        )
        if not report.grounded and not override_grounding:
            raise ApplicationMaterialsGroundingError()
        draft = draft_from_structured_output(parsed, context, report)
        record = _persist_grounded_draft(
            db,
            context,
            draft,
            existing=existing,
            grounded=report.grounded,
            unsupported_claims=report.rejected_categories,
        )
        if not report.grounded:
            logger.warning(
                "application_materials stored UNVERIFIED via explicit override "
                "rejected=%s categories=%s job_pk=%s",
                report.rejected_claim_count,
                report.rejected_categories,
                context.job_pk,
            )
        return _draft_from_record(record, job_id)

    if uses_injected_generator(generator):
        return _complete_with(generator)  # type: ignore[arg-type]

    last_error: Exception | None = None
    schema = application_materials_llm_schema()
    # See _should_replace_materials_error: without ranking, a later
    # unconfigured provider's error replaces the real one from the provider
    # that actually ran.
    for provider in configured_provider_names():
        def _provider_generate(
            prompt: str,
            system_prompt: str | None = None,
            *,
            _provider: str = provider,
        ) -> str:
            return invoke_provider_generate(
                get_llm_client(_provider), prompt, system_prompt, schema
            )

        try:
            return _complete_with(_provider_generate)
        except (
            ApplicationMaterialsParseError,
            ApplicationMaterialsGroundingError,
            LLMProviderError,
            LLMEmptyResponseError,
            LLMConfigurationError,
        ) as exc:
            if _should_replace_materials_error(last_error, exc):
                last_error = exc
            logger.info(
                "application_materials provider sequence failed category=%s job_pk=%s",
                type(exc).__name__,
                context.job_pk,
            )
            continue
    if last_error is not None:
        raise last_error
    raise ApplicationMaterialsParseError()

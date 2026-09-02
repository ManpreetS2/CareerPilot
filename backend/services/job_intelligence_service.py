"""Grounded extraction and persistence for structured job requirements."""

from __future__ import annotations

import html
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import JobIntelligenceRecord, JobRecord
from backend.schemas.schemas import JobIntelligence
from backend.services.analysis_service import (
    JobNotFoundError,
    _canonical_skill_key,
    _explicit_year_requirements,
    _skill_in_text,
    canonicalize_skill,
)
from backend.services.llm_client import (
    LLMAuthError,
    LLMConfigurationError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMRateLimitError,
    get_llm_client,
)
from backend.services.llm_provider_sequence import (
    configured_provider_names,
    invoke_provider_generate,
    uses_injected_generator,
)
from backend.services.llm_structured_schemas import job_intelligence_llm_schema
from backend.services.extraction_pool import (
    WorkerResult,
    generate_with_provider_slot,
    run_extraction_batch,
)
from backend.services.extraction_task import INTELLIGENCE_EXTRACTION_VERSION, ExtractionTask
from backend.services.job_content import source_fingerprint

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str, str | None], str]
MAX_PLAUSIBLE_EXPERIENCE_YEARS = 50

_SYSTEM_PROMPT = (
    "Extract factual job requirements from a stored posting. "
    "Do not infer, rewrite, strengthen, or add requirements. "
    "Return one raw JSON object only, with no markdown or commentary."
)

_JSON_SHAPE = """{
  "required_skills": ["exact skill phrase"],
  "preferred_skills": ["exact skill phrase"],
  "years_experience": null,
  "education_requirements": ["exact degree or field requirement"],
  "tech_stack": ["exact technology phrase"],
  "seniority": null,
  "responsibilities": ["exact responsibility phrase"],
  "likely_interview_focus": ["grounded posting topic"]
}"""

_DEGREE_ALIASES: dict[str, tuple[str, ...]] = {
    "associate": ("associate degree", "associate's degree"),
    "bachelor": (
        "bachelor degree",
        "bachelor's degree",
        "bachelors degree",
        "bachelor of science",
        "bachelor of arts",
    ),
    "master": (
        "master degree",
        "master's degree",
        "masters degree",
        "master of science",
        "master of arts",
        "master of business administration",
        "mba",
    ),
    "phd": ("phd", "ph.d.", "doctoral degree", "doctorate"),
}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "computer science": ("computer science", "computing"),
    "software engineering": ("software engineering",),
    "information systems": ("information systems",),
    "computer engineering": ("computer engineering",),
    "electrical engineering": ("electrical engineering",),
    "data science": ("data science",),
}

_SENIORITY_MODIFIERS = {
    "entry",
    "junior",
    "jr",
    "mid",
    "middle",
    "level",
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "intern",
    "associate",
    "director",
    "head",
    "chief",
}

_NON_TECH_SKILL_LABELS = _SENIORITY_MODIFIERS | {
    "analyst",
    "architect",
    "consultant",
    "designer",
    "developer",
    "engineer",
    "manager",
    "platform",
    "position",
    "role",
    "scientist",
    "software",
    "specialist",
}

_STRUCTURED_FIELDS = (
    "required_skills",
    "preferred_skills",
    "years_experience",
    "education_requirements",
    "tech_stack",
    "seniority",
    "responsibilities",
    "likely_interview_focus",
)

_REQUIRED_SIGNALS = (
    "required",
    "requirements",
    "must have",
    "must-have",
    "minimum",
    "qualifications",
)

_STRONG_REQUIRED_SIGNALS = (
    "required",
    "must have",
    "must-have",
    "minimum",
)

_PREFERRED_SIGNALS = (
    "preferred",
    "nice to have",
    "nice-to-have",
    "bonus",
    "plus",
)

_TECHNICAL_CONTEXT = re.compile(
    r"\b(?:experience\s+with|familiarity\s+with|knowledge\s+of|proficiency\s+in|"
    r"skills?|stack|technologies|technology|tools?|using|uses?)\b",
    flags=re.I,
)


class JobIntelligenceError(Exception):
    """Base class for safe job-requirement extraction errors."""


class PostingEvidenceError(JobIntelligenceError):
    def __init__(self) -> None:
        super().__init__("This job does not contain enough posting evidence for extraction.")


class JobIntelligenceNotFoundError(JobIntelligenceError):
    def __init__(self) -> None:
        super().__init__("Job requirements have not been extracted.")


class StructuredIntelligenceError(JobIntelligenceError):
    def __init__(self) -> None:
        super().__init__("The extraction service did not return valid structured requirements.")


class EmptyGroundedIntelligenceError(JobIntelligenceError):
    def __init__(self) -> None:
        super().__init__("No supported job requirements were found.")


_PROVIDER_ERROR_PRIORITY: dict[type[BaseException], int] = {
    PostingEvidenceError: 50,
    EmptyGroundedIntelligenceError: 50,
    StructuredIntelligenceError: 40,
    LLMRateLimitError: 40,
    LLMAuthError: 30,
    LLMProviderError: 40,
    LLMEmptyResponseError: 40,
    LLMConfigurationError: 10,
}


def _should_replace_provider_error(current: Exception | None, new: Exception) -> bool:
    if current is None:
        return True
    current_rank = _PROVIDER_ERROR_PRIORITY.get(type(current), 0)
    new_rank = _PROVIDER_ERROR_PRIORITY.get(type(new), 0)
    return new_rank > current_rank


def build_extraction_prompts(job: JobRecord | ExtractionTask) -> tuple[str, str]:
    """Build a strict prompt containing only the stored posting title and description."""
    user_prompt = f"""Extract structured requirements from this job posting.

Rules:
- Copy skill labels exactly as they appear in the posting, without trailing punctuation.
- Copy only requirements explicitly supported by the posting.
- Keep required, preferred, and technology-stack skills in their local posting categories.
- Copy complete technology and responsibility phrases; do not use substrings.
- Do not infer years, education, seniority, sponsorship, or work authorization.
- Preserve all numbers, percentages, currencies, dates, and units exactly.
- Interview-focus topics must be traceable to an explicit posting topic or retained requirement.
- Use null for absent scalar values and [] for absent list values.
- Return raw JSON only. Do not add markdown, commentary, or extra keys.

JSON shape:
{_JSON_SHAPE}

JOB TITLE:
\"\"\"
{job.title}
\"\"\"

JOB DESCRIPTION:
\"\"\"
{job.description}
\"\"\"
"""
    return _SYSTEM_PROMPT, user_prompt


def _retry_prompt(original: str) -> str:
    return (
        original
        + "\n\nIMPORTANT: Previous output was invalid or empty. Return one complete raw "
        "JSON object with every key present. Use literal phrases copied from the posting "
        "text above — do not paraphrase. Use [] or null for any category with no "
        "supported evidence; do not leave a key out."
    )


def _posting_source(job: JobRecord | ExtractionTask) -> str:
    title = html.unescape((job.title or "").strip())
    description = html.unescape((job.description or "").strip())
    return f"{title}\n{description}"


def _require_posting_evidence(job: JobRecord | ExtractionTask) -> None:
    title = (job.title or "").strip()
    description = (job.description or "").strip()
    if len(title) < 2 or len(description) < 12 or len(description.split()) < 2:
        raise PostingEvidenceError()


def has_usable_posting_evidence(job: JobRecord | ExtractionTask) -> bool:
    """Return whether the stored posting is sufficient for provider extraction."""
    try:
        _require_posting_evidence(job)
    except PostingEvidenceError:
        return False
    return True


def _parse_structured_output(raw: str) -> JobIntelligence:
    if not raw or not str(raw).strip():
        raise StructuredIntelligenceError()
    try:
        payload = json.loads(str(raw).strip())
    except json.JSONDecodeError as exc:
        raise StructuredIntelligenceError() from exc
    if not isinstance(payload, dict):
        raise StructuredIntelligenceError()
    payload = dict(payload)
    payload.pop("job_id", None)
    unknown = set(payload) - set(_STRUCTURED_FIELDS)
    if unknown:
        raise StructuredIntelligenceError()
    if any(field not in payload for field in _STRUCTURED_FIELDS):
        raise StructuredIntelligenceError()
    if isinstance(payload.get("years_experience"), bool):
        raise StructuredIntelligenceError()
    try:
        intelligence = JobIntelligence.model_validate(payload)
    except ValidationError as exc:
        raise StructuredIntelligenceError() from exc
    return intelligence


def _normalize_extracted_label(value: str) -> str:
    """Strip whitespace and trailing punctuation models often add in JSON arrays."""
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned.rstrip(".,;:!")


def _exact_phrase_supported(value: str, source: str) -> bool:
    claim = re.sub(r"\s+", " ", value.strip())
    if not claim:
        return False
    pattern = re.escape(claim).replace(r"\ ", r"\s+")
    return (
        re.search(
            rf"(?<![a-z0-9+.#-]){pattern}(?![a-z0-9+#-])(?!(?:\.[a-z0-9]))",
            source,
            flags=re.I,
        )
        is not None
    )


def _ground_skills(
    intelligence: JobIntelligence,
    source: str,
) -> tuple[list[str], list[str], list[str], int]:
    priority = {"stack": 0, "preferred": 1, "required": 2}
    selected: dict[str, tuple[str, str, int]] = {}
    removed = 0
    position = 0
    for labels in (
        intelligence.required_skills,
        intelligence.preferred_skills,
        intelligence.tech_stack,
    ):
        for raw in labels:
            label = _normalize_extracted_label(raw)
            position += 1
            if not label:
                removed += 1
                continue
            canonical = canonicalize_skill(label)
            if canonical is None:
                supported = (
                    _canonical_skill_key(label) not in _NON_TECH_SKILL_LABELS
                    and _exact_phrase_supported(label, source)
                    and _unknown_skill_has_explicit_context(label, source)
                )
            else:
                supported = _skill_in_text(label, source)
            if not supported:
                removed += 1
                continue
            kind = _local_skill_kind(label, source)
            if kind is None:
                removed += 1
                continue
            key = _canonical_skill_key(label)
            output_label = canonical or label
            existing = selected.get(key)
            if existing is None:
                selected[key] = (kind, output_label, position)
            elif priority[kind] > priority[existing[0]]:
                selected[key] = (kind, output_label, existing[2])
            else:
                removed += 1

    ordered = sorted(selected.values(), key=lambda item: item[2])
    required = [label for kind, label, _ in ordered if kind == "required"]
    preferred = [label for kind, label, _ in ordered if kind == "preferred"]
    stack = [label for kind, label, _ in ordered if kind == "stack"]
    return required, preferred, stack, removed


def _has_local_signal(text: str, signals: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])",
            text,
            flags=re.I,
        )
        for signal in signals
    )


def _classify_skill_context(text: str, heading_kind: str) -> str:
    preferred = _has_local_signal(text, _PREFERRED_SIGNALS)
    if preferred and not _has_local_signal(text, _STRONG_REQUIRED_SIGNALS):
        return "preferred"
    if _has_local_signal(text, _REQUIRED_SIGNALS):
        return "required"
    if preferred:
        return "preferred"
    return heading_kind


def _skill_label_in_text(label: str, text: str) -> bool:
    if canonicalize_skill(label) is not None:
        return _skill_in_text(label, text)
    return _exact_phrase_supported(label, text)


def _unknown_skill_has_explicit_context(label: str, source: str) -> bool:
    heading_is_technical = False
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            heading_is_technical = False
            continue
        if stripped.endswith(":"):
            heading_is_technical = (
                _has_local_signal(
                    stripped,
                    _REQUIRED_SIGNALS + _PREFERRED_SIGNALS,
                )
                or _TECHNICAL_CONTEXT.search(stripped) is not None
            )
        elif _section_heading_kind(stripped) is not None:
            heading_is_technical = _section_heading_kind(stripped) == "technical"
        clauses = re.split(
            r"\s*(?:;|\|)\s*|(?<=[.!?])\s+",
            stripped,
        )
        for clause in clauses:
            if not _exact_phrase_supported(label, clause):
                continue
            if (
                heading_is_technical
                or _has_local_signal(
                    clause,
                    _REQUIRED_SIGNALS + _PREFERRED_SIGNALS,
                )
                or _TECHNICAL_CONTEXT.search(clause) is not None
            ):
                return True
    return False


def _section_heading_kind(text: str) -> str | None:
    normalized = re.sub(r"[^a-z]+", " ", text.lower()).strip()
    if normalized in {
        "requirements",
        "qualifications",
        "preferred qualifications",
        "skills",
        "technical skills",
        "technology",
        "technology stack",
        "tools",
    } or re.fullmatch(
        r"(?:(?:key|minimum|preferred|required|technical)\s+)?"
        r"(?:qualifications|requirements|skills)",
        normalized,
    ):
        return "technical"
    if normalized in {
        "about",
        "about us",
        "benefits",
        "company",
        "company overview",
        "compensation",
        "culture",
        "equal opportunity",
        "interview focus",
        "interview topics",
        "responsibilities",
        "the role",
        "what you will do",
        "what you ll do",
    } or (
        normalized.startswith("about ")
        or normalized.startswith("why ")
        or "benefit" in normalized
        or "perk" in normalized
        or normalized.endswith(" culture")
        or normalized.endswith(" company")
        or normalized.startswith("our culture")
        or normalized.startswith("who we are")
    ):
        return "other"
    return None


def _local_skill_kind(label: str, source: str) -> str | None:
    """Classify each supported occurrence using its nearest section or clause."""
    priority = {"stack": 0, "preferred": 1, "required": 2}
    best: str | None = None
    heading_kind = "stack"
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            heading_kind = "stack"
            continue
        section_kind = _section_heading_kind(stripped)
        if stripped.endswith(":"):
            heading_kind = _classify_skill_context(stripped, "stack")
        elif section_kind == "technical":
            heading_kind = _classify_skill_context(stripped, "stack")
        elif section_kind == "other":
            heading_kind = "stack"
        clauses = re.split(
            r"\s*(?:;|\|)\s*|(?<=[.!?])\s+",
            stripped,
        )
        for clause in clauses:
            if not _skill_label_in_text(label, clause):
                continue
            kind = _classify_skill_context(clause, heading_kind)
            if best is None or priority[kind] > priority[best]:
                best = kind
    return best


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
            text,
            flags=re.I,
        )
        for alias in aliases
    )


def _education_signature(text: str) -> tuple[set[str], set[str]]:
    degrees = {
        canonical
        for canonical, aliases in _DEGREE_ALIASES.items()
        if _contains_alias(text, aliases)
    }
    fields = {
        canonical
        for canonical, aliases in _FIELD_ALIASES.items()
        if _contains_alias(text, aliases)
    }
    return degrees, fields


def _education_has_unrecognized_content(text: str) -> bool:
    residual = text.lower()
    aliases = [
        alias
        for groups in (*_DEGREE_ALIASES.values(), *_FIELD_ALIASES.values())
        for alias in groups
    ]
    for alias in sorted(aliases, key=len, reverse=True):
        residual = re.sub(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
            " ",
            residual,
        )
    remaining = set(re.findall(r"[a-z]+", residual))
    connectors = {
        "a",
        "an",
        "and",
        "degree",
        "degrees",
        "field",
        "in",
        "minimum",
        "of",
        "or",
        "qualification",
        "qualifications",
        "related",
        "required",
        "the",
    }
    return bool(remaining - connectors)


def _ground_education(items: list[str], source: str) -> tuple[list[str], int]:
    source_signatures = [
        _education_signature(line)
        for line in source.splitlines()
        if line.strip()
    ]
    kept: list[str] = []
    removed = 0
    seen: set[tuple[tuple[str, ...], tuple[str, ...], str]] = set()
    for raw in items:
        claim = raw.strip()
        degrees, fields = _education_signature(claim)
        has_unrecognized = _education_has_unrecognized_content(claim)
        signature = (
            tuple(sorted(degrees)),
            tuple(sorted(fields)),
            _normalized_line(claim) if has_unrecognized else "",
        )
        if not claim or (not degrees and not fields) or signature in seen:
            removed += 1
            continue
        if has_unrecognized and not _exact_phrase_supported(
            claim,
            source,
        ):
            removed += 1
            continue
        if not any(
            degrees <= source_degrees
            and fields <= source_fields
            and (degrees or fields)
            for source_degrees, source_fields in source_signatures
        ):
            removed += 1
            continue
        seen.add(signature)
        kept.append(claim)
    return kept, removed


def _ground_years(value: int | None, source: str) -> tuple[int | None, int]:
    if value is None:
        return None, 0
    if isinstance(value, bool) or value <= 0 or value > MAX_PLAUSIBLE_EXPERIENCE_YEARS:
        return None, 1
    explicit = _explicit_year_requirements(source)
    if value not in explicit or not _positive_year_requirement(value, source):
        return None, 1
    return value, 0


def _positive_year_requirement(value: int, source: str) -> bool:
    negative = re.compile(
        r"\b(?:at\s+most|do\s+not\s+need|does\s+not\s+need|less\s+than|"
        r"max(?:imum)?|no\s+more\s+than|not\s+required|not\s+require|"
        r"need\s+not|not\s+(?:expected|mandatory|necessary|needed|required)|"
        r"optional|unnecessary|unneeded|up\s+to|"
        r"without\s+requiring)\b",
        flags=re.I,
    )
    for clause in re.split(
        r"[\n;|]+|(?<=[.!?])\s+(?=[A-Z])",
        source,
    ):
        if not re.search(
            rf"(?<!\d){value}(?:\s*\+)?\s+(?:years?|yrs?)\b",
            clause,
            flags=re.I,
        ):
            continue
        if not re.search(r"\bexperience\b", clause, flags=re.I):
            continue
        if negative.search(clause) or re.search(
            rf"\bno\b[^.;|]*\b{value}\s+(?:years?|yrs?)\b",
            clause,
            flags=re.I,
        ):
            continue
        return True
    return False


def _normalize_seniority(value: str) -> list[str]:
    return re.findall(r"[a-z]+", value.lower())


def _seniority_phrase_supported(value: str, source: str) -> bool:
    words = _normalize_seniority(value)
    pattern = r"(?<![a-z0-9])" + r"[\s-]+".join(map(re.escape, words)) + r"(?![a-z0-9])"
    for match in re.finditer(pattern, source.lower()):
        prefix_words = re.findall(r"[a-z]+", source[: match.start()].lower())
        suffix_words = re.findall(r"[a-z]+", source[match.end() :].lower())
        previous = prefix_words[-1] if prefix_words else None
        following = suffix_words[0] if suffix_words else None
        if previous in _SENIORITY_MODIFIERS or following in _SENIORITY_MODIFIERS:
            continue
        return True
    return False


def _seniority_supported(value: str | None, job: JobRecord | ExtractionTask) -> bool:
    if not value or not value.strip():
        return False
    words = _normalize_seniority(value)
    if not words or any(word not in _SENIORITY_MODIFIERS for word in words):
        return False
    title = job.title
    lowered_title = title.lower()
    if (
        words == ["lead"]
        and re.search(r"\blead[\s-]+generation\b", lowered_title)
    ) or (
        words == ["entry"]
        and re.search(r"\bdata[\s-]+entry\b", lowered_title)
    ):
        title = ""
    contexts = [title]
    role_context = re.compile(
        r"\b(?:analyst|architect|consultant|designer|developer|engineer|intern|"
        r"level|manager|position|role|scientist|seniority|specialist)\b",
        flags=re.I,
    )
    contexts.extend(
        line
        for line in job.description.splitlines()
        if role_context.search(line)
        and not re.search(r"\byou\s+will\s+lead\b", line, flags=re.I)
        and not re.search(
            r"\b(?:associate'?s?|bachelor'?s?|degree|education|master'?s?)\b",
            line,
            flags=re.I,
        )
    )
    return any(_seniority_phrase_supported(value, context) for context in contexts)


def _normalized_line(value: str) -> str:
    value = value.strip().lstrip("-*•").strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"^responsibilit(?:y|ies)\s*:\s*", "", value, flags=re.I)
    value = re.sub(
        r"^(?:likely\s+)?interview(?:\s+(?:topics?|focus))?\s*:\s*",
        "",
        value,
        flags=re.I,
    )
    return value.rstrip(" .;:").lower()


def _split_into_clauses(text: str) -> list[str]:
    """Split a dense paragraph into exact sentences/clauses. Punctuation-based
    only — no fuzzy or semantic matching."""
    return [
        clause.strip()
        for clause in re.split(r"\s*(?:;|\|)\s*|(?<=[.!?])\s+(?=[A-Z])", text)
        if clause.strip()
    ]


def _add_line_and_clauses(lines: set[str], text: str) -> None:
    lines.add(_normalized_line(text))
    for clause in _split_into_clauses(text):
        lines.add(_normalized_line(clause))


def _responsibility_source_lines(source: str) -> set[str]:
    lines: set[str] = set()
    in_responsibilities = False
    cue_lines_allowed = True
    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            in_responsibilities = False
            continue
        inline_responsibility = re.match(
            r"^(?:duties|responsibilities)\s*:\s*(.+)$",
            stripped,
            flags=re.I,
        )
        if inline_responsibility:
            _add_line_and_clauses(lines, inline_responsibility.group(1))
            in_responsibilities = True
            cue_lines_allowed = True
            continue
        normalized_heading = re.sub(r"[^a-z]+", " ", stripped.lower()).strip()
        if normalized_heading in {
            "duties",
            "responsibilities",
            "the role",
            "what you will do",
        }:
            in_responsibilities = True
            cue_lines_allowed = True
            continue
        if stripped.endswith(":") or _section_heading_kind(stripped) is not None:
            in_responsibilities = False
            cue_lines_allowed = False
            continue
        if in_responsibilities or re.search(
            r"\b(?:responsible\s+for|you\s+will|your\s+duties\s+include)\b",
            stripped,
            flags=re.I,
        ) and cue_lines_allowed and not re.search(
            r"\b(?:benefits?|compensation|equity|perks?|salary)\b",
            stripped,
            flags=re.I,
        ):
            _add_line_and_clauses(lines, stripped)
    return {line for line in lines if line}


def _ground_exact_phrases(items: list[str], source: str) -> tuple[list[str], int]:
    source_lines = _responsibility_source_lines(source)
    kept: list[str] = []
    removed = 0
    seen: set[str] = set()
    for raw in items:
        claim = raw.strip()
        normalized = _normalized_line(claim)
        if (
            not normalized
            or normalized in seen
            or normalized not in source_lines
        ):
            removed += 1
            continue
        seen.add(normalized)
        kept.append(claim)
    return kept, removed


def _ground_interview_focus(
    items: list[str],
    source: str,
    *,
    skills: list[str],
    education: list[str],
    responsibilities: list[str],
) -> tuple[list[str], int]:
    traceable = {
        _normalized_line(value)
        for value in [*skills, *education, *responsibilities]
        if value.strip()
    }
    source_lines = _interview_topic_source_lines(source)
    kept: list[str] = []
    removed = 0
    seen: set[str] = set()
    for raw in items:
        claim = raw.strip()
        normalized = _normalized_line(claim)
        exact_posting_topic = normalized in source_lines
        if not normalized or normalized in seen or (
            normalized not in traceable and not exact_posting_topic
        ):
            removed += 1
            continue
        seen.add(normalized)
        kept.append(claim)
    return kept, removed


def _interview_topic_source_lines(source: str) -> set[str]:
    topics: set[str] = set()
    in_interview_topics = False
    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            in_interview_topics = False
            continue
        inline_topic = re.match(
            r"^(?:interview|interview focus|interview topics)\s*:\s*(.+)$",
            stripped,
            flags=re.I,
        )
        if inline_topic:
            topics.add(_normalized_line(inline_topic.group(1)))
            in_interview_topics = True
            continue
        normalized_heading = re.sub(r"[^a-z]+", " ", stripped.lower()).strip()
        if normalized_heading in {"interview", "interview focus", "interview topics"}:
            in_interview_topics = True
            continue
        if stripped.endswith(":") or _section_heading_kind(stripped) is not None:
            in_interview_topics = False
            continue
        if in_interview_topics:
            topics.add(_normalized_line(stripped))
    return {topic for topic in topics if topic}


def ground_job_intelligence(
    raw: JobIntelligence | dict[str, Any],
    job: JobRecord | ExtractionTask,
) -> tuple[JobIntelligence, dict[str, int]]:
    """Drop unsupported claims and return category-level removal counts."""
    raw_years_is_boolean = isinstance(raw, dict) and isinstance(
        raw.get("years_experience"),
        bool,
    )
    intelligence = (
        raw if isinstance(raw, JobIntelligence) else JobIntelligence.model_validate(raw)
    )
    source = _posting_source(job)
    required, preferred, stack, removed_skills = _ground_skills(intelligence, source)
    years, removed_years = _ground_years(
        None if raw_years_is_boolean else intelligence.years_experience,
        source,
    )
    if raw_years_is_boolean:
        removed_years = 1
    education, removed_education = _ground_education(
        intelligence.education_requirements,
        source,
    )
    seniority = (
        intelligence.seniority
        if _seniority_supported(intelligence.seniority, job)
        else None
    )
    removed_seniority = int(bool(intelligence.seniority) and seniority is None)
    responsibilities, removed_responsibilities = _ground_exact_phrases(
        intelligence.responsibilities,
        source,
    )
    all_skills = [*required, *preferred, *stack]
    interview_focus, removed_focus = _ground_interview_focus(
        intelligence.likely_interview_focus,
        source,
        skills=all_skills,
        education=education,
        responsibilities=responsibilities,
    )
    counts = {
        "skills": removed_skills,
        "years": removed_years,
        "education": removed_education,
        "seniority": removed_seniority,
        "responsibilities": removed_responsibilities,
        "interview_focus": removed_focus,
    }
    grounded = JobIntelligence(
        job_id=job.public_id,
        required_skills=required,
        preferred_skills=preferred,
        years_experience=years,
        education_requirements=education,
        tech_stack=stack,
        seniority=seniority,
        responsibilities=responsibilities,
        likely_interview_focus=interview_focus,
    )
    return grounded, counts


def _has_usable_intelligence(intelligence: JobIntelligence) -> bool:
    return any(getattr(intelligence, field) for field in _STRUCTURED_FIELDS)


def _record_to_schema(record: JobIntelligenceRecord, public_id: str) -> JobIntelligence:
    return JobIntelligence(
        job_id=public_id,
        required_skills=list(record.required_skills or []),
        preferred_skills=list(record.preferred_skills or []),
        years_experience=record.years_experience,
        education_requirements=list(record.education_requirements or []),
        tech_stack=list(record.tech_stack or []),
        seniority=record.seniority,
        responsibilities=list(record.responsibilities or []),
        likely_interview_focus=list(record.likely_interview_focus or []),
    )


def _load_job(db: Session, public_id: str) -> JobRecord:
    job = db.query(JobRecord).filter(JobRecord.public_id == public_id).first()
    if job is None:
        raise JobNotFoundError()
    return job


def get_stored_job_intelligence(db: Session, public_id: str) -> JobIntelligence:
    """Read stored intelligence without creating or mutating data."""
    job = _load_job(db, public_id)
    record = (
        db.query(JobIntelligenceRecord)
        .filter(JobIntelligenceRecord.job_id == job.id)
        .first()
    )
    if record is None:
        raise JobIntelligenceNotFoundError()
    return _record_to_schema(record, job.public_id)


def _extract_structured(
    job: JobRecord | ExtractionTask,
    generate_fn: GenerateFn | None,
    *,
    provider: str | None = None,
    use_slots: bool = False,
    worker_result: WorkerResult | None = None,
) -> JobIntelligence:
    system_prompt, user_prompt = build_extraction_prompts(job)
    schema = job_intelligence_llm_schema()
    generator = generate_fn
    if generator is None:
        if use_slots:
            def generator(prompt: str, system: str | None) -> str:
                text, slot_id = generate_with_provider_slot(
                    provider or "gemini",
                    prompt,
                    system,
                    schema,
                )
                if worker_result is not None:
                    worker_result.slot_id = slot_id
                    worker_result.attempts += 1
                    worker_result.provider = provider or "gemini"
                return text
        else:
            client = get_llm_client(provider or "gemini")
            generator = lambda prompt, system: invoke_provider_generate(
                client, prompt, system, schema
            )

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = generator(
                user_prompt if attempt == 0 else _retry_prompt(user_prompt),
                system_prompt,
            )
            structured = _parse_structured_output(raw)
            if not any(
                getattr(structured, field)
                for field in _STRUCTURED_FIELDS
            ):
                raise StructuredIntelligenceError()
            return structured
        except LLMProviderError:
            raise
        except LLMEmptyResponseError as exc:
            last_error = StructuredIntelligenceError()
            last_error.__cause__ = exc
        except StructuredIntelligenceError as exc:
            last_error = exc
        logger.warning(
            "job intelligence structured attempt=%s job_pk=%s category=invalid_output",
            attempt + 1,
            job.id,
        )
    raise StructuredIntelligenceError() from last_error


def _persist_grounded(
    db: Session,
    job: JobRecord,
    intelligence: JobIntelligence,
) -> JobIntelligence:
    record = (
        db.query(JobIntelligenceRecord)
        .filter(JobIntelligenceRecord.job_id == job.id)
        .first()
    )
    payload = {
        "required_skills": list(intelligence.required_skills),
        "preferred_skills": list(intelligence.preferred_skills),
        "years_experience": intelligence.years_experience,
        "education_requirements": list(intelligence.education_requirements),
        "tech_stack": list(intelligence.tech_stack),
        "seniority": intelligence.seniority,
        "responsibilities": list(intelligence.responsibilities),
        "likely_interview_focus": list(intelligence.likely_interview_focus),
        "source_fingerprint": source_fingerprint(job.title, job.description),
        "extraction_version": INTELLIGENCE_EXTRACTION_VERSION,
    }
    schema_payload = {
        key: payload[key]
        for key in (
            "required_skills",
            "preferred_skills",
            "years_experience",
            "education_requirements",
            "tech_stack",
            "seniority",
            "responsibilities",
            "likely_interview_focus",
        )
    }
    if record is None:
        record = JobIntelligenceRecord(job_id=job.id, **payload)
        db.add(record)
    else:
        for key, value in payload.items():
            setattr(record, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        record = (
            db.query(JobIntelligenceRecord)
            .filter(JobIntelligenceRecord.job_id == job.id)
            .first()
        )
        if record is None:
            raise
        for key, value in payload.items():
            setattr(record, key, value)
        db.commit()
    return JobIntelligence(job_id=job.public_id, **schema_payload)


def extraction_task_from_job(job: JobRecord) -> ExtractionTask:
    return ExtractionTask(
        kind="job_intelligence",
        job_public_id=job.public_id,
        job_pk=job.id,
        source_fingerprint=source_fingerprint(job.title, job.description),
        extraction_version=INTELLIGENCE_EXTRACTION_VERSION,
        title=job.title,
        company=job.company,
        description=job.description or "",
        content_status=job.content_status,
    )


def intelligence_record_is_current(
    job: JobRecord,
    record: JobIntelligenceRecord | None,
) -> bool:
    if record is None:
        return False
    stored_fp = record.source_fingerprint
    stored_ver = record.extraction_version
    if not stored_fp:
        return True
    return (
        stored_fp == source_fingerprint(job.title, job.description)
        and int(stored_ver or 0) == INTELLIGENCE_EXTRACTION_VERSION
    )


def extract_intelligence_on_worker(
    task: ExtractionTask,
    generate_fn: GenerateFn | None,
) -> WorkerResult:
    """Provider/parse/ground only. No SQLAlchemy Session."""
    started = time.perf_counter()
    result = WorkerResult()
    try:
        _require_posting_evidence(task)
        if uses_injected_generator(generate_fn):
            structured = _extract_structured(task, generate_fn)
            grounded, _counts = ground_job_intelligence(structured, task)
            if not _has_usable_intelligence(grounded):
                raise EmptyGroundedIntelligenceError()
            result.intelligence = grounded
            return result
        last_error: Exception | None = None
        for index, provider in enumerate(configured_provider_names()):
            try:
                structured = _extract_structured(
                    task,
                    None,
                    provider=provider,
                    use_slots=True,
                    worker_result=result,
                )
                grounded, _counts = ground_job_intelligence(structured, task)
                if not _has_usable_intelligence(grounded):
                    raise EmptyGroundedIntelligenceError()
                result.intelligence = grounded
                result.provider = provider
                if index > 0:
                    result.fallbacks += 1
                return result
            except (
                StructuredIntelligenceError,
                EmptyGroundedIntelligenceError,
                LLMProviderError,
                LLMEmptyResponseError,
                LLMConfigurationError,
            ) as exc:
                if index > 0:
                    result.fallbacks += 1
                if _should_replace_provider_error(last_error, exc):
                    last_error = exc
                logger.warning(
                    "job intelligence provider sequence failed category=%s job_pk=%s",
                    type(exc).__name__,
                    task.job_pk,
                )
                continue
        result.error = last_error or StructuredIntelligenceError()
        return result
    except Exception as exc:  # noqa: BLE001 — isolate one job
        result.error = exc
        return result
    finally:
        result.provider_duration_ms = int((time.perf_counter() - started) * 1000)


def extract_job_intelligence(
    db: Session,
    public_id: str,
    *,
    generate_fn: GenerateFn | None = None,
) -> JobIntelligence:
    """Extract, ground, and upsert requirements with the request session."""
    try:
        job = _load_job(db, public_id)
        _require_posting_evidence(job)
        logger.info("job intelligence extraction started job_pk=%s", job.id)
        if uses_injected_generator(generate_fn):
            structured = _extract_structured(job, generate_fn)
            return _ground_and_persist_intelligence(db, job, structured)
        last_error: Exception | None = None
        for provider in configured_provider_names():
            try:
                structured = _extract_structured(job, None, provider=provider)
                return _ground_and_persist_intelligence(db, job, structured)
            except (
                StructuredIntelligenceError,
                EmptyGroundedIntelligenceError,
                LLMProviderError,
                LLMEmptyResponseError,
                LLMConfigurationError,
            ) as exc:
                if _should_replace_provider_error(last_error, exc):
                    last_error = exc
                logger.warning(
                    "job intelligence provider sequence failed category=%s job_pk=%s",
                    type(exc).__name__,
                    job.id,
                )
                db.rollback()
                continue
        if last_error is not None:
            raise last_error
        raise StructuredIntelligenceError()
    except Exception:
        db.rollback()
        raise


def extract_job_intelligence_batch(
    db: Session,
    public_ids: list[str],
    *,
    generate_fn: GenerateFn | None = None,
    force: bool = False,
) -> list[JobIntelligence | BaseException | None]:
    """Parallelize Job Intelligence provider extraction only.

    JobRequirementProfile / Verified Fit / Find Jobs stay on their existing
    deterministic paths. This does not create a third source of truth.
    """
    ordered_jobs: list[JobRecord | None] = []
    cached: dict[str, JobIntelligence] = {}
    pending: list[ExtractionTask] = []
    failures: dict[str, BaseException] = {}
    for public_id in public_ids:
        try:
            job = _load_job(db, public_id)
        except JobNotFoundError as exc:
            ordered_jobs.append(None)
            failures[public_id] = exc
            continue
        ordered_jobs.append(job)
        if not has_usable_posting_evidence(job):
            failures[public_id] = PostingEvidenceError()
            continue
        record = (
            db.query(JobIntelligenceRecord)
            .filter(JobIntelligenceRecord.job_id == job.id)
            .first()
        )
        if not force and intelligence_record_is_current(job, record):
            assert record is not None
            cached[job.public_id] = _record_to_schema(record, job.public_id)
            continue
        pending.append(extraction_task_from_job(job))

    outcome = run_extraction_batch(pending, extract_intelligence_on_worker, generate_fn=generate_fn)
    outcome.metrics.cache_hits = len(cached)
    outcome.metrics.queued = len(pending)

    stored_by_id: dict[str, JobIntelligence | BaseException | None] = dict(cached)
    stored_by_id.update(failures)
    jobs_by_pk = {job.id: job for job in ordered_jobs if job is not None}
    for task in pending:
        result = outcome.results.get(task.job_public_id) or WorkerResult(
            error=StructuredIntelligenceError()
        )
        job = jobs_by_pk.get(task.job_pk)
        if job is None:
            stored_by_id[task.job_public_id] = JobNotFoundError()
            continue
        try:
            db.refresh(job)
        except Exception:  # noqa: BLE001 — reload if this session cannot refresh
            job = db.query(JobRecord).filter(JobRecord.id == task.job_pk).first()
            if job is None:
                stored_by_id[task.job_public_id] = JobNotFoundError()
                continue
            jobs_by_pk[task.job_pk] = job
        current_fp = source_fingerprint(job.title, job.description)
        if current_fp != task.source_fingerprint:
            stored_by_id[task.job_public_id] = None
            logger.warning(
                "job intelligence discarded stale snapshot job_pk=%s",
                task.job_pk,
            )
            continue
        if result.error is not None or result.intelligence is None:
            stored_by_id[task.job_public_id] = result.error
            continue
        try:
            stored_by_id[task.job_public_id] = _persist_grounded(db, job, result.intelligence)
        except Exception as exc:  # noqa: BLE001 — keep other jobs
            db.rollback()
            stored_by_id[task.job_public_id] = exc
            logger.warning(
                "job intelligence persist failed category=%s job_pk=%s",
                type(exc).__name__,
                job.id,
            )

    return [stored_by_id.get(public_id) for public_id in public_ids]


def _ground_and_persist_intelligence(
    db: Session,
    job: JobRecord,
    structured: JobIntelligence,
) -> JobIntelligence:
    grounded, counts = ground_job_intelligence(structured, job)
    logger.info(
        "job intelligence grounding job_pk=%s counts=%s",
        job.id,
        counts,
    )
    if not _has_usable_intelligence(grounded):
        raise EmptyGroundedIntelligenceError()
    stored = _persist_grounded(db, job, grounded)
    logger.info(
        "job intelligence persisted job_pk=%s categories=%s",
        job.id,
        sum(bool(getattr(stored, field)) for field in _STRUCTURED_FIELDS),
    )
    return stored

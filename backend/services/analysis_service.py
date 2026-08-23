"""Deterministic explainable Fit & Gap scoring. No LLM calls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import (
    Candidate,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
)
from backend.schemas.schemas import MatchScore

logger = logging.getLogger(__name__)

# Component weights. Unavailable components are omitted and remaining weights renormalized.
WEIGHT_SKILLS = 0.55
WEIGHT_EXPERIENCE = 0.20
WEIGHT_EDUCATION = 0.10
WEIGHT_LOCATION = 0.05
WEIGHT_PREFERENCES = 0.10

# Within the skill component. Renormalize if one group is empty.
SKILL_REQUIRED_SHARE = 0.75
SKILL_PREFERRED_SHARE = 0.25

FULL_MATCH = 1.0
PARTIAL_MATCH = 0.5
MISSING_MATCH = 0.0

APPLY_THRESHOLD = 80.0
CONSIDER_THRESHOLD = 60.0

# Closed CareerPilot MVP vocabulary. Values are canonical labels.
_ALIAS_TO_CANONICAL: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "react": "React",
    "node.js": "Node.js",
    "node js": "Node.js",
    "node-js": "Node.js",
    "nodejs": "Node.js",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "rest": "REST",
    "rest api": "REST",
    "graphql": "GraphQL",
    "git": "Git",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "linux": "Linux",
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "go": "Go",
    "golang": "Go",
    "r": "R",
    ".net": ".NET",
    "dotnet": ".NET",
    "spring": "Spring",
    "spring boot": "Spring Boot",
}

# Job requirement canonical -> candidate canonicals that count as documented partials only.
_PARTIAL_CANDIDATE_FOR_JOB: dict[str, frozenset[str]] = {
    "SQL": frozenset({"PostgreSQL", "MySQL"}),
    "JavaScript": frozenset({"TypeScript"}),
    "Spring": frozenset({"Spring Boot"}),
}

_REQUIRED_SIGNALS = (
    "required",
    "requirements",
    "must have",
    "must-have",
    "minimum",
    "qualifications",
)
_PREFERRED_SIGNALS = (
    "preferred",
    "nice to have",
    "nice-to-have",
    "bonus",
    "plus",
)
_STRONG_REQUIRED_SIGNALS = (
    "required",
    "must have",
    "must-have",
    "minimum",
)

_DEGREE_ALIASES = {
    "b.s.": "bachelor",
    "b.s": "bachelor",
    "bachelor": "bachelor",
    "bachelors": "bachelor",
    "bachelor's": "bachelor",
    "undergraduate": "bachelor",
    "bachelor of science": "bachelor",
    "bachelor of arts": "bachelor",
    "b s": "bachelor",
    "m s": "master",
    "m.s.": "master",
    "m.s": "master",
    "master": "master",
    "masters": "master",
    "master's": "master",
    "mba": "master",
    "ph.d.": "phd",
    "phd": "phd",
    "doctorate": "phd",
    "a.a.": "associate",
    "a.a": "associate",
    "a a": "associate",
    "associate": "associate",
}
_FIELD_ALIASES = {
    "computer science": "computer science",
    "computing": "computer science",
    "software engineering": "software engineering",
    "information systems": "information systems",
}

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


class ScoringError(Exception):
    """Base scoring error with a safe public message."""


class JobNotFoundError(ScoringError):
    def __init__(self) -> None:
        super().__init__("Job not found.")


class CandidateRequiredError(ScoringError):
    def __init__(self) -> None:
        super().__init__("Build a candidate profile before calculating fit.")


class RequirementsUnavailableError(ScoringError):
    def __init__(self) -> None:
        super().__init__("Job requirements are not available for scoring.")


@dataclass
class GroundedRequirements:
    required: list[str]
    preferred: list[str]
    tech_stack: list[str]
    years_experience: int | None
    education_requirements: list[str]
    seniority: str | None
    source: str  # "intelligence" | "description"
    dropped: int = 0


@dataclass
class SkillMatchResult:
    matched: list[str]
    partial: list[str]
    missing: list[str]
    required_ratio: float | None
    preferred_ratio: float | None


@dataclass
class ScoreBreakdown:
    skill: float | None
    experience: float | None
    education: float | None
    location: float | None
    preference: float | None
    overall: float
    recommendation: str
    rationale: str
    matched: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def _skill_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def canonicalize_skill(label: str) -> str | None:
    key = _skill_key(label)
    return _ALIAS_TO_CANONICAL.get(key)


def _canonical_skill_key(label: str) -> str:
    return canonicalize_skill(label) or _skill_key(label)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    lowered = alias.lower()
    body = re.escape(lowered)
    # Period is allowed as trailing punctuation ("Python.") and is not a token character,
    # except aliases that themselves contain a dot (node.js, .NET).
    if lowered == "react":
        return re.compile(rf"(?<![a-z0-9+#]){body}(?![\s-]*native)(?![a-z0-9+#])", re.I)
    if lowered == "java":
        return re.compile(rf"(?<![a-z0-9+#]){body}(?!script)(?![a-z0-9+#])", re.I)
    if lowered == "go":
        return re.compile(
            rf"(?<![a-z0-9+#]){body}(?![\s-]+(?:to|for|ahead|back|home|live|viral)\b)"
            rf"(?![a-z0-9+#])",
            re.I,
        )
    if lowered == "spring":
        return re.compile(
            rf"(?<![a-z0-9+#]){body}(?!\s+(?:semester|season|break|term)\b)"
            rf"(?![a-z0-9+#])",
            re.I,
        )
    if lowered == "c":
        return re.compile(
            rf"(?<![a-z0-9+#-]){body}(?![\s-]*level\b)(?![a-z0-9+#-])",
            re.I,
        )
    if lowered == "r":
        return re.compile(
            rf"(?<![a-z0-9+#-]){body}(?![\s-]*rated\b)(?![a-z0-9+#-])",
            re.I,
        )
    return re.compile(rf"(?<![a-z0-9+#]){body}(?![a-z0-9+#])", re.I)


def _skill_in_text(label: str, text: str) -> bool:
    canonical = canonicalize_skill(label) or label
    aliases = [alias for alias, canon in _ALIAS_TO_CANONICAL.items() if canon == canonical]
    if _skill_key(label) not in _ALIAS_TO_CANONICAL:
        aliases.append(_skill_key(label))
    aliases.sort(key=len, reverse=True)
    for alias in aliases:
        if _alias_pattern(alias).search(text):
            return True
    return False


def _ordered_unique(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        key = _canonical_skill_key(label)
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _looks_like_education_claim(value: str, source: str) -> bool:
    needle = value.strip()
    if not needle:
        return False
    if _skill_in_text(needle, source):
        return True
    pattern = rf"(?<![a-z0-9]){re.escape(needle.lower())}(?![a-z0-9])"
    return re.search(pattern, source.lower()) is not None


def _explicit_year_requirements(source: str) -> set[int]:
    """Return only explicit numeric work-experience requirements."""
    patterns = (
        r"(?<!\d)(\d{1,2})(?:\s*\+)?\s+(?:years?|yrs?)\s+of\s+"
        r"(?:(?:professional|relevant|work|industry)\s+)?experience\b",
        r"(?<!\d)(\d{1,2})(?:\s*\+)?\s+(?:years?|yrs?)\s+"
        r"(?:(?:professional|relevant|work|industry)\s+)?experience\b",
        r"\bexperience\s*(?::|of|for)?\s*(?:at\s+least\s+|minimum\s+)?"
        r"(\d{1,2})(?:\s*\+)?\s+(?:years?|yrs?)\b",
        r"\b(?:at\s+least|minimum(?:\s+of)?)\s+(\d{1,2})(?:\s*\+)?\s+"
        r"(?:years?|yrs?)\s+(?:(?:professional|relevant|work|industry)\s+)?experience\b",
    )
    found: set[int] = set()
    for pattern in patterns:
        found.update(int(match) for match in re.findall(pattern, source, flags=re.I))
    return {years for years in found if years > 0}


def _source_skill_classifications(source: str) -> dict[str, str]:
    extracted = extract_explicit_skills_from_description(source)
    classifications: dict[str, str] = {}
    for kind, labels in (
        ("required", extracted.required),
        ("preferred", extracted.preferred),
        ("stack", extracted.tech_stack),
    ):
        for label in labels:
            classifications[_canonical_skill_key(label)] = kind
    return classifications


def _source_skill_kind(
    label: str,
    source: str,
    known_classifications: dict[str, str],
) -> str | None:
    del known_classifications
    heading: str | None = None
    best: str | None = None
    priority = {"stack": 0, "preferred": 1, "required": 2}
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            heading = None
            continue
        section_kind = _source_section_heading_kind(stripped)
        if stripped.endswith(":") or re.match(
            r"^(?:requirements?|qualifications?|preferred|nice[- ]to[- ]have|bonus)\s*:",
            stripped,
            flags=re.I,
        ):
            heading = line
        elif section_kind == "technical":
            heading = line
        elif section_kind == "other":
            heading = None
        clauses = re.split(
            r"\s*(?:;|\|)\s*|(?<=[.!?])\s+",
            stripped,
        )
        for clause in clauses:
            if not _skill_in_text(label, clause):
                continue
            kind = _classify_line(clause, heading)
            if best is None or priority[kind] > priority[best]:
                best = kind
    return best


def _source_section_heading_kind(text: str) -> str | None:
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


def _ground_intelligence(
    intelligence: JobIntelligenceRecord,
    job: JobRecord,
) -> GroundedRequirements:
    source = f"{job.title}\n{job.description}"
    dropped = 0
    source_classifications = _source_skill_classifications(source)
    classified: dict[str, list[str]] = {
        "required": [],
        "preferred": [],
        "stack": [],
    }
    seen_skills: set[str] = set()
    for items in (
        intelligence.required_skills,
        intelligence.preferred_skills,
        intelligence.tech_stack,
    ):
        for raw in items or []:
            if not isinstance(raw, str) or not raw.strip():
                dropped += 1
                continue
            label = raw.strip()
            key = _canonical_skill_key(label)
            kind = _source_skill_kind(label, source, source_classifications)
            if kind is None or key in seen_skills:
                dropped += 1
                continue
            seen_skills.add(key)
            classified[kind].append(label)

    def _keep_education(items: list | None) -> list[str]:
        nonlocal dropped
        kept: list[str] = []
        for raw in items or []:
            if not isinstance(raw, str) or not raw.strip():
                dropped += 1
                continue
            if _looks_like_education_claim(raw, source):
                kept.append(raw.strip())
            else:
                dropped += 1
        return kept

    required = _ordered_unique(classified["required"])
    preferred = _ordered_unique(classified["preferred"])
    tech = _ordered_unique(classified["stack"])
    education = _keep_education(intelligence.education_requirements)
    years = intelligence.years_experience if isinstance(intelligence.years_experience, int) else None
    explicit_years = _explicit_year_requirements(source)
    if years is not None and (years <= 0 or years not in explicit_years):
        years = None
        dropped += 1
    seniority = intelligence.seniority
    if seniority and not re.search(
        rf"(?<![a-z0-9]){re.escape(seniority)}(?![a-z0-9])",
        source,
        flags=re.I,
    ):
        seniority = None
        dropped += 1
    return GroundedRequirements(
        required=required,
        preferred=preferred,
        tech_stack=tech,
        years_experience=years,
        education_requirements=education,
        seniority=seniority,
        source="intelligence",
        dropped=dropped,
    )


def _has_signal(text: str, signals: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(signal)}(?![a-z0-9])", lowered) for signal in signals)


def _classify_line(line: str, heading: str | None) -> str:
    line_preferred = _has_signal(line, _PREFERRED_SIGNALS)
    if line_preferred and not _has_signal(line, _STRONG_REQUIRED_SIGNALS):
        return "preferred"
    if _has_signal(line, _REQUIRED_SIGNALS):
        return "required"
    if line_preferred:
        return "preferred"
    if heading:
        heading_preferred = _has_signal(heading, _PREFERRED_SIGNALS)
        if heading_preferred and not _has_signal(heading, _STRONG_REQUIRED_SIGNALS):
            return "preferred"
        if _has_signal(heading, _REQUIRED_SIGNALS):
            return "required"
        if heading_preferred:
            return "preferred"
    return "stack"


def _clause_at_position(line: str, position: int) -> str:
    start = 0
    for separator in re.finditer(
        r"\s*(?:;|\|)\s*|(?<=[.!?])\s+",
        line,
    ):
        if position < separator.start():
            return line[start : separator.start()]
        start = separator.end()
    return line[start:]


def extract_explicit_skills_from_description(description: str) -> GroundedRequirements:
    """Closed-vocabulary explicit mentions only. Stable source order, alias-deduped."""
    aliases = sorted(_ALIAS_TO_CANONICAL.items(), key=lambda item: len(item[0]), reverse=True)
    lines = description.splitlines() or [description]
    found: dict[str, tuple[int, int, str, str]] = {}
    occupied = [[False] * len(line) for line in lines]
    heading: str | None = None
    kind_priority = {"stack": 0, "preferred": 1, "required": 2}
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            heading = None
            continue
        section_kind = _source_section_heading_kind(stripped)
        if stripped.endswith(":") or re.match(
            r"^(?:requirements?|qualifications?|preferred|nice[- ]to[- ]have|bonus)\s*:",
            stripped,
            flags=re.I,
        ):
            heading = line
        elif section_kind == "technical":
            heading = line
        elif section_kind == "other":
            heading = None
        lowered = line.lower()
        for alias, canonical in aliases:
            for match in _alias_pattern(alias).finditer(lowered):
                start, end = match.span()
                if any(occupied[line_idx][pos] for pos in range(start, end)):
                    continue
                for pos in range(start, end):
                    occupied[line_idx][pos] = True
                kind = _classify_line(
                    _clause_at_position(line, match.start()),
                    heading,
                )
                if canonical not in found:
                    found[canonical] = (line_idx, match.start(), canonical, kind)
                elif kind_priority[kind] > kind_priority[found[canonical][3]]:
                    first_line, first_pos, _, _ = found[canonical]
                    found[canonical] = (first_line, first_pos, canonical, kind)
    ordered = sorted(found.values(), key=lambda row: (row[0], row[1]))
    required: list[str] = []
    preferred: list[str] = []
    stack: list[str] = []
    for _, _, canonical, kind in ordered:
        if kind == "required":
            required.append(canonical)
        elif kind == "preferred":
            preferred.append(canonical)
        else:
            stack.append(canonical)
    return GroundedRequirements(
        required=required,
        preferred=preferred,
        tech_stack=stack,
        years_experience=None,
        education_requirements=[],
        seniority=None,
        source="description",
        dropped=0,
    )


def _candidate_skill_evidence(candidate: Candidate) -> set[str]:
    labels: list[str] = []
    for skill in candidate.skills or []:
        if isinstance(skill, str):
            labels.append(skill)
    for project in candidate.projects or []:
        if not isinstance(project, dict):
            continue
        for tech in project.get("technologies") or []:
            if isinstance(tech, str):
                labels.append(tech)
        description = project.get("description")
        if isinstance(description, str):
            labels.extend(extract_explicit_skills_from_description(description).tech_stack)
            labels.extend(extract_explicit_skills_from_description(description).required)
            labels.extend(extract_explicit_skills_from_description(description).preferred)
    for item in candidate.experience or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if isinstance(title, str):
            labels.extend(extract_explicit_skills_from_description(title).tech_stack)
        for highlight in item.get("highlights") or []:
            if isinstance(highlight, str):
                extracted = extract_explicit_skills_from_description(highlight)
                labels.extend(extracted.required + extracted.preferred + extracted.tech_stack)
    for cert in candidate.certifications or []:
        if isinstance(cert, str):
            labels.append(cert)
            labels.extend(extract_explicit_skills_from_description(cert).tech_stack)
    evidence: set[str] = set()
    for label in labels:
        evidence.add(_canonical_skill_key(label))
    return evidence


def _match_skills(requirements: GroundedRequirements, evidence: set[str]) -> SkillMatchResult:
    def _bucket(job_labels: list[str]) -> tuple[list[str], list[str], list[str], float | None]:
        if not job_labels:
            return [], [], [], None
        matched: list[str] = []
        partial: list[str] = []
        missing: list[str] = []
        scores: list[float] = []
        for label in job_labels:
            canonical = _canonical_skill_key(label)
            if canonical in evidence:
                matched.append(label)
                scores.append(FULL_MATCH)
                continue
            related = _PARTIAL_CANDIDATE_FOR_JOB.get(canonical, frozenset())
            if evidence & related:
                partial.append(label)
                scores.append(PARTIAL_MATCH)
            else:
                missing.append(label)
                scores.append(MISSING_MATCH)
        ratio = sum(scores) / len(scores)
        return matched, partial, missing, ratio

    req_m, req_p, req_miss, req_ratio = _bucket(requirements.required)
    pref_labels = _ordered_unique([*requirements.preferred, *requirements.tech_stack])
    # Keep preferred/stack labels that are not already required canonicals.
    required_canon = {_canonical_skill_key(item) for item in requirements.required}
    pref_labels = [
        item for item in pref_labels if _canonical_skill_key(item) not in required_canon
    ]
    pref_m, pref_p, pref_miss, pref_ratio = _bucket(pref_labels)

    matched = _ordered_unique([*req_m, *pref_m])
    partial = _ordered_unique([item for item in [*req_p, *pref_p] if item not in matched])
    missing = _ordered_unique([item for item in [*req_miss, *pref_miss] if item not in matched and item not in partial])
    return SkillMatchResult(
        matched=matched,
        partial=partial,
        missing=missing,
        required_ratio=req_ratio,
        preferred_ratio=pref_ratio,
    )


def _skill_component(match: SkillMatchResult) -> float | None:
    parts: list[tuple[float, float]] = []
    if match.required_ratio is not None:
        parts.append((SKILL_REQUIRED_SHARE, match.required_ratio))
    if match.preferred_ratio is not None:
        parts.append((SKILL_PREFERRED_SHARE, match.preferred_ratio))
    if not parts:
        return None
    weight_sum = sum(weight for weight, _ in parts)
    return 100.0 * sum(weight * value for weight, value in parts) / weight_sum


def _parse_month_year(value: str) -> date | None:
    text = value.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", text)
    if iso:
        year, month = int(iso.group(1)), int(iso.group(2))
        day = int(iso.group(3) or "1")
        try:
            return date(year, month, day)
        except ValueError:
            return None
    month_match = re.fullmatch(
        r"(january|february|march|april|may|june|july|august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?\s+(\d{4})",
        text,
        flags=re.I,
    )
    if month_match:
        month = _MONTHS[month_match.group(1).lower().rstrip(".")]
        return date(int(month_match.group(2)), month, 1)
    return None


def _is_present(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"present", "current", "now"}


def _employment_intervals(candidate: Candidate, as_of: date) -> list[tuple[date, date]]:
    intervals: list[tuple[date, date]] = []
    for item in candidate.experience or []:
        if not isinstance(item, dict):
            continue
        start_raw = item.get("start_date")
        end_raw = item.get("end_date")
        if not isinstance(start_raw, str) or not start_raw.strip():
            continue
        start = _parse_month_year(start_raw)
        if start is None:
            continue
        if _is_present(end_raw if isinstance(end_raw, str) else None):
            end = as_of
        elif isinstance(end_raw, str) and end_raw.strip():
            parsed_end = _parse_month_year(end_raw)
            if parsed_end is None:
                continue
            end = min(parsed_end, as_of)
        else:
            continue
        if start > as_of or end < start:
            continue
        intervals.append((start, end))
    if not intervals:
        return []
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _experience_years(candidate: Candidate, as_of: date) -> float | None:
    intervals = _employment_intervals(candidate, as_of)
    if not intervals:
        return None
    days = sum((end - start).days for start, end in intervals)
    return days / 365.25


def _experience_score(requirements: GroundedRequirements, candidate: Candidate, as_of: date) -> float | None:
    required = requirements.years_experience
    if required is None or required <= 0:
        return None
    years = _experience_years(candidate, as_of)
    if years is None:
        return None
    return max(0.0, min(100.0, 100.0 * min(1.0, years / required)))


def _normalize_degree(value: str) -> str:
    lowered = value.lower().strip()
    compact = re.sub(r"[^a-z]", "", lowered)
    spaced = re.sub(r"[^a-z]+", " ", lowered).strip()
    for key in (lowered, compact, spaced):
        if key in _DEGREE_ALIASES:
            return _DEGREE_ALIASES[key]
    return spaced


def _normalize_field(value: str) -> str:
    key = re.sub(r"[^a-z]+", " ", value.lower()).strip()
    return _FIELD_ALIASES.get(key, key)


def _closed_alias_in_text(
    value: str,
    aliases: dict[str, str],
) -> str | None:
    lowered = value.lower()
    for alias, canonical in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
            lowered,
        ):
            return canonical
    return None


def _education_score(requirements: GroundedRequirements, candidate: Candidate) -> float | None:
    needed = [item for item in requirements.education_requirements if item and item.strip()]
    if not needed:
        return None
    records = [item for item in (candidate.education or []) if isinstance(item, dict)]
    if not records:
        return 0.0
    hits = 0
    for requirement in needed:
        req_degree = _closed_alias_in_text(requirement, _DEGREE_ALIASES)
        req_field = _closed_alias_in_text(requirement, _FIELD_ALIASES)
        matched = False
        for edu in records:
            degree = _normalize_degree(str(edu.get("degree") or ""))
            field = _normalize_field(str(edu.get("field") or ""))
            if req_degree and degree != req_degree:
                continue
            if req_field and field != req_field:
                continue
            if not req_degree and not req_field:
                candidate_claim = f"{edu.get('degree') or ''} {edu.get('field') or ''}"
                if not _looks_like_education_claim(requirement, candidate_claim):
                    continue
            matched = True
            break
        if matched:
            hits += 1
    return 100.0 * hits / len(needed)


def _explicit_work_modes(value: str | None) -> set[str]:
    if not value:
        return set()
    modes: set[str] = set()
    if re.search(r"\bremote\b", value, flags=re.I):
        modes.add("remote")
    if re.search(r"\bhybrid\b", value, flags=re.I):
        modes.add("hybrid")
    if re.search(r"\b(?:on[\s-]?site|in[\s-]?office)\b", value, flags=re.I):
        modes.add("onsite")
    return modes


def _candidate_work_modes(preferences: TargetPreference) -> set[str]:
    value = (preferences.remote_preference or "").strip().lower().replace("-", "_")
    mapping = {
        "remote": {"remote"},
        "hybrid": {"hybrid"},
        "onsite": {"onsite"},
        "on_site": {"onsite"},
        "hybrid_or_remote": {"hybrid", "remote"},
    }
    modes = set(mapping.get(value, set()))
    for location in preferences.preferred_locations or []:
        if isinstance(location, str):
            modes.update(_explicit_work_modes(location))
    return modes


def _city_state(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    match = re.match(
        r"^\s*([a-z][a-z .'-]*?),\s*([a-z]{2})(?=\s*(?:$|[(/-]))",
        value,
        flags=re.I,
    )
    if not match:
        return None
    city = re.sub(r"[^a-z]+", " ", match.group(1).lower()).strip()
    state = match.group(2).lower()
    if not city:
        return None
    return city, state


def _location_score(job: JobRecord, preferences: TargetPreference | None) -> float | None:
    if preferences is None:
        return None
    parts: list[float] = []
    job_modes = _explicit_work_modes(job.location)
    candidate_modes = _candidate_work_modes(preferences)
    if job_modes and candidate_modes:
        parts.append(100.0 if job_modes & candidate_modes else 0.0)

    job_place = _city_state(job.location)
    preferred_places = [
        parsed
        for item in (preferences.preferred_locations or [])
        if isinstance(item, str)
        for parsed in [_city_state(item)]
        if parsed is not None
    ]
    if job_place is not None and preferred_places:
        parts.append(100.0 if job_place in preferred_places else 0.0)

    if not parts:
        return None
    return sum(parts) / len(parts)


def _parse_annual_salary(text: str | None) -> int | None:
    if not text:
        return None
    lowered = text.lower()
    if re.search(
        r"\b(?:estimated|estimate|approx(?:imately)?|negotiable|bonus|commission|"
        r"equity|ote|total compensation)\b",
        lowered,
    ):
        return None
    if re.search(
        r"(?:/|\bper\s+)(?:hour|hr|day|daily|week|wk|month|mo)\b|"
        r"\b(?:hourly|daily|weekly|monthly)\b",
        lowered,
    ):
        return None
    if not re.search(r"(?:/|\bper\s+)(?:year|yr)\b|\b(?:annual|annually|per annum)\b", lowered):
        return None
    if re.search(r"[€£¥]|\b(?:cad|eur|gbp|aud|jpy)\b", lowered):
        return None
    if "$" not in text and not re.search(r"\busd\b", lowered):
        return None
    compact = text.replace(",", "")
    amounts: list[int] = []
    for match in re.finditer(
        r"(?:\busd\s*|\$\s*)?(\d{2,7})(?:\.\d+)?\s*(k)?\b",
        compact,
        flags=re.I,
    ):
        amount = int(match.group(1))
        if match.group(2):
            amount *= 1000
        if 10_000 <= amount <= 1_000_000:
            amounts.append(amount)
    return max(amounts) if amounts else None


def _role_matches(job_title: str, roles: list[str]) -> bool | None:
    usable = [role.strip() for role in roles if isinstance(role, str) and role.strip()]
    if not usable:
        return None
    title = job_title.lower()
    for role in usable:
        if re.search(rf"(?<![a-z0-9]){re.escape(role.lower())}(?![a-z0-9])", title):
            return True
    return False


def _preference_score(job: JobRecord, preferences: TargetPreference | None) -> float | None:
    if preferences is None:
        return None
    parts: list[float] = []
    role_hit = _role_matches(job.title, list(preferences.target_roles or []))
    if role_hit is True:
        parts.append(100.0)
    elif role_hit is False:
        parts.append(40.0)
    salary_floor = preferences.salary_min
    job_salary = _parse_annual_salary(job.salary)
    if isinstance(salary_floor, int) and salary_floor >= 10_000 and job_salary is not None:
        parts.append(100.0 if job_salary >= salary_floor else 30.0)
    if not parts:
        return None
    return sum(parts) / len(parts)


def _combine(components: dict[str, float | None]) -> float:
    weighted = [
        (WEIGHT_SKILLS, components["skill"]),
        (WEIGHT_EXPERIENCE, components["experience"]),
        (WEIGHT_EDUCATION, components["education"]),
        (WEIGHT_LOCATION, components["location"]),
        (WEIGHT_PREFERENCES, components["preference"]),
    ]
    available = [(weight, value) for weight, value in weighted if value is not None]
    if not available:
        return 0.0
    total_weight = sum(weight for weight, _ in available)
    overall = sum(weight * value for weight, value in available) / total_weight
    return max(0.0, min(100.0, round(overall, 1)))


def _recommend(overall: float, source: str, has_explicit: bool) -> str:
    if source == "description":
        if overall >= CONSIDER_THRESHOLD:
            return "consider"
        return "skip" if has_explicit else "skip"
    if overall >= APPLY_THRESHOLD:
        return "apply"
    if overall >= CONSIDER_THRESHOLD:
        return "consider"
    return "skip"


def _rationale(
    source: str,
    components: dict[str, float | None],
    match: SkillMatchResult,
    recommendation: str,
) -> str:
    available = [name for name, value in components.items() if value is not None]
    unavailable = [name for name, value in components.items() if value is None]
    mode = "full Job Intelligence" if source == "intelligence" else "provisional explicit-description"
    reason = "required-skill coverage" if match.required_ratio is not None else "available grounded components"
    text = (
        f"{mode} scoring. "
        f"Available components: {', '.join(available) or 'none'}. "
        f"Unavailable components omitted (not zeroed): {', '.join(unavailable) or 'none'}. "
        f"Skills matched={len(match.matched)} partial={len(match.partial)} missing={len(match.missing)}. "
        f"Major driver: {reason}. "
        f"Recommendation {recommendation}"
        f"{' because overall is below 60' if recommendation == 'skip' else ''}"
        f"{' because overall is at least 80' if recommendation == 'apply' else ''}"
        f"{' because overall is at least 60' if recommendation == 'consider' else ''}."
    )
    if source == "description":
        text += " Full Job Intelligence could change this result. Apply is never returned for provisional scores."
    return text


def load_job(db: Session, public_id: str) -> JobRecord:
    record = db.query(JobRecord).filter(JobRecord.public_id == public_id).first()
    if record is None:
        raise JobNotFoundError()
    return record


def load_latest_candidate(db: Session, user_id: int) -> Candidate:
    record = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    if record is None:
        raise CandidateRequiredError()
    return record


def load_preferences(db: Session, candidate: Candidate) -> TargetPreference | None:
    """Scoped to this user's own preferences — no fallback to an
    unattributed row. That fallback used to exist for a single-tenant app
    where "no linked preferences" and "no preferences at all" were
    indistinguishable; with real accounts, falling back to *any* unowned
    preferences row would leak one user's answers into another user's
    scoring.

    Filters on TargetPreference.user_id, not candidate_id: a user can save
    preferences before ever uploading a resume (no Candidate row yet), so
    candidate_id is null on that row even though user_id is always set —
    filtering on candidate_id alone would silently orphan those answers
    forever once the Candidate is created later, since nothing backfills
    candidate_id onto the earlier row.
    """
    return (
        db.query(TargetPreference)
        .filter(TargetPreference.user_id == candidate.user_id)
        .order_by(TargetPreference.id.desc())
        .first()
    )


def load_requirements(db: Session, job: JobRecord) -> GroundedRequirements:
    intelligence = (
        db.query(JobIntelligenceRecord).filter(JobIntelligenceRecord.job_id == job.id).first()
    )
    if intelligence is not None:
        grounded = _ground_intelligence(intelligence, job)
        logger.info(
            "scoring requirement_source=intelligence dropped=%s job_pk=%s",
            grounded.dropped,
            job.id,
        )
        if (
            grounded.required
            or grounded.preferred
            or grounded.tech_stack
            or grounded.years_experience is not None
            or grounded.education_requirements
        ):
            return grounded
        # Intelligence existed but nothing scoreable; do not invent from the posting.
        raise RequirementsUnavailableError()
    fallback = extract_explicit_skills_from_description(f"{job.title}\n{job.description}")
    logger.info(
        "scoring requirement_source=description skills=%s job_pk=%s",
        len(fallback.required) + len(fallback.preferred) + len(fallback.tech_stack),
        job.id,
    )
    if not (fallback.required or fallback.preferred or fallback.tech_stack):
        raise RequirementsUnavailableError()
    return fallback


def compute_breakdown(
    job: JobRecord,
    candidate: Candidate,
    preferences: TargetPreference | None,
    requirements: GroundedRequirements,
    *,
    as_of: date | None = None,
) -> ScoreBreakdown:
    when = as_of or date.today()
    evidence = _candidate_skill_evidence(candidate)
    skill_match = _match_skills(requirements, evidence)
    components = {
        "skill": _skill_component(skill_match),
        "experience": _experience_score(requirements, candidate, when),
        "education": _education_score(requirements, candidate),
        "location": _location_score(job, preferences),
        "preference": _preference_score(job, preferences),
    }
    overall = _combine(components)
    has_explicit = bool(requirements.required or requirements.preferred or requirements.tech_stack)
    recommendation = _recommend(overall, requirements.source, has_explicit)
    return ScoreBreakdown(
        skill=None if components["skill"] is None else round(components["skill"], 1),
        experience=None if components["experience"] is None else round(components["experience"], 1),
        education=None if components["education"] is None else round(components["education"], 1),
        location=None if components["location"] is None else round(components["location"], 1),
        preference=None if components["preference"] is None else round(components["preference"], 1),
        overall=overall,
        recommendation=recommendation,
        rationale=_rationale(requirements.source, components, skill_match, recommendation),
        matched=skill_match.matched,
        partial=skill_match.partial,
        missing=skill_match.missing,
    )


def persist_score(
    db: Session,
    job: JobRecord,
    candidate: Candidate,
    breakdown: ScoreBreakdown,
) -> MatchScore:
    existing_rows = (
        db.query(MatchScoreRecord)
        .filter(MatchScoreRecord.job_id == job.id, MatchScoreRecord.candidate_id == candidate.id)
        .order_by(MatchScoreRecord.id.desc())
        .all()
    )
    existing = existing_rows[0] if existing_rows else None
    payload = {
        "job_id": job.id,
        "candidate_id": candidate.id,
        "overall_score": breakdown.overall,
        "skill_score": breakdown.skill,
        "experience_score": breakdown.experience,
        "education_score": breakdown.education,
        "location_score": breakdown.location,
        "preference_score": breakdown.preference,
        "matched_skills": list(breakdown.matched),
        "partial_matches": list(breakdown.partial),
        "missing_skills": list(breakdown.missing),
        "recommendation": breakdown.recommendation,
        "rationale": breakdown.rationale,
    }
    try:
        if existing is not None:
            for key, value in payload.items():
                setattr(existing, key, value)
            for duplicate in existing_rows[1:]:
                db.delete(duplicate)
            record = existing
        else:
            record = MatchScoreRecord(**payload)
            db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        logger.error(
            "scoring persist failed job_pk=%s candidate_pk=%s category=%s",
            job.id,
            candidate.id,
            "database",
        )
        raise
    logger.info(
        "scoring persisted job_pk=%s candidate_pk=%s rows=%s",
        job.id,
        candidate.id,
        1,
    )
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


def score_job(db: Session, job_public_id: str, user_id: int, *, as_of: date | None = None) -> MatchScore:
    """Request-scoped scoring entrypoint. Never opens SessionLocal."""
    job = load_job(db, job_public_id)
    candidate = load_latest_candidate(db, user_id)
    preferences = load_preferences(db, candidate)
    requirements = load_requirements(db, job)
    breakdown = compute_breakdown(job, candidate, preferences, requirements, as_of=as_of)
    return persist_score(db, job, candidate, breakdown)

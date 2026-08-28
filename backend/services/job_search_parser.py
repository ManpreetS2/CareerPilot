"""Deterministic JobSearchIntent parser. Never emits SQL, ORM, or URLs."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

OpportunityKind = Literal["internship", "role", "unknown"]
DatePostedWindow = Literal["past_24h", "past_3d", "past_7d", "past_14d", "past_30d"]
VerifiedState = Literal["all", "verified", "potential"]
EligibilityState = Literal["all", "likely_eligible", "eligibility_uncertain", "likely_ineligible"]
ConfidenceState = Literal["all", "high", "medium", "low"]
SortMode = Literal["best_match", "newest", "qualification", "preference"]
JobsTab = Literal["discover", "matches", "saved"]


class JobSearchIntent(BaseModel):
    """Allowlisted Jobs filters. Unknown stays unknown."""

    raw_query: str | None = None
    query: str | None = None
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    opportunity_types: list[OpportunityKind] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    experience_levels: list[str] = Field(default_factory=list)
    work_modes: list[str] = Field(default_factory=list)
    remote_scopes: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    date_posted: DatePostedWindow | None = None
    verified_state: VerifiedState = "all"
    eligibility_state: EligibilityState = "all"
    confidence_state: ConfidenceState = "all"
    parser_ready: bool = True
    parser_source: Literal["deterministic", "gemini", "empty"] = "deterministic"


_LOCATION_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:sf\s+)?bay\s+area\b|\bsan\s+francisco\s+bay\b|\bsilicon\s+valley\b", re.I), "San Francisco Bay Area"),
    (re.compile(r"\bsan\s+francisco\b", re.I), "San Francisco"),
    (re.compile(r"\bnew\s+york(?:\s+city)?\b|\bnyc\b|\bmanhattan\b", re.I), "New York"),
    (re.compile(r"\blos\s+angeles\b", re.I), "Los Angeles"),
    (re.compile(r"\bseattle\b", re.I), "Seattle"),
    (re.compile(r"\baustin\b", re.I), "Austin"),
    (re.compile(r"\bboston\b", re.I), "Boston"),
    (re.compile(r"\bchicago\b", re.I), "Chicago"),
    (re.compile(r"\bdenver\b", re.I), "Denver"),
    (re.compile(r"\batlanta\b", re.I), "Atlanta"),
    (re.compile(r"\bremote\s+us\b|\bunited\s+states\b", re.I), "United States"),
)

_INDUSTRY_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfintech\b|\bfinancial\s+tech", re.I), "fintech"),
    (re.compile(r"\bhealth(?:care)?\s*tech\b|\bhealthtech\b", re.I), "healthtech"),
    (re.compile(r"\bclimate\s*tech\b|\bclimatetech\b", re.I), "climatetech"),
    (re.compile(r"\bedtech\b|\beducation\s+tech", re.I), "edtech"),
    (re.compile(r"\bsaas\b", re.I), "saas"),
)

_ROLE_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsoftware\s+engineers?\b|\bsoftware\s+engineering\b|\bswe\b", re.I), "Software Engineering"),
    (re.compile(r"\bbackend\b", re.I), "Backend"),
    (re.compile(r"\bfrontend\b|\bfront-end\b", re.I), "Frontend"),
    (re.compile(r"\bfull[\s-]?stack\b", re.I), "Full-Stack"),
    (re.compile(r"\bdata\s+scientist\b|\bdata\s+science\b", re.I), "Data Science"),
    (re.compile(r"\bdata\s+analyst\b|\bdata\s+analytics\b", re.I), "Data Analyst"),
    (re.compile(r"\bmachine\s+learning\b|\bml\s+engineer\b", re.I), "Machine Learning"),
    (re.compile(r"\bproduct\s+manager\b", re.I), "Product Manager"),
    (re.compile(r"\bux\s+design", re.I), "UX Design"),
    (re.compile(r"\bsecurity\s+engineer\b", re.I), "Security Engineering"),
)

_EXPERIENCE = (
    ("principal", "principal"),
    ("staff", "staff"),
    ("director", "director"),
    ("manager", "manager"),
    ("senior", "senior"),
    ("lead", "lead"),
    ("junior", "junior"),
    ("entry-level", "entry"),
    ("entry level", "entry"),
    ("intern", "intern"),
    ("new grad", "new_grad"),
    ("new-grad", "new_grad"),
)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def parse_job_search_intent(raw: str | None) -> JobSearchIntent:
    text = (raw or "").strip()
    if not text:
        return JobSearchIntent(raw_query=None, parser_ready=True, parser_source="empty")

    lowered = text.lower()
    consumed: list[tuple[int, int]] = []

    def _mark(match: re.Match[str]) -> None:
        consumed.append((match.start(), match.end()))

    work_modes: list[str] = []
    if match := re.search(r"\bhybrid\b", lowered):
        work_modes.append("hybrid")
        _mark(match)
    if match := re.search(r"\bon-?site\b|\bin[\s-]?office\b", lowered):
        work_modes.append("onsite")
        _mark(match)
    if match := re.search(r"\bremote\b", lowered):
        work_modes.append("remote")
        _mark(match)

    employment_types: list[str] = []
    opportunity_types: list[OpportunityKind] = []
    if match := re.search(r"\bintern(?:s|ships?)?\b", lowered):
        employment_types.append("internship")
        opportunity_types.append("internship")
        _mark(match)
    if match := re.search(r"\bco-?ops?\b", lowered):
        employment_types.append("co_op")
        opportunity_types.append("internship")
        _mark(match)
    if match := re.search(r"\bnew[\s-]?grads?(?:uate)?s?\b", lowered):
        employment_types.append("new_grad")
        opportunity_types.append("internship")
        _mark(match)
    if match := re.search(r"\bfull[\s-]?time\b", lowered):
        employment_types.append("full_time")
        if "internship" not in opportunity_types:
            opportunity_types.append("role")
        _mark(match)
    if match := re.search(r"\bpart[\s-]?time\b", lowered):
        employment_types.append("part_time")
        _mark(match)
    if match := re.search(r"\bcontract\b", lowered):
        employment_types.append("contract")
        _mark(match)

    remote_scopes: list[str] = []
    if match := re.search(r"\bremote\s+(?:us|u\.s\.|united\s+states)\b", lowered):
        remote_scopes.append("United States only")
        _mark(match)

    locations: list[str] = []
    for pattern, label in _LOCATION_ALIASES:
        match = pattern.search(text)
        if match:
            locations.append(label)
            consumed.append((match.start(), match.end()))

    industries: list[str] = []
    for pattern, label in _INDUSTRY_ALIASES:
        match = pattern.search(text)
        if match:
            industries.append(label)
            consumed.append((match.start(), match.end()))

    roles: list[str] = []
    for pattern, label in _ROLE_ALIASES:
        match = pattern.search(text)
        if match:
            roles.append(label)
            consumed.append((match.start(), match.end()))

    experience_levels: list[str] = []
    for needle, label in _EXPERIENCE:
        if needle == "intern" and "internship" in employment_types:
            continue
        pattern = re.compile(rf"\b{re.escape(needle)}\b", re.I)
        match = pattern.search(lowered)
        if match:
            experience_levels.append(label)
            consumed.append((match.start(), match.end()))

    leftover = list(text)
    for start, end in sorted(consumed, reverse=True):
        leftover[start:end] = [" "] * (end - start)
    leftover_text = re.sub(
        r"\b(?:in|at|the|and|or|for|with|companies?|roles?|jobs?|looking|want(?:ed)?)\b",
        " ",
        "".join(leftover),
        flags=re.I,
    )
    leftover_text = re.sub(r"[^\w+#.+]+", " ", leftover_text).strip()
    leftover_text = re.sub(r"\s+", " ", leftover_text)

    intent = JobSearchIntent(
        raw_query=text,
        query=leftover_text or None,
        roles=_dedupe(roles),
        locations=_dedupe(locations),
        opportunity_types=_dedupe(opportunity_types),  # type: ignore[arg-type]
        employment_types=_dedupe(employment_types),
        experience_levels=_dedupe(experience_levels),
        work_modes=_dedupe(work_modes),
        remote_scopes=_dedupe(remote_scopes),
        industries=_dedupe(industries),
        parser_ready=True,
        parser_source="deterministic",
    )
    return intent


def scout_terms_from_intent(intent: JobSearchIntent) -> tuple[list[str], str | None]:
    """Allowlisted outbound scout query strings. Never URLs."""
    queries = [item for item in intent.roles if item]
    if intent.opportunity_types == ["internship"] and queries:
        queries = [f"{item} intern" if "intern" not in item.lower() else item for item in queries]
    if not queries and intent.query:
        queries = [intent.query]
    if not queries and intent.raw_query:
        queries = [intent.raw_query[:120]]
    location = intent.locations[0] if intent.locations else None
    return queries[:3], location

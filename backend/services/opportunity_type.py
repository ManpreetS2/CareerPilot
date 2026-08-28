"""Canonical opportunity and work-setup labels for Jobs filters.

Do not reimplement title.includes('intern') in React. Ambiguous listings stay
unknown and appear when the opportunity filter is Both.

Internship opportunity: internship and co-op.
Role opportunity: new-grad, full-time, part-time, contract, temporary, fellowship.
"""

from __future__ import annotations

import re

EmploymentType = str
OpportunityType = str
WorkMode = str

INTERNSHIP_EMPLOYMENT = frozenset({"internship", "co_op"})
ROLE_EMPLOYMENT = frozenset(
    {"new_grad", "full_time", "part_time", "contract", "temporary", "fellowship"}
)

_CO_OP = re.compile(r"\bco-?op\b", re.I)
_INTERN = re.compile(r"\bintern(?:s|ship)?\b", re.I)
_NEW_GRAD = re.compile(r"\bnew[\s-]?grad(?:uate)?s?\b", re.I)
_JOB_FULL_TIME = re.compile(
    r"(?i)(?:this is (?:a |an )?full[\s-]?time\b|employment type:\s*full[\s-]?time\b|"
    r"\bfull[\s-]?time (?:role|position|job)\b|"
    r"(?:^|[.!?]\s+)full[\s-]?time(?:[.!?]|$))"
)
_JOB_PART_TIME = re.compile(
    r"(?i)(?:this is (?:a |an )?part[\s-]?time\b|employment type:\s*part[\s-]?time\b|"
    r"\bpart[\s-]?time (?:role|position|job)\b|"
    r"(?:^|[.!?]\s+)part[\s-]?time(?:[.!?]|$))"
)
_JOB_CONTRACT = re.compile(
    r"(?i)(?:this is (?:a |an )?(?:\d+[\s-]?month )?contract (?:role|position|job)\b|"
    r"employment type:\s*contract\b|"
    r"\b\d+[\s-]?month contract(?: position)?\b|"
    r"\bcontract (?:role|position)\b)"
)
_JOB_FELLOW = re.compile(
    r"(?i)(?:this is (?:a |an )?fellow(?:ship)?\b|employment type:\s*fellow(?:ship)?\b|"
    r"\bfellowship (?:role|position|job)\b)"
)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_REMOTE = re.compile(r"\bremote\b", re.I)
_ONSITE = re.compile(r"\b(?:on-?site|in[\s-]?office)\b", re.I)
_JOB_HYBRID = re.compile(
    r"(?i)(?:this is (?:a |an )?hybrid\b|\bhybrid (?:role|position|job|work)\b|\bhybrid in\b|"
    r"(?:^|[.!?]\s+)hybrid(?:[.!?]|$))"
)
_JOB_ONSITE = re.compile(
    r"(?i)(?:this is (?:a |an )?(?:on-?site|in[\s-]?office)\b|"
    r"\b(?:on-?site|in[\s-]?office) (?:role|position|job)\b|"
    r"\bwork on-?site\b|"
    r"\bonsite (?:\d+|five) days)"
)
_JOB_REMOTE = re.compile(
    r"(?i)(?:this is (?:a |an )?(?:fully )?remote\b|"
    r"\b(?:fully )?remote (?:role|position|job|only|us|united)\b|"
    r"\bwork remotely\b|"
    r"\bremote -|"
    r"(?:^|[.!?]\s+)(?:fully )?remote(?:[.!?]|$))"
)


def infer_employment_type(title: str | None, description: str | None = None) -> EmploymentType:
    title_text = title or ""
    if _INTERN.search(title_text):
        return "internship"
    if _CO_OP.search(title_text):
        return "co_op"
    if _NEW_GRAD.search(title_text):
        return "new_grad"
    blob = (description or "")[:2500]
    found: list[EmploymentType] = []
    if _JOB_PART_TIME.search(blob):
        found.append("part_time")
    if _JOB_CONTRACT.search(blob):
        found.append("contract")
    if _JOB_FELLOW.search(blob):
        found.append("fellowship")
    if _JOB_FULL_TIME.search(blob):
        found.append("full_time")
    if len(found) == 1:
        return found[0]
    return "unknown"


def opportunity_type_for(employment_type: str | None) -> OpportunityType:
    """internship is internship/co-op. role is new-grad and other non-intern work."""
    value = (employment_type or "unknown").strip().lower()
    if value in INTERNSHIP_EMPLOYMENT:
        return "internship"
    if value in ROLE_EMPLOYMENT:
        return "role"
    return "unknown"


def infer_opportunity_type(title: str | None, description: str | None = None) -> OpportunityType:
    return opportunity_type_for(infer_employment_type(title, description))


def _modes_in(text: str) -> list[WorkMode]:
    found: list[WorkMode] = []
    if _HYBRID.search(text):
        found.append("hybrid")
    if _REMOTE.search(text):
        found.append("remote")
    if _ONSITE.search(text):
        found.append("onsite")
    return found


def _job_clause_modes(text: str) -> list[WorkMode]:
    found: list[WorkMode] = []
    if _JOB_HYBRID.search(text):
        found.append("hybrid")
    if _JOB_REMOTE.search(text):
        found.append("remote")
    if _JOB_ONSITE.search(text):
        found.append("onsite")
    return found


def infer_work_mode(
    title: str | None,
    description: str | None = None,
    location: str | None = None,
) -> WorkMode:
    header = f"{title or ''}\n{location or ''}"
    header_modes = _modes_in(header)
    if len(header_modes) == 1:
        return header_modes[0]
    blob = (description or "")[:2500]
    clause_modes = _job_clause_modes(blob)
    if len(clause_modes) == 1:
        return clause_modes[0]
    return "unknown"


def matches_opportunity_filter(opportunity: OpportunityType, wanted: str | None) -> bool:
    if not wanted or wanted in {"both", "all"}:
        return True
    if wanted == "internship":
        return opportunity == "internship"
    if wanted == "role":
        return opportunity == "role"
    return True

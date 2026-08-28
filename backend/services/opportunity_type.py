"""Canonical opportunity and work-setup labels for Jobs filters.

Do not reimplement title.includes('intern') in React. Ambiguous listings stay
unknown and appear when the opportunity filter is Both.
"""

from __future__ import annotations

import re

EmploymentType = str
OpportunityType = str
WorkMode = str

INTERNSHIP_EMPLOYMENT = frozenset({"internship", "co_op", "new_grad"})
ROLE_EMPLOYMENT = frozenset({"full_time", "part_time", "contract", "temporary", "fellowship"})

_CO_OP = re.compile(r"\bco-?op\b", re.I)
_INTERN = re.compile(r"\bintern(?:s|ship)?\b", re.I)
_NEW_GRAD = re.compile(r"\bnew[\s-]?grad(?:uate)?s?\b", re.I)
_FULL_TIME = re.compile(r"\bfull[\s-]?time\b", re.I)
_PART_TIME = re.compile(r"\bpart[\s-]?time\b", re.I)
_CONTRACT = re.compile(r"\bcontract(?:or|ing)?\b", re.I)
_FELLOW = re.compile(r"\bfellow(?:ship)?\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_REMOTE = re.compile(r"\bremote\b", re.I)
_ONSITE = re.compile(r"\b(?:on-?site|in[\s-]?office)\b", re.I)


def infer_employment_type(title: str | None, description: str | None = None) -> EmploymentType:
    title_text = title or ""
    if _INTERN.search(title_text):
        return "internship"
    if _CO_OP.search(title_text):
        return "co_op"
    if _NEW_GRAD.search(title_text):
        return "new_grad"
    blob = f"{title_text}\n{(description or '')[:2500]}"
    if _PART_TIME.search(blob):
        return "part_time"
    if _CONTRACT.search(blob):
        return "contract"
    if _FELLOW.search(blob):
        return "fellowship"
    if _FULL_TIME.search(blob):
        return "full_time"
    return "unknown"


def opportunity_type_for(employment_type: str | None) -> OpportunityType:
    """internship includes internship/co-op/new-grad. role is explicit non-intern work."""
    value = (employment_type or "unknown").strip().lower()
    if value in INTERNSHIP_EMPLOYMENT:
        return "internship"
    if value in ROLE_EMPLOYMENT:
        return "role"
    return "unknown"


def infer_opportunity_type(title: str | None, description: str | None = None) -> OpportunityType:
    return opportunity_type_for(infer_employment_type(title, description))


def infer_work_mode(title: str | None, description: str | None = None) -> WorkMode:
    blob = f"{title or ''}\n{(description or '')[:2500]}"
    if _HYBRID.search(blob):
        return "hybrid"
    if _REMOTE.search(blob):
        return "remote"
    if _ONSITE.search(blob):
        return "onsite"
    return "unknown"


def matches_opportunity_filter(opportunity: OpportunityType, wanted: str | None) -> bool:
    if not wanted or wanted in {"both", "all"}:
        return True
    if wanted == "internship":
        return opportunity == "internship"
    if wanted == "role":
        return opportunity == "role"
    return True

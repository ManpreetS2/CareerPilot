"""Canonical Jobs listing metadata from current profile, then conservative inference.

A stale JobRequirementProfile must not drive search/filter labels. GET surfaces
share this resolver so catalog, detail, and query do not disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy.orm import object_session

from backend.db.models import JobRecord, JobRequirementProfileRecord
from backend.services.job_requirement_extractor import is_current_requirement_profile
from backend.services.opportunity_type import (
    INTERNSHIP_EMPLOYMENT,
    ROLE_EMPLOYMENT,
    infer_employment_type,
    infer_work_mode,
    opportunity_type_for,
)

_VALID_WORK = frozenset({"remote", "hybrid", "onsite"})
_VALID_EMPLOYMENT = INTERNSHIP_EMPLOYMENT | ROLE_EMPLOYMENT
_VALID_EXPERIENCE = frozenset(
    {
        "intern",
        "new_grad",
        "entry",
        "junior",
        "mid",
        "senior",
        "staff",
        "principal",
        "lead",
        "manager",
        "director",
        "executive",
    }
)

_TITLE_INTERN = re.compile(r"\bintern(?:s|ship)?\b", re.I)
_TITLE_NEW_GRAD = re.compile(r"\bnew[\s-]?grad(?:uate)?s?\b", re.I)
_TITLE_JUNIOR = re.compile(
    r"\b(?:junior|jr\.?|entry[\s-]?level|(?:software\s+)?(?:engineer|developer)\s+(?:i|1))\b",
    re.I,
)
_OCCUPATION = (
    r"(?:software\s+)?(?:engineer|developer|scientist|architect|designer|"
    r"product(?:\s+manager)?|manager|analyst|researcher|consultant|specialist)"
)
_EXPERIENCE_TITLE = {
    "senior": re.compile(rf"\b(?:senior|sr\.?)\s+{_OCCUPATION}", re.I),
    "staff": re.compile(rf"\bstaff\s+{_OCCUPATION}", re.I),
    "lead": re.compile(rf"\blead\s+{_OCCUPATION}", re.I),
    "principal": re.compile(rf"\bprincipal\s+{_OCCUPATION}", re.I),
    "mid": re.compile(r"\b(?:mid[\s-]?level|mid[\s-]?career)\b", re.I),
    "manager": re.compile(r"\b(?:engineering\s+)?manager\b", re.I),
}


@dataclass(frozen=True)
class JobListingMetadata:
    employment_type: str
    opportunity_type: str
    experience_level: str
    work_mode: str
    location_text: str
    role_text: str


def requirement_profile_for_record(
    record: JobRecord,
    profile_row: JobRequirementProfileRecord | None = None,
) -> JobRequirementProfileRecord | None:
    if profile_row is not None:
        return profile_row
    if object_session(record) is None:
        return None
    return record.requirement_profile


def infer_experience_level(title: str | None, employment_type: str | None) -> str:
    text = title or ""
    emp = (employment_type or "").lower()
    if emp == "internship" or _TITLE_INTERN.search(text):
        return "intern"
    if emp == "new_grad" or _TITLE_NEW_GRAD.search(text):
        return "new_grad"
    if emp in {"entry", "junior"} or _TITLE_JUNIOR.search(text):
        return "junior"
    for level, pattern in _EXPERIENCE_TITLE.items():
        if pattern.search(text):
            return level
    return "unknown"


def _profile_dict(row: JobRequirementProfileRecord | None) -> dict:
    if row is None or not isinstance(row.profile_json, dict):
        return {}
    return row.profile_json


def resolve_job_listing_metadata(
    record: JobRecord,
    profile_row: JobRequirementProfileRecord | None = None,
) -> JobListingMetadata:
    row = requirement_profile_for_record(record, profile_row)
    profile = _profile_dict(row) if is_current_requirement_profile(record, row) else {}

    work_mode = profile.get("work_mode")
    if work_mode not in _VALID_WORK:
        work_mode = infer_work_mode(record.title, record.description, record.location)

    employment = profile.get("employment_type")
    if employment not in _VALID_EMPLOYMENT:
        employment = infer_employment_type(record.title, record.description)

    experience = profile.get("experience_level")
    if experience not in _VALID_EXPERIENCE:
        experience = infer_experience_level(record.title, employment)

    location_parts = [record.location or ""]
    remote_scope = profile.get("remote_scope")
    if remote_scope:
        location_parts.append(str(remote_scope))
    for loc in profile.get("locations") or []:
        if isinstance(loc, dict):
            location_parts.append(str(loc.get("label") or ""))
        elif isinstance(loc, str):
            location_parts.append(loc)

    role_parts = [
        record.title or "",
        str(profile.get("role_title") or ""),
        str(profile.get("role_family") or ""),
    ]
    return JobListingMetadata(
        employment_type=employment,
        opportunity_type=opportunity_type_for(employment),
        experience_level=experience,
        work_mode=work_mode,
        location_text=" ".join(location_parts).lower(),
        role_text=" ".join(role_parts).lower(),
    )

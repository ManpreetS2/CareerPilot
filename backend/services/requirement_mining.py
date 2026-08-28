"""Deterministic hard-requirement mining from a complete posting.

The LLM structures additional skills/responsibilities. These miners exist so
eligibility-critical clauses (especially AND/OR student rules) cannot be
missed when a model truncates the end of a posting.
"""

from __future__ import annotations

import re
import uuid

from backend.schemas.job_requirements import (
    JobLocation,
    JobRequirementProfile,
    Requirement,
    RequirementGroup,
)
from backend.services.fit_v2 import occupational_family, seniority_from_text
from backend.services.job_content import CanonicalJobContent

_FINAL_YEAR_OR_RECENT = re.compile(
    r"(?:candidates?|applicants?|you)\s+must\s+(?:either\s+)?be\s+in\s+(?:the\s+|their\s+)?"
    r"final\s+year.{0,120}(?:or|,).{0,40}graduated.{0,80}\d+\s+months?"
    r"|final\s+year\s+of\s+(?:their\s+|the\s+)?degree.{0,80}or.{0,40}graduated.{0,80}\d+\s+months?",
    re.I | re.S,
)
_FINAL_YEAR = re.compile(r"\b(?:final[- ]year|senior[- ]year|last\s+year\s+of\s+(?:their\s+)?(?:degree|program))\b", re.I)
_RECENT_GRAD_WINDOW = re.compile(
    r"graduated\s+(?:within|in)\s+(?:the\s+)?(?:previous|prior|past|last)\s+(\d+)\s+months?",
    re.I,
)
_ENROLLED = re.compile(
    r"\b(?:must\s+be\s+)?(?:currently\s+)?enrolled\b|\bmust\s+be\s+a\s+(?:current\s+)?student\b",
    re.I,
)
_NO_SPONSOR = re.compile(
    r"(?:will\s+not|cannot|does\s+not|unable\s+to)\s+(?:provide|offer|sponsor).{0,40}sponsor"
    r"|no\s+(?:employment\s+)?(?:visa\s+)?sponsorship"
    r"|not\s+(?:able|available)\s+to\s+sponsor",
    re.I,
)
_SPONSOR_OK = re.compile(r"sponsorship\s+(?:is\s+)?(?:available|offered)|will\s+sponsor", re.I)
_CPT = re.compile(r"\bcpt\b", re.I)
_OPT = re.compile(r"\bopt\b", re.I)
_US_AUTH = re.compile(
    r"must\s+be\s+(?:authorized|legally\s+authorized)\s+to\s+work\s+in\s+the\s+(?:u\.?s\.?|united\s+states)",
    re.I,
)
_HYBRID_DAYS = re.compile(
    r"hybrid[^\n.]{0,60}?(?:(\d)|one|two|three|four|five)\s+days?\s+(?:a|per)\s+week",
    re.I,
)
_HYBRID_DAY_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_REMOTE_US = re.compile(r"\bremote\b[^\n.]{0,40}\b(?:united\s+states|u\.s\.a?|us\s+only)\b", re.I)
_REMOTE_CA = re.compile(r"\bremote\b[^\n.]{0,40}\bcalifornia\b", re.I)
_TRAVEL_PCT = re.compile(r"(\d{1,2})\s*[–\-]\s*(\d{1,2})%\s+travel|(\d{1,2})%\s+travel", re.I)
_BACHELOR_OR_EQ = re.compile(
    r"bachelor'?s(?:\s+degree)?[^\n.]{0,40}or\s+(?:equivalent\s+)?experience",
    re.I,
)
_PYTHON = re.compile(r"\bpython\b", re.I)
_SQL = re.compile(r"\bsql\b", re.I)
_AWS = re.compile(r"\baws\b", re.I)
_GPA = re.compile(r"\bgpa\b[^\n.]{0,24}(\d(?:\.\d{1,2})?)", re.I)
_CLEARANCE = re.compile(r"\b(?:security\s+)?clearance\b", re.I)
_LICENSE = re.compile(r"\b(?:driver'?s?\s+license|professional\s+engineer(?:ing)?\s+license|\bpe\s+license)\b", re.I)
_UNPAID = re.compile(r"\bunpaid\s+internship\b", re.I)
_PAID = re.compile(r"\bpaid\s+internship\b", re.I)
_START_DATE = re.compile(r"\b(?:start(?:ing)?(?:\s+date)?|must\s+start)\b[^\n.]{0,80}", re.I)
_RELOC_REQUIRED = re.compile(r"\brelocation\s+(?:is\s+)?required\b|\bmust\s+relocate\b", re.I)
_RELOC_OFFERED = re.compile(r"\brelocation\s+(?:assistance|offered|package)\b", re.I)
_TIMEZONE = re.compile(
    r"(?:overlap|cover|available).{0,40}(?:pacific|pt).{0,40}(?:eastern|et)|pacific\s+through\s+eastern",
    re.I,
)
_CPT_OK = re.compile(r"\bcpt\s+(?:is\s+)?(?:accepted|allowed|ok|okay)\b|\baccepts?\s+cpt\b", re.I)
_OPT_OK = re.compile(r"\bopt\s+(?:is\s+)?(?:accepted|allowed|ok|okay)\b|\baccepts?\s+opt\b", re.I)
_PYTHON_AND_SQL = re.compile(r"\bpython\b.{0,40}\band\b.{0,20}\bsql\b", re.I)
_KNOWN_CITIES = (
    "San Francisco",
    "New York",
    "Austin",
    "Seattle",
    "Boston",
    "Chicago",
    "Los Angeles",
    "Denver",
    "Atlanta",
)


def _rid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _sentence_window(text: str, match: re.Match[str]) -> str:
    start = text.rfind("\n", 0, match.start())
    end = text.find("\n", match.end())
    if start < 0:
        start = max(0, match.start() - 160)
    if end < 0:
        end = min(len(text), match.end() + 160)
    return text[start:end].strip()


def mine_hard_requirements(canonical: CanonicalJobContent) -> JobRequirementProfile:
    text = canonical.full_description or ""
    title = canonical.title
    requirements: list[Requirement] = []
    groups: list[RequirementGroup] = []

    final_match = _FINAL_YEAR_OR_RECENT.search(text)
    if final_match:
        evidence = _sentence_window(text, final_match)
        window = 12
        window_match = _RECENT_GRAD_WINDOW.search(evidence)
        if window_match:
            window = int(window_match.group(1))
        a = Requirement(
            id=_rid("final-year"),
            category="academic_year",
            text="Candidate is in the final year of their degree program",
            importance="hard_required",
            evidence_text=evidence,
            structured_condition={"kind": "final_year"},
        )
        b = Requirement(
            id=_rid("recent-grad"),
            category="graduation",
            text=f"Candidate graduated within the previous {window} months",
            importance="hard_required",
            evidence_text=evidence,
            structured_condition={"kind": "recent_graduate", "months": window},
        )
        requirements.extend([a, b])
        groups.append(
            RequirementGroup(
                id=_rid("final-or-recent"),
                operator="any_of",
                requirement_ids=[a.id, b.id],
                text="Final year of degree program OR graduated within the stated recent-graduate window",
                evidence_text=evidence,
                importance="hard_required",
            )
        )

    enrolled = _ENROLLED.search(text)
    if enrolled and not final_match:
        evidence = _sentence_window(text, enrolled)
        requirements.append(
            Requirement(
                id=_rid("enrolled"),
                category="enrollment",
                text="Must currently be enrolled",
                importance="hard_required",
                evidence_text=evidence,
                structured_condition={"kind": "currently_enrolled"},
            )
        )

    no_sponsor = _NO_SPONSOR.search(text)
    if no_sponsor:
        evidence = _sentence_window(text, no_sponsor)
        requirements.append(
            Requirement(
                id=_rid("no-sponsor"),
                category="sponsorship",
                text="Sponsorship is not available",
                importance="hard_required",
                evidence_text=evidence,
                structured_condition={"kind": "sponsorship", "available": False},
            )
        )
    elif _SPONSOR_OK.search(text):
        evidence = _sentence_window(text, _SPONSOR_OK.search(text))  # type: ignore[arg-type]
        requirements.append(
            Requirement(
                id=_rid("sponsor-ok"),
                category="sponsorship",
                text="Sponsorship may be available",
                importance="preferred",
                evidence_text=evidence,
                structured_condition={"kind": "sponsorship", "available": True},
            )
        )

    if match := _US_AUTH.search(text):
        requirements.append(
            Requirement(
                id=_rid("us-auth"),
                category="work_authorization",
                text="Must be authorized to work in the United States",
                importance="hard_required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "work_authorization", "region": "us"},
            )
        )

    bachelor_match = _BACHELOR_OR_EQ.search(text)
    if bachelor_match:
        evidence = _sentence_window(text, bachelor_match)
        if not re.search(r"\b(plus|preferred|nice to have)\b", evidence, re.I):
            degree = Requirement(
                id=_rid("bachelor"),
                category="education",
                text="Bachelor's degree completed",
                importance="hard_required",
                evidence_text=evidence,
                structured_condition={"kind": "degree", "level": "bachelor"},
            )
            equivalent = Requirement(
                id=_rid("equiv-exp"),
                category="experience",
                text="Equivalent experience in lieu of a bachelor's degree",
                importance="hard_required",
                evidence_text=evidence,
                structured_condition={"kind": "equivalent_experience"},
            )
            requirements.extend([degree, equivalent])
            groups.append(
                RequirementGroup(
                    id=_rid("degree-or-exp"),
                    operator="any_of",
                    requirement_ids=[degree.id, equivalent.id],
                    text="Bachelor's degree OR equivalent experience",
                    evidence_text=evidence,
                    importance="hard_required",
                )
            )

    python_req = _PYTHON.search(text)
    sql_req = _SQL.search(text)
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    lowered = text.lower()
    if python_req and any(token in lowered for token in ("required", "must have", "requirements")):
        required_skills.append("Python")
    if sql_req and "sql" in lowered:
        if "python and sql" in lowered or re.search(r"\bsql\b", lowered):
            required_skills.append("SQL")
    if _AWS.search(text) and "preferred" in lowered:
        preferred_skills.append("AWS")

    if _PYTHON_AND_SQL.search(text) and "Python" in required_skills and "SQL" in required_skills:
        py_req = next((item for item in requirements if item.structured_condition and item.structured_condition.get("kind") == "skill" and item.structured_condition.get("name") == "Python"), None)
        sql_item = next((item for item in requirements if item.structured_condition and item.structured_condition.get("kind") == "skill" and item.structured_condition.get("name") == "SQL"), None)
        if py_req is None:
            py_req = Requirement(
                id=_rid("skill-python"),
                category="skill",
                text="Python required",
                importance="hard_required",
                evidence_text=_sentence_window(text, python_req) if python_req else "Python",
                structured_condition={"kind": "skill", "name": "Python"},
            )
            requirements.append(py_req)
        if sql_item is None:
            sql_item = Requirement(
                id=_rid("skill-sql"),
                category="skill",
                text="SQL required",
                importance="hard_required",
                evidence_text=_sentence_window(text, sql_req) if sql_req else "SQL",
                structured_condition={"kind": "skill", "name": "SQL"},
            )
            requirements.append(sql_item)
        groups.append(
            RequirementGroup(
                id=_rid("python-and-sql"),
                operator="all_of",
                requirement_ids=[py_req.id, sql_item.id],
                text="Python AND SQL",
                evidence_text=_sentence_window(text, _PYTHON_AND_SQL.search(text)),  # type: ignore[arg-type]
                importance="hard_required",
            )
        )

    work_mode: str = "unknown"
    remote_scope = None
    hybrid_days = None
    if match := _HYBRID_DAYS.search(text):
        work_mode = "hybrid"
        if match.group(1):
            hybrid_days = int(match.group(1))
        else:
            word = re.search(r"\b(one|two|three|four|five)\b", match.group(0), re.I)
            if word:
                hybrid_days = _HYBRID_DAY_WORDS[word.group(1).lower()]
    elif re.search(r"\bhybrid\b", text, re.I):
        work_mode = "hybrid"
    elif _REMOTE_US.search(text) or _REMOTE_CA.search(text) or re.search(r"\bremote\b", text, re.I):
        work_mode = "remote"
        if _REMOTE_US.search(text):
            remote_scope = "United States only"
        elif _REMOTE_CA.search(text):
            remote_scope = "California only"
    elif re.search(r"\b(on-?site|in office)\b", text, re.I):
        work_mode = "onsite"

    travel: list[Requirement] = []
    if match := _TRAVEL_PCT.search(text):
        evidence = _sentence_window(text, match)
        low = match.group(1) or match.group(3)
        high = match.group(2) or match.group(3)
        travel.append(
            Requirement(
                id=_rid("travel"),
                category="travel",
                text=f"Travel {low}-{high}%" if match.group(1) else f"Travel {low}%",
                importance="required",
                evidence_text=evidence,
                structured_condition={"kind": "travel_percent", "min": int(low), "max": int(high)},
            )
        )

    if match := _GPA.search(text):
        requirements.append(
            Requirement(
                id=_rid("gpa"),
                category="gpa",
                text=f"GPA {match.group(1)} or higher",
                importance="required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "gpa", "minimum": float(match.group(1))},
            )
        )
    if match := _CLEARANCE.search(text):
        requirements.append(
            Requirement(
                id=_rid("clearance"),
                category="security_clearance",
                text="Security clearance required",
                importance="hard_required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "security_clearance"},
            )
        )
    if match := _LICENSE.search(text):
        requirements.append(
            Requirement(
                id=_rid("license"),
                category="license",
                text=match.group(0),
                importance="hard_required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "license"},
            )
        )
    if match := _START_DATE.search(text):
        requirements.append(
            Requirement(
                id=_rid("start"),
                category="start_date",
                text=match.group(0).strip(),
                importance="required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "start_date"},
            )
        )
    relocation: list[Requirement] = []
    if match := _RELOC_REQUIRED.search(text):
        relocation.append(
            Requirement(
                id=_rid("reloc-req"),
                category="relocation",
                text="Relocation required",
                importance="required",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "relocation", "required": True},
            )
        )
    elif match := _RELOC_OFFERED.search(text):
        relocation.append(
            Requirement(
                id=_rid("reloc-offered"),
                category="relocation",
                text="Relocation offered",
                importance="preferred",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "relocation", "required": False},
            )
        )
    timezone_requirements = None
    if match := _TIMEZONE.search(text):
        timezone_requirements = _sentence_window(text, match)
    if match := _CPT_OK.search(text):
        requirements.append(
            Requirement(
                id=_rid("cpt"),
                category="cpt",
                text="CPT accepted",
                importance="preferred",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "cpt", "accepted": True},
            )
        )
    if match := _OPT_OK.search(text):
        requirements.append(
            Requirement(
                id=_rid("opt"),
                category="opt",
                text="OPT accepted",
                importance="preferred",
                evidence_text=_sentence_window(text, match),
                structured_condition={"kind": "opt", "accepted": True},
            )
        )

    paid_status = "unknown"
    if _UNPAID.search(text):
        paid_status = "unpaid"
    elif _PAID.search(text) or re.search(r"\bthis is a paid internship\b", text, re.I):
        paid_status = "paid"

    title_l = title.lower()
    if "intern" in title_l or re.search(r"\binternship\b", text, re.I):
        employment_type = "internship"
    elif "new grad" in title_l or "new-grad" in title_l or re.search(r"\bnew\s+grad(?:uate)?\b", text, re.I):
        employment_type = "new_grad"
    elif re.search(r"\bco-?op\b", text + " " + title, re.I):
        employment_type = "co_op"
    elif re.search(r"\bpart[- ]time\b", text, re.I):
        employment_type = "part_time"
    elif re.search(r"\bcontract\b", text, re.I):
        employment_type = "contract"
    elif re.search(r"\bfull[- ]time\b", text, re.I):
        employment_type = "full_time"
    else:
        employment_type = "unknown"
    raw_level = seniority_from_text(title, text)
    level_map = {
        "intern": "intern",
        "junior": "junior",
        "entry": "entry",
        "entry-level": "entry",
        "associate": "entry",
        "mid": "mid",
        "mid-level": "mid",
        "senior": "senior",
        "staff": "staff",
        "principal": "principal",
        "lead": "lead",
        "manager": "manager",
        "director": "director",
    }
    level = level_map.get((raw_level or "").lower(), "unknown")

    locations: list[JobLocation] = []
    haystack = f"{title}\n{text}"
    for city in _KNOWN_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", haystack):
            locations.append(JobLocation(label=city, evidence_text=city))

    family = occupational_family(title)
    return JobRequirementProfile(
        role_title=title,
        role_family=family,
        experience_level=level,  # type: ignore[arg-type]
        employment_type=employment_type,  # type: ignore[arg-type]
        required_skills=sorted(set(required_skills)),
        preferred_skills=sorted(set(preferred_skills)),
        locations=locations,
        work_mode=work_mode,  # type: ignore[arg-type]
        remote_scope=remote_scope,
        timezone_requirements=timezone_requirements,
        hybrid_onsite_frequency=hybrid_days,
        relocation_requirements=relocation,
        travel_requirements=travel,
        paid_status=paid_status,  # type: ignore[arg-type]
        requirements=requirements,
        requirement_groups=groups,
        academic_year_requirements=[item for item in requirements if item.category == "academic_year"],
        graduation_requirements=[item for item in requirements if item.category == "graduation"],
        enrollment_requirements=[item for item in requirements if item.category == "enrollment"],
        education_requirements=[item for item in requirements if item.category == "education"],
        gpa_requirements=[item for item in requirements if item.category == "gpa"],
        licenses=[item for item in requirements if item.category == "license"],
        security_clearance_requirements=[item for item in requirements if item.category == "security_clearance"],
        start_date_requirements=[item for item in requirements if item.category == "start_date"],
        cpt_information=[item for item in requirements if item.category == "cpt"],
        opt_information=[item for item in requirements if item.category == "opt"],
        sponsorship_information=[item for item in requirements if item.category == "sponsorship"],
        work_authorization_requirements=[item for item in requirements if item.category == "work_authorization"],
        extraction_confidence=72.0 if groups or requirements else 40.0,
        source_fingerprint=canonical.source_fingerprint,
        content_status=canonical.content_status,
        canonical=canonical,
    )

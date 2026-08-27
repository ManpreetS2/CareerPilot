"""Fit Score V2: qualification, preference, eligibility, confidence, ranking.

Deterministic and local. No LLM. Unknown is not mismatch. Sparse evidence
does not renormalize remaining weights into an inflated percentage.

Responsibility matching uses deterministic token overlap and conservative
skill families. An embedding layer is a later enhancement and is not used
here — automatic discovery must stay local and LLM-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from backend.db.models import Candidate, JobRecord, TargetPreference
    from backend.services.analysis_service import GroundedRequirements, SkillMatchResult

SCORING_VERSION = 2
NEUTRAL_PRIOR = 50.0

QUAL_REQUIRED_SKILLS = 0.25
QUAL_EXPERIENCE_RESP = 0.25
QUAL_REQUIRED_QUALS = 0.20
QUAL_ROLE_SENIORITY = 0.15
QUAL_PREFERRED = 0.10
QUAL_DOMAIN_SOFT = 0.05

OVERALL_QUAL_SHARE = 0.85
OVERALL_PREF_SHARE = 0.15

EligibilityStatus = Literal["likely_eligible", "eligibility_uncertain", "likely_ineligible"]
ConfidenceLevel = Literal["high", "medium", "low"]
MatchTier = Literal["strong_match", "good_match", "possible_match", "weak_match"]
ApplyRecommendation = Literal["strong_apply", "apply", "consider", "probably_skip"]
CompatRecommendation = Literal["apply", "consider", "skip"]

_SENIORITY_RANK = {
    "intern": 0,
    "internship": 0,
    "intern-level": 0,
    "entry": 1,
    "entry-level": 1,
    "junior": 1,
    "associate": 1,
    "mid": 2,
    "mid-level": 2,
    "intermediate": 2,
    "senior": 3,
    "staff": 4,
    "principal": 5,
    "lead": 4,
    "manager": 4,
    "director": 5,
}

_OCCUPATIONAL_RE = re.compile(
    r"\b(?:engineer|developer|analyst|scientist|intern|designer|manager|"
    r"product|data|security|researcher|architect|consultant|specialist|"
    r"programmer|sre|devops|frontend|backend|full[\s-]?stack)\b",
    re.I,
)

_LEVEL_TOKENS = frozenset(
    {
        "intern", "internship", "internships", "junior", "senior", "staff", "principal",
        "associate", "entry", "level", "graduate", "newgrad", "coop", "mid", "lead",
        "manager", "director", "i", "ii", "iii",
    }
)

OccupationalFamily = Literal[
    "software_engineering",
    "data_analytics",
    "data_science",
    "machine_learning_ai",
    "product",
    "cybersecurity",
    "cloud_devops",
    "it_support",
    "finance",
    "investment_banking",
    "accounting",
    "consulting",
    "sales",
    "customer_success",
    "marketing",
    "design",
    "operations",
    "hr_recruiting",
    "legal",
    "healthcare",
    "other",
]

# First matching rule wins. More specific families must appear before broader ones.
_FAMILY_RULES: tuple[tuple[OccupationalFamily, re.Pattern[str]], ...] = (
    ("investment_banking", re.compile(r"investment\s+bank|\bequity research\b|sales\s*&\s*trading", re.I)),
    ("accounting", re.compile(r"\b(?:accountant|accounting intern|audit intern|tax intern)\b", re.I)),
    ("finance", re.compile(r"\b(?:financial analyst|fp&a|corporate finance|treasury|asset management|wealth management)\b", re.I)),
    ("machine_learning_ai", re.compile(r"\b(?:machine learning|ml engineer|deep learning|artificial intelligence|ai engineer)\b", re.I)),
    ("data_science", re.compile(r"\bdata scien", re.I)),
    ("data_analytics", re.compile(r"\b(?:data analyst|analytics intern|business analyst|bi analyst)\b", re.I)),
    ("cybersecurity", re.compile(r"\b(?:security engineer|cybersecurity|infosec|appsec)\b", re.I)),
    ("cloud_devops", re.compile(r"\b(?:devops|sre\b|site reliability|cloud engineer|platform engineer)\b", re.I)),
    ("software_engineering", re.compile(
        r"\b(?:software engineer|software engineering|software developer|swe\b|backend|frontend|"
        r"full[\s-]?stack|mobile engineer|android engineer|ios engineer)\b",
        re.I,
    )),
    ("product", re.compile(r"\bproduct (?:manager|intern|analyst)\b|\bpm intern\b", re.I)),
    ("it_support", re.compile(r"\b(?:help desk|it support|desktop support)\b", re.I)),
    ("consulting", re.compile(r"\b(?:consulting intern|consultant intern|management consult)\b", re.I)),
    ("sales", re.compile(r"\b(?:sales intern|sales representative|sales associate|sdr\b|bdr\b)\b", re.I)),
    ("customer_success", re.compile(r"\bcustomer success\b", re.I)),
    ("marketing", re.compile(r"\b(?:marketing intern|marketing coordinator|marketing specialist)\b|\bmarketing\b", re.I)),
    ("design", re.compile(r"\b(?:product designer|ux intern|ui intern|graphic design|ux designer)\b", re.I)),
    ("hr_recruiting", re.compile(r"\b(?:recruiter|recruiting intern|human resources|\bhr intern)\b", re.I)),
    ("legal", re.compile(r"\b(?:paralegal|legal intern|counsel intern)\b", re.I)),
    ("healthcare", re.compile(r"\b(?:clinical intern|nursing intern|medical intern)\b", re.I)),
    ("operations", re.compile(r"\b(?:operations intern|ops intern|business operations intern)\b", re.I)),
)

_RELATED_FAMILIES: dict[str, frozenset[str]] = {
    "software_engineering": frozenset({"cloud_devops"}),
    "cloud_devops": frozenset({"software_engineering"}),
    "data_analytics": frozenset({"data_science"}),
    "data_science": frozenset({"data_analytics", "machine_learning_ai"}),
    "machine_learning_ai": frozenset({"data_science"}),
}

_ROLE_HEADING = re.compile(
    r"^(?:requirements?|qualifications?|responsibilities|about the role|the role|"
    r"what you.?ll do|what you will do|job (?:description|summary)|duties|"
    r"must have|minimum qualifications)\b",
    re.I,
)
_IGNORE_HEADING = re.compile(
    r"^(?:about us|about the company|who we are|our (?:culture|mission|values|story)|"
    r"benefits|perks|equal opportunity|eeo|life at|why join|what we offer)\b",
    re.I,
)

_STOP = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "of", "for", "with", "in", "on",
        "our", "you", "will", "your", "this", "that", "from", "as", "be", "by",
        "at", "is", "are", "we", "work", "using", "across", "into", "able",
        "team", "role", "job",
    }
)

_RESP_FAMILIES = (
    frozenset({"api", "rest", "endpoint", "fastapi", "django", "flask", "backend", "service"}),
    frozenset({"frontend", "react", "ui", "typescript", "javascript", "css", "html"}),
    frozenset({"data", "sql", "pipeline", "warehouse", "analytics", "etl"}),
    frozenset({"test", "testing", "pytest", "qa", "automation"}),
    frozenset({"deploy", "docker", "kubernetes", "ci", "cd", "devops", "infrastructure"}),
    frozenset({"ml", "model", "training", "pytorch", "tensorflow"}),
)

_GENERIC_SOFT = frozenset(
    {
        "communication", "communicator", "motivated", "team player", "passionate",
        "self-starter", "detail-oriented", "hard worker", "fast learner", "go-getter",
        "customer", "sales", "leadership", "collaboration", "team",
    }
)

# Strong phrases only, and only when they appear in role-focused text.
_SOFT_EVIDENCE = (
    ("customer-facing work", ("customer-facing", "client-facing")),
    ("cross-functional collaboration", ("cross-functional collaboration",)),
    ("fintech domain", ("fintech",)),
    ("quota-carrying sales work", ("quota-carrying", "sales quota")),
)


@dataclass
class Dimension:
    score: float | None
    mode: Literal["scored", "neutral", "na"]


@dataclass
class FitV2Result:
    overall: float
    qualification: float
    preference: float | None
    skill: float | None
    experience: float | None
    education: float | None
    location: float | None
    confidence_score: float
    confidence_level: ConfidenceLevel
    eligibility_status: EligibilityStatus
    match_tier: MatchTier
    apply_recommendation: ApplyRecommendation
    recommendation: CompatRecommendation
    ranking_score: float
    score_kind: Literal["full", "preliminary"]
    rationale: str
    matched: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)
    gap_reasons: list[str] = field(default_factory=list)
    watchouts: list[str] = field(default_factory=list)
    covered_responsibilities: list[str] = field(default_factory=list)
    partial_responsibilities: list[str] = field(default_factory=list)
    uncovered_responsibilities: list[str] = field(default_factory=list)


def has_occupational_signal(title: str | None) -> bool:
    return bool(title and _OCCUPATIONAL_RE.search(title))


def occupational_family(title: str | None) -> OccupationalFamily | None:
    """Classify a job/target title into an occupational family, or None if weak."""
    if not title or not title.strip():
        return None
    for family, pattern in _FAMILY_RULES:
        if pattern.search(title):
            return family
    return None


def _content_tokens(text: str) -> set[str]:
    return {tok for tok in _tokens(text) if tok not in _LEVEL_TOKENS}


def _role_focused_text(title: str | None, description: str | None, responsibilities: list[str]) -> str:
    parts = [title or ""]
    parts.extend(item for item in responsibilities if item.strip())
    ignore = False
    kept: list[str] = []
    for line in (description or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _IGNORE_HEADING.search(stripped):
            ignore = True
            continue
        if _ROLE_HEADING.search(stripped):
            ignore = False
            kept.append(stripped)
            continue
        if not ignore:
            kept.append(stripped)
    parts.extend(kept)
    return "\n".join(parts)


def _family_alignment(job_family: str | None, candidate_families: set[str]) -> float | None:
    if job_family is None or not candidate_families:
        return None
    if job_family in candidate_families:
        return 100.0
    if any(
        job_family in _RELATED_FAMILIES.get(family, frozenset())
        or family in _RELATED_FAMILIES.get(job_family, frozenset())
        for family in candidate_families
    ):
        return 58.0
    return 12.0


def seniority_from_text(*parts: str | None) -> str | None:
    blob = " ".join(part for part in parts if part)
    if not blob:
        return None
    lowered = blob.lower()
    if re.search(r"\bintern(?:s|ship)?\b", lowered):
        return "intern"
    for label in (
        "principal", "director", "staff", "manager", "senior", "lead",
        "junior", "associate", "entry-level", "entry", "mid-level", "mid",
    ):
        if re.search(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", lowered):
            return label
    return None


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z][a-z0-9+.#]{1,}", text.lower()) if tok not in _STOP}


def _candidate_blobs(candidate: Candidate) -> list[str]:
    blobs: list[str] = []
    for skill in candidate.skills or []:
        if isinstance(skill, str):
            blobs.append(skill)
    for project in candidate.projects or []:
        if not isinstance(project, dict):
            continue
        for key in ("name", "description"):
            value = project.get(key)
            if isinstance(value, str):
                blobs.append(value)
        for tech in project.get("technologies") or []:
            if isinstance(tech, str):
                blobs.append(tech)
    for item in candidate.experience or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if isinstance(title, str):
            blobs.append(title)
        for highlight in item.get("highlights") or []:
            if isinstance(highlight, str):
                blobs.append(highlight)
    return blobs


def _responsibility_coverage(job_resp: str, blobs: list[str]) -> Literal["full", "partial", "none"]:
    job_tokens = _tokens(job_resp)
    if len(job_tokens) < 2:
        return "none"
    best = 0.0
    for blob in blobs:
        cand = _tokens(blob)
        if not cand:
            continue
        overlap = job_tokens & cand
        best = max(best, len(overlap) / max(len(job_tokens), 1))
        for family in _RESP_FAMILIES:
            if job_tokens & family and cand & family:
                best = max(best, 0.72)
    if best >= 0.45:
        return "full"
    if best >= 0.22:
        return "partial"
    return "none"


def _combine_dimensions(parts: list[tuple[float, Dimension]]) -> float:
    usable = [(weight, dim) for weight, dim in parts if dim.mode != "na"]
    if not usable:
        return NEUTRAL_PRIOR
    total = 0.0
    weight_sum = 0.0
    for weight, dim in usable:
        value = dim.score if dim.mode == "scored" and dim.score is not None else NEUTRAL_PRIOR
        total += weight * value
        weight_sum += weight
    return max(0.0, min(100.0, total / weight_sum))


def _title_overlap(job_title: str, roles: list[str]) -> float | None:
    usable = [role.strip() for role in roles if isinstance(role, str) and role.strip()]
    if not usable:
        return None
    title_tokens = _content_tokens(job_title)
    if not title_tokens:
        return 0.0
    best = 0.0
    for role in usable:
        role_tokens = _content_tokens(role)
        if not role_tokens:
            continue
        occupational = re.sub(
            r"\b(?:intern(?:ship|ships)?|junior|senior|staff|principal|entry[- ]level)\b",
            " ",
            role,
            flags=re.I,
        ).strip()
        if occupational and re.search(
            rf"(?<![a-z0-9]){re.escape(occupational.lower())}(?![a-z0-9])",
            job_title.lower(),
        ):
            return 100.0
        overlap = title_tokens & role_tokens
        best = max(best, 100.0 * len(overlap) / max(len(role_tokens), 1))
    return best


def _is_internship(title: str, seniority: str | None) -> bool:
    if (seniority or "").lower() in {"intern", "internship", "intern-level"}:
        return True
    return bool(re.search(r"\bintern(?:s|ship)?\b", title or "", flags=re.I))


def _role_type_from_constraints(constraints: list | None) -> str:
    for item in constraints or []:
        if isinstance(item, str) and item.startswith("role_type:"):
            return item.split(":", 1)[1]
    return "both"


def _sponsorship_signal(text: str) -> Literal["none", "available", None]:
    lowered = text.lower()
    if re.search(
        r"\b(?:no sponsorship|not sponsoring|cannot sponsor|"
        r"without (?:visa )?sponsorship|unrestricted work authorization)\b",
        lowered,
    ):
        return "none"
    if re.search(r"\b(?:visa )?sponsorship (?:is )?available|will sponsor\b", lowered):
        return "available"
    return None


def _license_requirement(text: str) -> str | None:
    match = re.search(
        r"\b(?:must (?:have|hold)|required)\b.{0,40}\b("
        r"cpa|bar license|medical license|pe license|driver'?s license|"
        r"professional engineer|security clearance)\b",
        text,
        flags=re.I,
    )
    return match.group(1) if match else None


def _degree_or_equivalent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:bachelor|master|degree).{0,40}\bor\b.{0,20}equivalent\b|"
            r"\bequivalent experience\b",
            text,
            flags=re.I,
        )
    )


def _completed_degree_required(text: str) -> bool:
    lowered = text.lower()
    if "or equivalent" in lowered:
        return False
    return bool(
        re.search(
            r"\b(?:must have (?:completed|earned)|completed bachelor|"
            r"have (?:already )?graduated|bachelor'?s degree required)\b",
            lowered,
        )
    )


def _enrollment_required(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:currently enrolled|must be enrolled|must be a (?:current )?student|"
            r"enrolled in a .{0,20}program)\b",
            text,
            flags=re.I,
        )
    )


def compute_fit_v2(
    job: JobRecord,
    candidate: Candidate,
    preferences: TargetPreference | None,
    requirements: GroundedRequirements,
    skill_match: SkillMatchResult,
    skill_component: float | None,
    experience_years_score: float | None,
    education_score: float | None,
    location_score: float | None,
    *,
    as_of: date,
    experience_years: float | None,
) -> FitV2Result:
    from backend.services.analysis_service import (
        _canonical_skill_key,
        _candidate_work_modes,
        _explicit_work_modes,
        _parse_annual_salary,
    )

    posting = f"{job.title}\n{job.description}"
    blobs = _candidate_blobs(candidate)
    reasons: list[str] = []
    gaps: list[str] = []
    watchouts: list[str] = []

    required_n = len(requirements.required)
    required_keys = {_canonical_skill_key(item) for item in requirements.required}
    missing_required = [
        label for label in skill_match.missing if _canonical_skill_key(label) in required_keys
    ]
    if skill_match.required_ratio is not None and required_n:
        matched_req = required_n - len(missing_required)
        reasons.append(f"You match {matched_req} of {required_n} required technical skills.")
        if missing_required:
            gaps.append(
                f"This role asks for {missing_required[0]}, which is not present in your profile."
            )

    if skill_match.required_ratio is not None:
        req_dim = Dimension(round(100.0 * skill_match.required_ratio, 1), "scored")
    elif requirements.source == "preliminary":
        req_dim = Dimension(NEUTRAL_PRIOR, "neutral")
    else:
        req_dim = Dimension(None, "na")

    covered: list[str] = []
    partial_resp: list[str] = []
    uncovered: list[str] = []
    resp_scores: list[float] = []
    responsibilities = [item for item in (requirements.responsibilities or []) if item.strip()]
    for index, item in enumerate(responsibilities[:12]):
        coverage = _responsibility_coverage(item, blobs)
        weight = 1.4 if index < 3 else 1.0
        copies = max(1, int(weight * 10))
        if coverage == "full":
            covered.append(item)
            resp_scores.extend([100.0] * copies)
        elif coverage == "partial":
            partial_resp.append(item)
            resp_scores.extend([55.0] * copies)
        else:
            uncovered.append(item)
            resp_scores.extend([0.0] * copies)
    if covered:
        snippet = covered[0] if len(covered[0]) <= 90 else covered[0][:87] + "…"
        reasons.append(f"Your experience supports this role's work: {snippet}")
    if uncovered:
        gaps.append("Some listed responsibilities are not evidenced on your profile.")

    years_part = experience_years_score
    if resp_scores and years_part is not None:
        exp_value = 0.55 * (sum(resp_scores) / len(resp_scores)) + 0.45 * years_part
        exp_dim = Dimension(round(exp_value, 1), "scored")
    elif resp_scores:
        exp_dim = Dimension(round(sum(resp_scores) / len(resp_scores), 1), "scored")
    elif years_part is not None:
        exp_dim = Dimension(years_part, "scored")
    elif not responsibilities and requirements.years_experience is None:
        if len((job.description or "").strip()) < 280:
            exp_dim = Dimension(NEUTRAL_PRIOR, "neutral")
        else:
            exp_dim = Dimension(None, "na")
    else:
        exp_dim = Dimension(NEUTRAL_PRIOR, "neutral")

    or_equivalent = _degree_or_equivalent(posting)
    enrollment_needed = _enrollment_required(posting)
    completed_needed = _completed_degree_required(posting)
    qual_bits: list[float] = []
    enrolled = (preferences.currently_enrolled_in_program or "").strip().lower() if preferences else ""
    if education_score is not None:
        if or_equivalent and education_score < 100 and (experience_years or 0) >= 4:
            qual_bits.append(100.0)
            reasons.append("Equivalent experience satisfies the degree-or-equivalent requirement.")
        else:
            qual_bits.append(education_score)
            if education_score >= 100:
                reasons.append("Your education matches an explicit requirement.")
            elif education_score == 0:
                gaps.append("An explicit education requirement is not evidenced on your profile.")
    if enrollment_needed:
        if enrolled in {"yes", "true", "1", "currently enrolled"}:
            qual_bits.append(100.0)
            reasons.append("Your current enrollment satisfies the student requirement.")
        elif enrolled in {"no", "false", "0"}:
            qual_bits.append(0.0)
            gaps.append("This role requires current enrollment.")
        else:
            qual_bits.append(NEUTRAL_PRIOR)
    if requirements.education_requirements or enrollment_needed or completed_needed:
        req_qual_dim = Dimension(
            round(sum(qual_bits) / len(qual_bits), 1) if qual_bits else NEUTRAL_PRIOR,
            "scored" if qual_bits else "neutral",
        )
    elif len((job.description or "").strip()) < 280:
        req_qual_dim = Dimension(NEUTRAL_PRIOR, "neutral")
    else:
        req_qual_dim = Dimension(None, "na")

    job_seniority = requirements.seniority or seniority_from_text(job.title, job.description)
    cand_titles = [
        item["title"]
        for item in (candidate.experience or [])
        if isinstance(item, dict) and isinstance(item.get("title"), str)
    ]
    target_roles = list(preferences.target_roles or []) if preferences else []
    cand_seniority = seniority_from_text(*(cand_titles + target_roles))
    if cand_seniority is None and any(_is_internship(role, None) for role in target_roles):
        cand_seniority = "intern"

    job_family = occupational_family(job.title)
    candidate_families = {
        family
        for source in (*target_roles, *cand_titles)
        if (family := occupational_family(source))
    }
    family_score = _family_alignment(job_family, candidate_families)
    token_title_fit = _title_overlap(job.title, target_roles) if target_roles else None
    if family_score is not None:
        title_fit = family_score
    else:
        title_fit = token_title_fit

    role_bits: list[float] = []
    # ~10 of the 15-point title/seniority component is occupational family.
    if title_fit is not None:
        role_bits.extend([title_fit, title_fit])
        if title_fit >= 80:
            reasons.append("The job title aligns with your target roles.")
        elif title_fit <= 20:
            gaps.append("This title is outside your saved occupational lane.")
    if job_seniority or cand_seniority:
        job_rank = _SENIORITY_RANK.get((job_seniority or "mid").lower(), 2)
        cand_rank = _SENIORITY_RANK.get((cand_seniority or "entry").lower(), 1)
        delta = abs(job_rank - cand_rank)
        seniority_score = {0: 100.0, 1: 72.0, 2: 40.0}.get(delta, 15.0)
        if job_rank >= 3 and cand_rank <= 1:
            seniority_score = min(seniority_score, 18.0)
        role_bits.append(seniority_score)
        if seniority_score <= 40:
            gaps.append("Seniority on this posting does not match your experience level.")
    role_dim = Dimension(round(sum(role_bits) / len(role_bits), 1), "scored") if role_bits else Dimension(NEUTRAL_PRIOR, "neutral")

    if skill_match.preferred_ratio is not None:
        pref_skill_dim = Dimension(round(100.0 * skill_match.preferred_ratio, 1), "scored")
        preferred_missing = [label for label in skill_match.missing if label not in missing_required]
        for label in preferred_missing[:2]:
            gaps.append(f"{label} is preferred and not on your profile.")
    else:
        pref_skill_dim = Dimension(None, "na")

    domain_hits = 0
    domain_checked = 0
    family_mismatch = family_score is not None and family_score <= 20
    role_text = _role_focused_text(job.title, job.description, responsibilities).lower()
    blob_text = " ".join(blobs).lower()
    if not family_mismatch:
        for label, needles in _SOFT_EVIDENCE:
            if any(needle in role_text for needle in needles):
                domain_checked += 1
                if any(needle in blob_text for needle in needles):
                    domain_hits += 1
                    reasons.append(f"Your background includes {label} this posting asks about.")
    if any(word in role_text for word in _GENERIC_SOFT):
        watchouts.append("Generic soft-skill wording on the posting was not treated as a skill match.")
    domain_dim = (
        Dimension(round(100.0 * domain_hits / domain_checked, 1), "scored")
        if domain_checked
        else Dimension(None, "na")
    )

    qualification = round(
        _combine_dimensions(
            [
                (QUAL_REQUIRED_SKILLS, req_dim),
                (QUAL_EXPERIENCE_RESP, exp_dim),
                (QUAL_REQUIRED_QUALS, req_qual_dim),
                (QUAL_ROLE_SENIORITY, role_dim),
                (QUAL_PREFERRED, pref_skill_dim),
                (QUAL_DOMAIN_SOFT, domain_dim),
            ]
        ),
        1,
    )

    if len(missing_required) >= 3:
        qualification = min(qualification, 62.0)
    elif len(missing_required) >= 2:
        qualification = min(qualification, 74.0)
    elif len(missing_required) == 1 and required_n >= 1:
        qualification = min(qualification, 86.0)
    if job_seniority and cand_seniority:
        job_rank = _SENIORITY_RANK.get(job_seniority.lower(), 2)
        cand_rank = _SENIORITY_RANK.get(cand_seniority.lower(), 1)
        if job_rank >= 3 and cand_rank <= 1:
            qualification = min(qualification, 55.0)

    pref_bits: list[float] = []
    if location_score is not None:
        pref_bits.append(location_score)
    if title_fit is not None:
        pref_bits.append(title_fit)
    role_type = _role_type_from_constraints(preferences.constraints if preferences else None)
    internship_job = _is_internship(job.title, job_seniority)
    if role_type == "internships" and not internship_job:
        pref_bits.append(20.0)
        gaps.append("You asked for internships; this posting reads as full-time.")
    elif role_type == "full_time" and internship_job:
        pref_bits.append(25.0)
        gaps.append("You asked for full-time roles; this posting reads as an internship.")
    salary_floor = preferences.salary_min if preferences else None
    job_salary = _parse_annual_salary(job.salary)
    if isinstance(salary_floor, int) and salary_floor >= 10_000:
        if job_salary is None:
            watchouts.append("Salary is not listed, so pay alignment is unknown.")
        elif job_salary >= salary_floor:
            pref_bits.append(100.0)
        else:
            pref_bits.append(18.0)
            gaps.append("Listed pay is below your saved minimum.")
    preference = round(sum(pref_bits) / len(pref_bits), 1) if pref_bits else None
    if preference is not None and isinstance(salary_floor, int) and job_salary is not None and job_salary < salary_floor:
        preference = min(preference, 45.0)
    if preference is not None and (
        (role_type == "internships" and not internship_job)
        or (role_type == "full_time" and internship_job)
    ):
        preference = min(preference, 48.0)
    overall = qualification if preference is None else OVERALL_QUAL_SHARE * qualification + OVERALL_PREF_SHARE * preference

    eligibility: EligibilityStatus = "eligibility_uncertain"
    explicit_pass = 0
    unevaluable = 0
    hard_blockers = 0
    sponsor = _sponsorship_signal(posting)
    needs_sponsor = preferences.sponsorship_required if preferences else None
    if sponsor == "none" and needs_sponsor is True:
        eligibility = "likely_ineligible"
        hard_blockers += 1
        gaps.append("This posting says sponsorship is not available.")
    elif sponsor == "available" and needs_sponsor is True:
        explicit_pass += 1
        reasons.append("The posting indicates sponsorship may be available.")
    elif sponsor is None:
        watchouts.append("Work authorization requirements were not listed.")
    elif needs_sponsor is False and sponsor == "none":
        explicit_pass += 1

    license_needed = _license_requirement(posting)
    if license_needed:
        certs = " ".join(item for item in (candidate.certifications or []) if isinstance(item, str)).lower()
        if license_needed.lower() not in certs:
            eligibility = "likely_ineligible"
            hard_blockers += 1
            gaps.append("A required license or certification is not evidenced on your profile.")
        else:
            explicit_pass += 1

    if completed_needed:
        graduated = False
        for edu in candidate.education or []:
            if isinstance(edu, dict) and str(edu.get("graduation_year") or "").strip():
                try:
                    if int(str(edu.get("graduation_year"))[:4]) <= as_of.year:
                        graduated = True
                except ValueError:
                    graduated = True
        if enrolled in {"yes", "true", "1"} and not graduated:
            eligibility = "likely_ineligible"
            hard_blockers += 1
            gaps.append("This role requires a completed degree.")
        elif graduated:
            explicit_pass += 1
        else:
            unevaluable += 1

    if enrollment_needed:
        if enrolled in {"yes", "true", "1", "currently enrolled"}:
            explicit_pass += 1
        elif enrolled in {"no", "false", "0"}:
            eligibility = "likely_ineligible"
            hard_blockers += 1
        else:
            unevaluable += 1
            watchouts.append("Enrollment status is needed for this internship-style requirement.")

    job_modes = _explicit_work_modes(job.location) | _explicit_work_modes((job.description or "")[:1200])
    remote_only = (preferences.remote_preference or "").strip().lower() in {"remote"} if preferences else False
    if remote_only and job_modes == {"onsite"}:
        eligibility = "likely_ineligible"
        hard_blockers += 1
        gaps.append("This role is onsite and your saved preference is remote-only.")

    if eligibility != "likely_ineligible":
        if unevaluable:
            eligibility = "eligibility_uncertain"
        elif explicit_pass:
            eligibility = "likely_eligible"
        elif requirements.source == "preliminary" and len((job.description or "").strip()) < 280:
            eligibility = "eligibility_uncertain"
        else:
            eligibility = "likely_eligible"

    if hard_blockers >= 2:
        qualification = min(qualification, 48.0)
        overall = min(overall, 48.0)
    elif eligibility == "likely_ineligible":
        overall = min(overall, 55.0)

    signals = 0.0
    if requirements.source == "intelligence":
        signals += 2.0
    if required_n >= 3:
        signals += 1.5
    elif required_n:
        signals += 0.7
    if skill_match.preferred_ratio is not None:
        signals += 0.4
    if responsibilities:
        signals += 1.2
    if requirements.years_experience is not None:
        signals += 0.8
    if requirements.education_requirements:
        signals += 0.5
    if job.location:
        signals += 0.6
    if sponsor is not None:
        signals += 0.5
    desc_len = len((job.description or "").strip())
    if desc_len >= 900:
        signals += 1.2
    elif desc_len >= 280:
        signals += 0.6
    if candidate.skills and (candidate.experience or candidate.projects):
        signals += 0.8
    if requirements.source == "preliminary":
        signals = min(signals, 2.2)
    confidence_score = max(12.0, min(100.0, round(100.0 * signals / 10.5, 1)))
    if requirements.source == "intelligence":
        confidence_score = max(48.0, confidence_score)
    if confidence_score >= 75:
        confidence_level: ConfidenceLevel = "high"
    elif confidence_score >= 48:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    ranking_score = round(
        (confidence_score / 100.0) * overall + (1.0 - confidence_score / 100.0) * NEUTRAL_PRIOR,
        1,
    )
    overall = max(0.0, min(100.0, round(overall, 1)))
    qualification = max(0.0, min(100.0, round(qualification, 1)))

    if overall >= 85:
        match_tier: MatchTier = "strong_match"
    elif overall >= 70:
        match_tier = "good_match"
    elif overall >= 55:
        match_tier = "possible_match"
    else:
        match_tier = "weak_match"

    score_kind: Literal["full", "preliminary"] = (
        "full" if requirements.source == "intelligence" else "preliminary"
    )
    if match_tier == "strong_match" and confidence_level == "low":
        match_tier = "good_match"

    if eligibility == "likely_ineligible":
        apply_rec: ApplyRecommendation = "probably_skip"
        if match_tier == "strong_match":
            match_tier = "weak_match"
    elif score_kind != "full" or confidence_level == "low":
        apply_rec = "consider" if overall >= 55 else "probably_skip"
    elif overall >= 88 and confidence_level == "high":
        apply_rec = "strong_apply"
    elif overall >= 80:
        apply_rec = "apply"
    elif overall >= 55:
        apply_rec = "consider"
    else:
        apply_rec = "probably_skip"

    compat: CompatRecommendation = (
        "apply" if apply_rec in {"strong_apply", "apply"} else "consider" if apply_rec == "consider" else "skip"
    )
    if score_kind != "full" and compat == "apply":
        compat = "consider"
        apply_rec = "consider"

    mode = (
        "full Job Intelligence"
        if requirements.source == "intelligence"
        else "provisional explicit-description"
        if requirements.source == "description"
        else "preliminary"
    )
    rationale = (
        f"{mode} scoring (Fit V2). "
        f"Qualification {qualification}. "
        f"Preference {preference if preference is not None else 'unavailable'}. "
        f"Eligibility {eligibility.replace('_', ' ')}. "
        f"Confidence {confidence_level}. "
        f"Unknown requirements were not treated as mismatches. "
        f"Recommendation {compat}."
    )
    if requirements.source != "intelligence":
        rationale += " Full Job Intelligence could change this result. Apply is never returned for provisional scores."

    return FitV2Result(
        overall=overall,
        qualification=qualification,
        preference=preference,
        skill=None if skill_component is None else round(skill_component, 1),
        experience=None if exp_dim.mode != "scored" else round(exp_dim.score, 1),
        education=None if education_score is None else round(education_score, 1),
        location=None if location_score is None else round(location_score, 1),
        confidence_score=confidence_score,
        confidence_level=confidence_level,
        eligibility_status=eligibility,
        match_tier=match_tier,
        apply_recommendation=apply_rec,
        recommendation=compat,
        ranking_score=ranking_score,
        score_kind=score_kind,
        rationale=rationale,
        matched=list(skill_match.matched),
        partial=list(skill_match.partial),
        missing=list(skill_match.missing),
        match_reasons=reasons[:8],
        gap_reasons=gaps[:8],
        watchouts=watchouts[:6],
        covered_responsibilities=covered[:8],
        partial_responsibilities=partial_resp[:8],
        uncovered_responsibilities=uncovered[:8],
    )

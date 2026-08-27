"""Controlled hard-requirement recall benchmark on long realistic postings."""

from __future__ import annotations

from backend.services.job_content import canonical_from_job
from backend.services.requirement_mining import mine_hard_requirements

FILLER = ("Program details, interview process, benefits, and team rituals. " * 24)


def _posting(body: str, *, title: str = "Software Engineering Intern") -> str:
    return f"{title}\nAbout the team\n{FILLER}\n{body}\nClosing notes\n{FILLER}"


CASES: list[dict] = [
    {
        "id": "python_required",
        "text": _posting("Requirements\nPython required.\nSQL."),
        "expect": {"skills": ["Python"]},
    },
    {
        "id": "aws_preferred",
        "text": _posting("Requirements\nPython required.\nAWS preferred."),
        "expect": {"preferred": ["AWS"]},
    },
    {
        "id": "enrolled",
        "text": _posting("Must currently be enrolled as a student."),
        "expect": {"kinds": ["currently_enrolled"]},
    },
    {
        "id": "final_or_recent_end",
        "text": _posting("")
        + "\nCandidates must either be in the final year of their degree program or have graduated within the previous 12 months.",
        "expect": {"group": "any_of", "kinds": ["final_year", "recent_graduate"]},
    },
    {
        "id": "bachelor_or_eq",
        "text": _posting("Minimum qualifications: Bachelor's degree or equivalent experience."),
        "expect": {"group": "any_of", "kinds": ["degree", "equivalent_experience"]},
    },
    {
        "id": "no_sponsorship",
        "text": _posting("We are unable to provide visa sponsorship for this role."),
        "expect": {"kinds": ["sponsorship"]},
    },
    {
        "id": "sponsorship_unstated",
        "text": _posting("Python required. No immigration language appears here."),
        "expect": {"kinds_absent": ["sponsorship"]},
    },
    {
        "id": "us_auth",
        "text": _posting("Must be authorized to work in the United States."),
        "expect": {"kinds": ["work_authorization"]},
    },
    {
        "id": "opt_cpt",
        "text": _posting("CPT is accepted. OPT is accepted for this internship."),
        "expect": {"kinds": ["cpt", "opt"]},
    },
    {
        "id": "hybrid_three",
        "text": _posting("Hybrid, three days per week in San Francisco."),
        "expect": {"work_mode": "hybrid", "hybrid_days": 3, "cities": ["San Francisco"]},
    },
    {
        "id": "remote_us",
        "text": _posting("This role is Remote US only."),
        "expect": {"work_mode": "remote", "remote_scope": "United States only"},
    },
    {
        "id": "remote_ca",
        "text": _posting("Remote California only. Not worldwide."),
        "expect": {"work_mode": "remote", "remote_scope": "California only"},
    },
    {
        "id": "travel",
        "text": _posting("Remote, but 50–75% travel."),
        "expect": {"travel": True},
    },
    {
        "id": "multi_location",
        "text": _posting("Offices in San Francisco, New York, and Austin."),
        "expect": {"cities": ["San Francisco", "New York", "Austin"]},
    },
    {
        "id": "paid_intern",
        "text": _posting("This is a paid internship."),
        "expect": {"paid": "paid"},
    },
    {
        "id": "unpaid_intern",
        "text": _posting("This unpaid internship is for credit."),
        "expect": {"paid": "unpaid"},
    },
    {
        "id": "gpa",
        "text": _posting("Minimum qualifications include GPA 3.5."),
        "expect": {"kinds": ["gpa"]},
    },
    {
        "id": "clearance",
        "text": _posting("Active security clearance is required."),
        "expect": {"kinds": ["security_clearance"]},
    },
    {
        "id": "license",
        "text": _posting("A valid driver's license is required."),
        "expect": {"kinds": ["license"]},
    },
    {
        "id": "python_and_sql",
        "text": _posting("Requirements: Python and SQL are both required."),
        "expect": {"group": "all_of", "skills": ["Python", "SQL"]},
    },
]


def _mine(text: str):
    canonical = canonical_from_job(
        title="Software Engineering Intern",
        company="Benchmark Co",
        description=text,
        source="greenhouse",
        url="https://example.com/jobs/benchmark",
        content_status="full",
    )
    return mine_hard_requirements(canonical)


def test_hard_requirement_benchmark_has_twenty_postings() -> None:
    assert len(CASES) >= 20


def test_hard_requirement_recall() -> None:
    misses: list[str] = []
    for case in CASES:
        profile = _mine(case["text"])
        expect = case["expect"]
        kinds = {
            (item.structured_condition or {}).get("kind")
            for item in profile.requirements
            if item.structured_condition
        }
        if "skills" in expect:
            for skill in expect["skills"]:
                if skill not in profile.required_skills:
                    misses.append(f"{case['id']}: missing skill {skill}")
        if "preferred" in expect:
            for skill in expect["preferred"]:
                if skill not in profile.preferred_skills:
                    misses.append(f"{case['id']}: missing preferred {skill}")
        if "kinds" in expect:
            for kind in expect["kinds"]:
                if kind not in kinds:
                    misses.append(f"{case['id']}: missing kind {kind}")
        if "kinds_absent" in expect:
            for kind in expect["kinds_absent"]:
                if kind in kinds:
                    misses.append(f"{case['id']}: unexpected kind {kind}")
        if expect.get("group"):
            if not any(group.operator == expect["group"] for group in profile.requirement_groups):
                misses.append(f"{case['id']}: missing {expect['group']} group")
        if "work_mode" in expect and profile.work_mode != expect["work_mode"]:
            misses.append(f"{case['id']}: work_mode {profile.work_mode}")
        if "hybrid_days" in expect and profile.hybrid_onsite_frequency != expect["hybrid_days"]:
            misses.append(f"{case['id']}: hybrid days {profile.hybrid_onsite_frequency}")
        if "remote_scope" in expect and profile.remote_scope != expect["remote_scope"]:
            misses.append(f"{case['id']}: remote_scope {profile.remote_scope}")
        if "cities" in expect:
            labels = {item.label for item in profile.locations}
            for city in expect["cities"]:
                if city not in labels:
                    misses.append(f"{case['id']}: missing city {city}")
        if expect.get("travel") and not profile.travel_requirements:
            misses.append(f"{case['id']}: missing travel")
        if "paid" in expect and profile.paid_status != expect["paid"]:
            misses.append(f"{case['id']}: paid {profile.paid_status}")
    assert misses == []

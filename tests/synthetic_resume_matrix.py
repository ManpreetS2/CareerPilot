"""Privacy-safe synthetic resume layouts, manifests, and grounded-profile checks.

Fictional data only. Never print personal fields, resume text, or model output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tests.pdf_fixtures import (
    build_multipage_text_pdf,
    build_simple_text_pdf,
    build_two_column_text_pdf,
)

GENERATED_DIR = Path(__file__).resolve().parents[1] / "local_resumes" / "generated"
CAND_ID_RE = re.compile(r"^cand-\d{3,}$")

# Layout identifiers only — safe to print.
LAYOUT_TRADITIONAL = "traditional_single_column"
LAYOUT_TWO_COLUMN = "two_column_sidebar"
LAYOUT_MULTIPAGE = "multipage_repeated_anchor"


def _traditional() -> dict[str, Any]:
    text = """
Jordan Avery Quill
jordan.quill@example.com
+1-555-0101

Skills: Python, FastAPI, SQL, Docker

Experience
Software Engineer Intern, Northwind Systems
2024-06 – 2024-08
- Reduced p95 latency by 20% on search endpoints.
- Saved 500 engineering hours.

Projects
Harbor Atlas
Inventory dashboard with search and alerts.
Technologies: Python, FastAPI, React
https://github.com/example/harbor-atlas

Education
Lakeside Polytechnic — B.S. Computer Science, 2027

Certifications
AWS Cloud Practitioner
""".strip()
    return {
        "id": LAYOUT_TRADITIONAL,
        "pages": 1,
        "kind": "single",
        "text": text,
        "manifest": {
            "name": "Jordan Avery Quill",
            "email": "jordan.quill@example.com",
            "phone": "+1-555-0101",
            "allowed_skills": ["Python", "FastAPI", "SQL", "Docker", "React"],
            "projects": [
                {
                    "name": "Harbor Atlas",
                    "technologies": ["Python", "FastAPI", "React"],
                    "url": "https://github.com/example/harbor-atlas",
                }
            ],
            "experience": [
                {
                    "title": "Software Engineer Intern",
                    "company": "Northwind Systems",
                    "start_date": "2024-06",
                    "end_date": "2024-08",
                    "highlights": [
                        "Reduced p95 latency by 20% on search endpoints.",
                        "Saved 500 engineering hours.",
                    ],
                }
            ],
            "education": [
                {
                    "institution": "Lakeside Polytechnic",
                    "degree": "B.S.",
                    "field": "Computer Science",
                    "graduation_year": "2027",
                }
            ],
            "certifications": ["AWS Cloud Practitioner"],
            "numeric_unit_claims": ["20%", "500"],
            "never_survive": [
                "$500",
                "40%",
                "Quantum Teleportation",
                "Acme Warp Drive",
                "$20",
            ],
        },
    }


def _two_column() -> dict[str, Any]:
    left = """
Riley Chen-Moss
riley.moss@example.test
+1-555-0147

Skills
Python
C
R
Go
SQL

Education
Cedar Ridge University
B.S.
Applied Mathematics
2026
""".strip()
    right = """
Experience
Backend Engineer
Maple Circuit Labs
2025-01 – 2025-05
- Reduced costs by $100,000 annually.
- Improved throughput by 20%.

Projects
Signal Garden
Realtime telemetry viewer.
Technologies: Go, React
https://github.com/example/signal-garden

Notes
Career progression, research papers, and Google Cloud mentions
must not invent extra short skills.
""".strip()
    return {
        "id": LAYOUT_TWO_COLUMN,
        "pages": 1,
        "kind": "two_column",
        "left": left,
        "right": right,
        "manifest": {
            "name": "Riley Chen-Moss",
            "email": "riley.moss@example.test",
            "phone": "+1-555-0147",
            "allowed_skills": ["Python", "C", "R", "Go", "SQL", "React"],
            "projects": [
                {
                    "name": "Signal Garden",
                    "technologies": ["Go", "React"],
                    "url": "https://github.com/example/signal-garden",
                }
            ],
            "experience": [
                {
                    "title": "Backend Engineer",
                    "company": "Maple Circuit Labs",
                    "start_date": "2025-01",
                    "end_date": "2025-05",
                    "highlights": [
                        "Reduced costs by $100,000 annually.",
                        "Improved throughput by 20%.",
                    ],
                }
            ],
            "education": [
                {
                    "institution": "Cedar Ridge University",
                    "degree": "B.S.",
                    "field": "Applied Mathematics",
                    "graduation_year": "2026",
                }
            ],
            "certifications": [],
            "numeric_unit_claims": ["$100,000", "$100000", "20%"],
            "never_survive": [
                "Career",
                "Google",
                "20 points",
                "$20",
                "40%",
                "C++",
            ],
            "short_skills": ["C", "R", "Go"],
        },
    }


def _multipage() -> dict[str, Any]:
    page1 = """
Sam Rivera-Holt
sam.holt@example.com
+1-555-0199

Experience
Software Engineer
Helix Harbor
2024-01 – 2024-06
- Built APIs for Helix Harbor.

Software Engineer
Helix Harbor
2025-01 – 2025-06
- Second tour work at Helix Harbor.

Projects
Campus Beacon
Student events board.
Technologies: Python, FastAPI
https://github.com/example/campus-beacon
""".strip()
    page2 = """
Orbit Ledger
Orbital analytics dashboard.
Technologies: React
https://github.com/example/orbit-ledger

Education
State Harbor University
B.S.
Computer Science
2027
City Harbor College
A.A.
General Studies
2024
""".strip()
    return {
        "id": LAYOUT_MULTIPAGE,
        "pages": 2,
        "kind": "multipage",
        "pages_text": [page1, page2],
        "manifest": {
            "name": "Sam Rivera-Holt",
            "email": "sam.holt@example.com",
            "phone": "+1-555-0199",
            "allowed_skills": ["Python", "FastAPI", "React"],
            "projects": [
                {
                    "name": "Campus Beacon",
                    "technologies": ["Python", "FastAPI"],
                    "url": "https://github.com/example/campus-beacon",
                },
                {
                    "name": "Orbit Ledger",
                    "technologies": ["React"],
                    "url": "https://github.com/example/orbit-ledger",
                },
            ],
            "experience": [
                {
                    "title": "Software Engineer",
                    "company": "Helix Harbor",
                    "start_date": "2024-01",
                    "end_date": "2024-06",
                    "highlights": ["Built APIs for Helix Harbor."],
                },
                {
                    "title": "Software Engineer",
                    "company": "Helix Harbor",
                    "start_date": "2025-01",
                    "end_date": "2025-06",
                    "highlights": ["Second tour work at Helix Harbor."],
                },
            ],
            "education": [
                {
                    "institution": "State Harbor University",
                    "degree": "B.S.",
                    "field": "Computer Science",
                    "graduation_year": "2027",
                },
                {
                    "institution": "City Harbor College",
                    "degree": "A.A.",
                    "field": "General Studies",
                    "graduation_year": "2024",
                },
            ],
            "certifications": [],
            "numeric_unit_claims": ["2024-01", "2025-01", "2027", "2024"],
            "never_survive": ["Quantum Teleportation", "$500", "40%"],
        },
    }


LAYOUTS: list[dict[str, Any]] = [_traditional(), _two_column(), _multipage()]
LAYOUT_BY_ID = {item["id"]: item for item in LAYOUTS}


def layout_ids() -> list[str]:
    return [item["id"] for item in LAYOUTS]


def manifest_for(layout_id: str) -> dict[str, Any]:
    return LAYOUT_BY_ID[layout_id]["manifest"]


def forbidden_output_tokens() -> list[str]:
    """Values that must never appear in matrix runner stdout."""
    tokens: list[str] = []
    for layout in LAYOUTS:
        man = layout["manifest"]
        tokens.extend(
            [
                man["name"],
                man.get("email") or "",
                man.get("phone") or "",
            ]
        )
        for proj in man["projects"]:
            tokens.append(proj["name"])
            if proj.get("url"):
                tokens.append(proj["url"])
        for exp in man["experience"]:
            tokens.append(exp["company"])
            tokens.append(exp["title"])
        for edu in man["education"]:
            tokens.append(edu["institution"])
    return [token for token in tokens if token]


def build_pdf_bytes(layout: dict[str, Any]) -> bytes:
    kind = layout["kind"]
    if kind == "single":
        return build_simple_text_pdf(layout["text"])
    if kind == "two_column":
        return build_two_column_text_pdf(layout["left"], layout["right"])
    if kind == "multipage":
        return build_multipage_text_pdf(layout["pages_text"])
    raise ValueError(f"Unknown layout kind: {kind}")


def source_text(layout: dict[str, Any]) -> str:
    kind = layout["kind"]
    if kind == "single":
        return layout["text"]
    if kind == "two_column":
        return f"{layout['left']}\n{layout['right']}"
    if kind == "multipage":
        return "\n".join(layout["pages_text"])
    raise ValueError(f"Unknown layout kind: {kind}")


def expected_llm_payload(layout_id: str) -> dict[str, Any]:
    """Supported structured output (plus never_survive extras tests inject separately)."""
    man = manifest_for(layout_id)
    return {
        "name": man["name"],
        "email": man.get("email"),
        "phone": man.get("phone"),
        "skills": list(man["allowed_skills"]),
        "projects": [
            {
                "name": proj["name"],
                "description": None,
                "technologies": list(proj["technologies"]),
                "url": proj.get("url"),
            }
            for proj in man["projects"]
        ],
        "experience": [
            {
                "title": item["title"],
                "company": item["company"],
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
                "highlights": list(item.get("highlights") or []),
            }
            for item in man["experience"]
        ],
        "education": [
            {
                "institution": edu["institution"],
                "degree": edu.get("degree"),
                "field": edu.get("field"),
                "graduation_year": edu.get("graduation_year"),
            }
            for edu in man["education"]
        ],
        "certifications": list(man.get("certifications") or []),
        "strengths": [],
        "evidence_links": [proj["url"] for proj in man["projects"] if proj.get("url")],
    }


def write_layout_pdf(layout: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{layout['id']}.pdf"
    path.write_bytes(build_pdf_bytes(layout))
    return path


def write_layout_manifest(layout: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{layout['id']}.json"
    path.write_text(json.dumps(layout["manifest"], indent=2) + "\n", encoding="utf-8")
    return path


def generate_all(directory: Path | None = None) -> list[Path]:
    target = directory or GENERATED_DIR
    return [write_layout_pdf(layout, target) for layout in LAYOUTS]


def _profile_blob(profile: dict[str, Any]) -> str:
    return json.dumps(profile, default=str)


def evaluate_grounded_profile(profile: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    """Return failure codes only (no resume-derived values)."""
    failures: list[str] = []
    blob = _profile_blob(profile)

    if profile.get("name") != manifest["name"]:
        failures.append("name_not_supported")

    email = profile.get("email")
    if email and email != manifest.get("email"):
        failures.append("email_not_allowed")
    phone = profile.get("phone")
    if phone and phone != manifest.get("phone"):
        failures.append("phone_not_allowed")

    allowed_skills = set(manifest["allowed_skills"])
    for skill in profile.get("skills") or []:
        if skill not in allowed_skills:
            failures.append("skill_not_allowed")

    for token in manifest.get("never_survive") or []:
        if token and token in blob:
            failures.append("unsupported_claim_retained")

    allowed_projects = {item["name"]: item for item in manifest["projects"]}
    for project in profile.get("projects") or []:
        spec = allowed_projects.get(project.get("name"))
        if spec is None:
            failures.append("project_not_allowed")
            continue
        for tech in project.get("technologies") or []:
            if tech not in spec["technologies"]:
                failures.append("project_tech_leak")
        url = project.get("url")
        if url and url != spec.get("url"):
            failures.append("project_url_leak")

    remaining_exp = list(manifest["experience"])
    for item in profile.get("experience") or []:
        match_idx = next(
            (
                idx
                for idx, spec in enumerate(remaining_exp)
                if spec["title"] == item.get("title") and spec["company"] == item.get("company")
            ),
            None,
        )
        if match_idx is None:
            failures.append("experience_not_allowed")
            continue
        spec = remaining_exp.pop(match_idx)
        start = item.get("start_date")
        end = item.get("end_date")
        if start and start != spec.get("start_date"):
            failures.append("experience_date_leak")
        if end and end != spec.get("end_date"):
            failures.append("experience_date_leak")
        allowed_highlights = set(spec.get("highlights") or [])
        for highlight in item.get("highlights") or []:
            if highlight not in allowed_highlights:
                failures.append("experience_highlight_leak")

    remaining_edu = list(manifest["education"])
    for edu in profile.get("education") or []:
        match_idx = next(
            (
                idx
                for idx, spec in enumerate(remaining_edu)
                if spec["institution"] == edu.get("institution")
            ),
            None,
        )
        if match_idx is None:
            failures.append("education_not_allowed")
            continue
        spec = remaining_edu.pop(match_idx)
        for field_name in ("degree", "field", "graduation_year"):
            value = edu.get(field_name)
            if value and value != spec.get(field_name):
                failures.append("education_field_leak")

    for cert in profile.get("certifications") or []:
        if cert not in (manifest.get("certifications") or []):
            failures.append("certification_not_allowed")

    return sorted(set(failures))


def validate_parse_response(payload: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("preferences") is not None:
        failures.append("preferences_not_null")
    candidate = payload.get("candidate") or {}
    stored_id = candidate.get("id")
    if not isinstance(stored_id, str) or not CAND_ID_RE.match(stored_id):
        failures.append("missing_stored_id")
    failures.extend(evaluate_grounded_profile(candidate, manifest))
    return sorted(set(failures))

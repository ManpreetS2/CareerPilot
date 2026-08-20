#!/usr/bin/env python3
"""Manual live Candidate Profile test against a local PDF.

Usage:
  source .venv/bin/activate
  python scripts/test_candidate_profile.py /path/to/resume.pdf

Does not print resume text or API keys. Requires GEMINI_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.database import SessionLocal
from backend.db.init_db import init_db
from backend.services.candidate_profile_agent import build_candidate_profile_from_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Live CareerPilot candidate profile test")
    parser.add_argument("pdf_path", type=Path, help="Path to a local resume PDF (not committed)")
    args = parser.parse_args()

    pdf_path: Path = args.pdf_path
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        return 1

    init_db()
    db = SessionLocal()
    try:
        profile, extraction, report = build_candidate_profile_from_pdf(pdf_path, db=db)
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 2
    finally:
        db.close()

    print(f"filename: {pdf_path.name}")
    print(f"extraction_method: {extraction.method}")
    print(f"candidate_name: {profile.name}")
    print(f"candidate_id: {profile.id}")
    print(f"skills: {len(profile.skills)}")
    print(f"projects: {len(profile.projects)}")
    print(f"experiences: {len(profile.experience)}")
    print(f"education: {len(profile.education)}")
    print(f"certifications: {len(profile.certifications)}")
    print(f"grounding_warnings: {len(report.rejected)}")
    if report.rejected:
        print("rejected_claims:")
        for item in report.rejected[:20]:
            print(f"  - {item}")
        if len(report.rejected) > 20:
            print(f"  … {len(report.rejected) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

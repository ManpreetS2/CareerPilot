"""Day 2 Candidate Profile Agent — integration stubs only.

Human Developer A owns the real implementation. Do not invent candidate facts.
Keep POST /api/parse-resume behavior unchanged until these hooks are wired.
"""

from __future__ import annotations

from pathlib import Path

from backend.schemas.schemas import CandidateProfile


def extract_resume_text(pdf_path: Path) -> str:
    """TODO(Dev A): extract text with pdfplumber; OCR fallback only if nearly empty."""
    raise NotImplementedError("Resume text extraction is owned by Developer A (Day 2).")


def extract_candidate_profile_with_llm(resume_text: str) -> dict:
    """TODO(Dev A): Gemini prompt → strict JSON CandidateProfile fields."""
    raise NotImplementedError("LLM profile extraction is owned by Developer A (Day 2).")


def validate_and_ground_profile(
    raw_profile: dict,
    resume_text: str,
) -> CandidateProfile:
    """TODO(Dev A): Pydantic validate + evidence grounding. Never invent experience."""
    raise NotImplementedError("Profile grounding/validation is owned by Developer A (Day 2).")


def persist_candidate_profile(profile: CandidateProfile) -> CandidateProfile:
    """TODO(Dev A): save grounded CandidateProfile to SQLite and return stored row."""
    raise NotImplementedError("Profile persistence is owned by Developer A (Day 2).")

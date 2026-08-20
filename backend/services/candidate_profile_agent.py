"""Candidate Profile Agent — grounded resume extraction for Day 2.

Pipeline: PDF → text (pdfplumber, OCR fallback) → Gemini JSON →
Pydantic validate → evidence grounding → SQLite persistence.

Never invent candidate facts. Prefer dropping unsupported claims over
preserving hallucinations. Do not log resume contents.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.db.models import Candidate
from backend.schemas.schemas import (
    CandidateProfile,
    Education,
    Experience,
    Project,
)
from backend.services.llm_client import LLMClient, LLMConfigurationError, get_llm_client

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB
NEAR_EMPTY_CHAR_THRESHOLD = 40
FUZZY_RATIO_THRESHOLD = 0.72
TOKEN_COVERAGE_THRESHOLD = 0.6
SHORT_CLAIM_MAX_LEN = 3
ANNUAL_SALARY_MIN = 10_000
ANNUAL_SALARY_MAX = 1_000_000

PROFILE_JSON_SCHEMA_HINT = """
{
  "name": "string",
  "email": "string or null",
  "phone": "string or null",
  "skills": ["string"],
  "projects": [
    {
      "name": "string",
      "description": "string or null",
      "technologies": ["string"],
      "url": "string or null"
    }
  ],
  "experience": [
    {
      "title": "string",
      "company": "string",
      "start_date": "string or null",
      "end_date": "string or null",
      "highlights": ["string"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string or null",
      "field": "string or null",
      "graduation_year": "string or null"
    }
  ],
  "certifications": ["string"],
  "strengths": ["string"],
  "evidence_links": ["string"]
}
""".strip()


class CandidateProfileError(Exception):
    """Base error for candidate profile processing."""


class InvalidResumeError(CandidateProfileError):
    """Upload failed validation (type, size, corruption, empty content)."""


class OversizedResumeError(InvalidResumeError):
    """Upload exceeded the maximum allowed size."""


class ResumeExtractionError(CandidateProfileError):
    """PDF text could not be extracted."""


class OCRUnavailableError(ResumeExtractionError):
    """Scanned PDF needs OCR but Tesseract is not available."""


class ProfileExtractionError(CandidateProfileError):
    """LLM structured extraction failed after controlled retries."""


class ProfileGroundingError(CandidateProfileError):
    """Profile failed validation/grounding in a fatal way (e.g. missing name)."""


@dataclass
class ExtractionResult:
    text: str
    method: str  # "pdfplumber" | "ocr"


@dataclass
class GroundingReport:
    rejected: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.rejected.append(message)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_for_match(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("http://", "").replace("https://", "")
    value = re.sub(r"[^a-z0-9+.#/\s-]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[\s/|,;]+", _normalize_for_match(value)) if len(token) > 1}


def claim_supported(claim: str, source_text: str, *, min_ratio: float = FUZZY_RATIO_THRESHOLD) -> bool:
    """Conservative evidence check: substring, token coverage, or fuzzy window match."""
    claim_n = _normalize_for_match(claim)
    source_n = _normalize_for_match(source_text)
    if not claim_n:
        return False

    # Short skills (C, R, Go, …) require word-boundary style evidence.
    if len(claim_n) <= SHORT_CLAIM_MAX_LEN:
        pattern = rf"(?<![a-z0-9+.#]){re.escape(claim_n)}(?![a-z0-9+.#])"
        return re.search(pattern, source_n) is not None

    if claim_n in source_n:
        return True

    claim_tokens = _tokens(claim)
    if claim_tokens and len(claim_tokens & _tokens(source_text)) / len(claim_tokens) >= TOKEN_COVERAGE_THRESHOLD:
        distinctive = {t for t in claim_tokens if len(t) >= 4}
        if not distinctive or distinctive & _tokens(source_text):
            return True

    window = max(len(claim_n), 8)
    step = max(window // 2, 4)
    best = 0.0
    for idx in range(0, max(len(source_n) - window + 1, 1), step):
        chunk = source_n[idx : idx + window + 8]
        best = max(best, SequenceMatcher(None, claim_n, chunk).ratio())
        if best >= min_ratio:
            return True
    return best >= min_ratio


def is_tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_with_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber

    chunks: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise InvalidResumeError("PDF has no pages.")
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    chunks.append(page_text)
    except InvalidResumeError:
        raise
    except Exception as exc:
        raise ResumeExtractionError(
            "This PDF could not be read. Try exporting it as a new PDF."
        ) from exc
    return normalize_whitespace("\n\n".join(chunks))


def extract_with_ocr(pdf_path: Path) -> str:
    if not is_tesseract_available():
        raise OCRUnavailableError(
            "This appears to be a scanned PDF and requires Tesseract OCR, "
            "which is unavailable on this machine."
        )
    import pdfplumber
    import pytesseract
    from pytesseract import TesseractNotFoundError

    chunks: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise InvalidResumeError("PDF has no pages.")
            for page in pdf.pages:
                image = page.to_image(resolution=200).original
                text = pytesseract.image_to_string(image) or ""
                if text.strip():
                    chunks.append(text)
    except OCRUnavailableError:
        raise
    except InvalidResumeError:
        raise
    except TesseractNotFoundError as exc:
        raise OCRUnavailableError(
            "This appears to be a scanned PDF and requires Tesseract OCR, "
            "which is unavailable on this machine."
        ) from exc
    except Exception as exc:
        raise ResumeExtractionError(
            "No readable resume text was found in this PDF."
        ) from exc

    text = normalize_whitespace("\n\n".join(chunks))
    if len(text) < NEAR_EMPTY_CHAR_THRESHOLD:
        raise ResumeExtractionError(
            "No readable resume text was found in this PDF."
        )
    return text


def extract_resume_text(pdf_path: Path) -> ExtractionResult:
    """Extract resume text with pdfplumber first; OCR only when near-empty."""
    if not pdf_path.exists():
        raise InvalidResumeError("Resume file was not found.")

    text = extract_with_pdfplumber(pdf_path)
    if len(text) >= NEAR_EMPTY_CHAR_THRESHOLD:
        return ExtractionResult(text=text, method="pdfplumber")

    logger.info("pdfplumber extraction near-empty; attempting OCR fallback")
    ocr_text = extract_with_ocr(pdf_path)
    return ExtractionResult(text=ocr_text, method="ocr")


def validate_pdf_upload(
    filename: str | None,
    content: bytes,
    *,
    content_type: str | None = None,
) -> None:
    if not filename or not filename.strip():
        raise InvalidResumeError("Please choose a valid PDF file.")
    lower = filename.lower()
    if not lower.endswith(".pdf"):
        raise InvalidResumeError("Please choose a valid PDF file.")
    if content_type:
        normalized = content_type.split(";")[0].strip().lower()
        if normalized not in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
            raise InvalidResumeError("Please choose a valid PDF file.")
    if not content:
        raise InvalidResumeError("Please choose a valid PDF file.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise OversizedResumeError("Resume PDFs must be 10 MiB or smaller.")
    if not content.startswith(b"%PDF"):
        raise InvalidResumeError("This PDF could not be read. Try exporting it as a new PDF.")


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    # Model sometimes adds prose around a JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_profile_json(raw: str) -> dict[str, Any]:
    cleaned = _strip_code_fences(raw)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProfileExtractionError("Model returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ProfileExtractionError("Model JSON must be an object.")
    payload.pop("id", None)
    return payload


def build_extraction_prompts(resume_text: str) -> tuple[str, str]:
    system_prompt = (
        "You extract factual candidate profile data from resumes. "
        "You do not rewrite resumes, invent experience, or infer unsupported skills. "
        "Return JSON only with no markdown and no commentary."
    )
    user_prompt = f"""Extract a CandidateProfile from the resume text below.

Rules:
- Extract facts only. Do NOT rewrite the resume.
- Return JSON only. No prose preamble or markdown fences.
- Only include facts explicitly supported by the supplied resume.
- Never infer a skill solely because a job/project probably required it.
- Never manufacture dates, metrics, education, certifications, projects, or job titles.
- If a field is absent: use null for nullable scalars and [] for lists.
- Preserve factual wording where practical.
- URLs must originate from the resume text.
- Do not convert vague claims into stronger claims.
- Do not invent an id field.

JSON shape:
{PROFILE_JSON_SCHEMA_HINT}

RESUME TEXT:
\"\"\"
{resume_text}
\"\"\"
"""
    return system_prompt, user_prompt


def extract_candidate_profile_with_llm(
    resume_text: str,
    *,
    llm: LLMClient | None = None,
    generate_fn: Callable[[str, str | None], str] | None = None,
) -> dict[str, Any]:
    """Ask Gemini (or injected generator) for strict CandidateProfile JSON."""
    if not resume_text or not resume_text.strip():
        raise InvalidResumeError("Resume text is empty.")

    system_prompt, user_prompt = build_extraction_prompts(resume_text)

    def _generate(prompt: str, system: str | None) -> str:
        if generate_fn is not None:
            return generate_fn(prompt, system)
        client = llm or get_llm_client("gemini")
        return client.generate(prompt, system_prompt=system)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = _generate(user_prompt if attempt == 0 else _retry_prompt(user_prompt), system_prompt)
            if not raw or not raw.strip():
                raise ProfileExtractionError("Model returned an empty response.")
            return _parse_profile_json(raw)
        except InvalidResumeError:
            raise
        except LLMConfigurationError:
            raise
        except ProfileExtractionError as exc:
            last_error = exc
            logger.warning(
                "candidate LLM extraction attempt %s failed: %s",
                attempt + 1,
                type(exc).__name__,
            )
            continue
        except Exception as exc:  # noqa: BLE001 — provider/network failures become controlled errors
            last_error = ProfileExtractionError(
                "The AI extraction service could not process this resume. Please try again."
            )
            last_error.__cause__ = exc
            logger.warning(
                "candidate LLM extraction attempt %s failed: %s",
                attempt + 1,
                type(exc).__name__,
            )
            continue
    raise ProfileExtractionError(
        "The AI extraction service could not process this resume. Please try again."
    ) from last_error


def _retry_prompt(original: str) -> str:
    return (
        original
        + "\n\nIMPORTANT: Previous output was invalid. Reply with a single raw JSON object only."
    )


def validate_and_ground_profile(
    raw_profile: dict[str, Any],
    resume_text: str,
) -> tuple[CandidateProfile, GroundingReport]:
    """Validate with Pydantic, then drop unsupported optional claims."""
    report = GroundingReport()
    payload = dict(raw_profile)
    payload.pop("id", None)

    try:
        profile = CandidateProfile.model_validate(payload)
    except ValidationError as exc:
        raise ProfileGroundingError("Extracted profile failed schema validation.") from exc

    if not profile.name or not str(profile.name).strip():
        raise ProfileGroundingError(
            "We could not confirm a candidate name from this resume. Please try another PDF export."
        )

    name_ok = claim_supported(profile.name, resume_text, min_ratio=0.55)
    if not name_ok:
        parts = [part for part in re.split(r"[\s,]+", profile.name) if len(part) > 1]
        name_ok = bool(parts) and all(
            claim_supported(part, resume_text, min_ratio=0.8) for part in parts
        )
    if not name_ok:
        raise ProfileGroundingError(
            "We could not confirm a candidate name from this resume. Please try another PDF export."
        )

    if profile.email and not claim_supported(profile.email, resume_text, min_ratio=0.9):
        report.add("Dropped unsupported email")
        profile.email = None

    if profile.phone:
        phone_digits = re.sub(r"\D", "", profile.phone)
        source_digits = re.sub(r"\D", "", resume_text)
        if len(phone_digits) < 7 or phone_digits not in source_digits:
            report.add("Dropped unsupported phone")
            profile.phone = None

    grounded_skills: list[str] = []
    for skill in profile.skills:
        if claim_supported(skill, resume_text):
            grounded_skills.append(skill)
        else:
            report.add(f"Dropped unsupported skill: {skill}")
    profile.skills = grounded_skills

    grounded_projects: list[Project] = []
    for project in profile.projects:
        if not claim_supported(project.name, resume_text):
            report.add(f"Dropped unsupported project: {project.name}")
            continue
        techs = []
        for tech in project.technologies:
            if claim_supported(tech, resume_text):
                techs.append(tech)
            else:
                report.add(f"Dropped unsupported project technology: {tech}")
        description = project.description
        if description and not claim_supported(description, resume_text, min_ratio=0.55):
            # Keep name/techs; drop invented description rather than hallucinate detail.
            report.add(f"Dropped unsupported project description: {project.name}")
            description = None
        url = project.url
        if url and not claim_supported(url, resume_text, min_ratio=0.9):
            report.add(f"Dropped unsupported project URL: {project.name}")
            url = None
        grounded_projects.append(
            Project(name=project.name, description=description, technologies=techs, url=url)
        )
    profile.projects = grounded_projects

    grounded_experience: list[Experience] = []
    for item in profile.experience:
        if not claim_supported(item.company, resume_text) or not claim_supported(item.title, resume_text):
            report.add(f"Dropped unsupported experience: {item.title} @ {item.company}")
            continue
        start = item.start_date
        end = item.end_date
        if start and not claim_supported(start, resume_text, min_ratio=0.8):
            report.add("Dropped unsupported experience start_date")
            start = None
        if end and end.lower() not in {"present", "current", "now"} and not claim_supported(
            end, resume_text, min_ratio=0.8
        ):
            report.add("Dropped unsupported experience end_date")
            end = None
        highlights: list[str] = []
        for highlight in item.highlights:
            if claim_supported(highlight, resume_text, min_ratio=0.55):
                highlights.append(highlight)
            else:
                report.add("Dropped unsupported experience highlight")
        grounded_experience.append(
            Experience(
                title=item.title,
                company=item.company,
                start_date=start,
                end_date=end,
                highlights=highlights,
            )
        )
    profile.experience = grounded_experience

    grounded_education: list[Education] = []
    for edu in profile.education:
        if not claim_supported(edu.institution, resume_text):
            report.add(f"Dropped unsupported education: {edu.institution}")
            continue
        degree = edu.degree
        field = edu.field
        year = edu.graduation_year
        if degree and not claim_supported(degree, resume_text, min_ratio=0.75):
            report.add("Dropped unsupported degree")
            degree = None
        if field and not claim_supported(field, resume_text, min_ratio=0.75):
            report.add("Dropped unsupported field of study")
            field = None
        if year and not claim_supported(year, resume_text, min_ratio=0.9):
            report.add("Dropped unsupported graduation year")
            year = None
        grounded_education.append(
            Education(institution=edu.institution, degree=degree, field=field, graduation_year=year)
        )
    profile.education = grounded_education

    grounded_certs: list[str] = []
    for cert in profile.certifications:
        if claim_supported(cert, resume_text):
            grounded_certs.append(cert)
        else:
            report.add(f"Dropped unsupported certification: {cert}")
    profile.certifications = grounded_certs

    grounded_strengths: list[str] = []
    for strength in profile.strengths:
        if claim_supported(strength, resume_text, min_ratio=0.7):
            grounded_strengths.append(strength)
        else:
            report.add(f"Dropped unsupported strength: {strength}")
    profile.strengths = grounded_strengths

    grounded_links: list[str] = []
    for link in profile.evidence_links:
        if _url_in_resume(link, resume_text):
            grounded_links.append(link)
        else:
            report.add(f"Dropped unsupported evidence link: {link}")
    profile.evidence_links = grounded_links

    logger.info("grounding rejected_claims=%s", len(report.rejected))
    return profile, report


def _url_in_resume(link: str, resume_text: str) -> bool:
    if claim_supported(link, resume_text, min_ratio=0.9):
        return True
    parsed = urlparse(link if "://" in link else f"https://{link}")
    host_path = f"{parsed.netloc}{parsed.path}".rstrip("/")
    return bool(host_path) and claim_supported(host_path, resume_text, min_ratio=0.9)


def persist_candidate_profile(profile: CandidateProfile, db: Session) -> CandidateProfile:
    """Save grounded profile to SQLite and return profile with public id."""
    record = Candidate(
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        skills=list(profile.skills),
        projects=[item.model_dump() for item in profile.projects],
        experience=[item.model_dump() for item in profile.experience],
        education=[item.model_dump() for item in profile.education],
        certifications=list(profile.certifications),
        strengths=list(profile.strengths),
        evidence_links=list(profile.evidence_links),
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        raise
    stored = profile.model_copy(deep=True)
    stored.id = f"cand-{record.id:03d}"
    return stored


def build_candidate_profile_from_pdf(
    pdf_path: Path,
    *,
    db: Session,
    llm: LLMClient | None = None,
    generate_fn: Callable[[str, str | None], str] | None = None,
) -> tuple[CandidateProfile, ExtractionResult, GroundingReport]:
    """Full Day 2 pipeline for a PDF on disk."""
    extraction = extract_resume_text(pdf_path)
    raw = extract_candidate_profile_with_llm(
        extraction.text, llm=llm, generate_fn=generate_fn
    )
    profile, report = validate_and_ground_profile(raw, extraction.text)
    stored = persist_candidate_profile(profile, db)
    return stored, extraction, report


def build_candidate_profile_from_upload(
    filename: str | None,
    content: bytes,
    *,
    db: Session,
    content_type: str | None = None,
    llm: LLMClient | None = None,
    generate_fn: Callable[[str, str | None], str] | None = None,
) -> tuple[CandidateProfile, ExtractionResult, GroundingReport]:
    """Validate upload bytes, process via temp file, always clean up."""
    validate_pdf_upload(filename, content, content_type=content_type)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        return build_candidate_profile_from_pdf(
            tmp_path, db=db, llm=llm, generate_fn=generate_fn
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

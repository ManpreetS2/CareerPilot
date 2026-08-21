"""Form Fill / Assisted Apply Agent.

Fills what can be confidently mapped from an approved application package
onto a real ATS application form, and stops there. No field is guessed —
anything that can't be confidently matched is flagged for the human to fill
in manually rather than left blank or invented. The automation never
reaches a submit action; this agent prepares an application for a human to
review and submit themselves, it does not apply on anyone's behalf.

Runs only against jobs whose application package is already "approved" —
the same review gate the Approval Agent enforces elsewhere. Assisted apply
is downstream of human sign-off, not a way around it.

Supports Greenhouse and Lever, the two platforms named in the project plan.
Field detection tries known selector patterns for each platform first, then
falls back to matching an input by its associated label text — DOM
structure varies across individual postings and neither platform publishes
a stable field-name contract, so a single fixed selector list would miss
real-world variation. Anything neither approach matches gets flagged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from fastapi import HTTPException, status
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import ApplicationPackageRecord, Candidate, FormFillAttemptRecord, JobRecord
from backend.schemas.schemas import FlaggedField, FormFillResult

logger = logging.getLogger(__name__)

_GREENHOUSE_HOSTS = ("greenhouse.io",)
_LEVER_HOSTS = ("lever.co",)

# No real resume file exists on disk once a candidate's PDF has been parsed
# (backend/services/candidate_profile_agent.py extracts text in-memory and
# never persists the upload) — a file-upload field can never be filled
# confidently, so it's always flagged rather than attempted.
_RESUME_UPLOAD_REASON = "Resume file upload — attach your resume manually (no stored file to upload)."


class FormFillError(Exception):
    """Raised for a form-fill failure that should surface as an HTTP error."""


@dataclass
class _CandidateFields:
    full_name: str
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    current_company: str | None
    portfolio_url: str | None
    cover_letter: str | None
    flagged: list[FlaggedField] = field(default_factory=list)


def _navigation_url(job_url: str, platform: str) -> str:
    """The URL that actually contains the application FORM, which for Lever
    is not the posting/description page itself.

    Confirmed by testing against multiple real, currently-open Lever
    postings: the plain posting URL (what job_scout_service stores and what
    shows up in search results) renders zero form fields — Lever only
    mounts the form at "{posting_url}/apply". Greenhouse doesn't have this
    split; the form is present on the posting page itself.
    """
    if platform == "lever" and not job_url.rstrip("/").endswith("/apply"):
        return job_url.rstrip("/") + "/apply"
    return job_url


def detect_ats_platform(url: str) -> str:
    """Return "greenhouse", "lever", or "unsupported" based on the posting host."""
    host = urlparse(url).netloc.lower()
    if any(host == h or host.endswith(f".{h}") for h in _GREENHOUSE_HOSTS):
        return "greenhouse"
    if any(host == h or host.endswith(f".{h}") for h in _LEVER_HOSTS):
        return "lever"
    return "unsupported"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _current_company(candidate: Candidate) -> str | None:
    for entry in candidate.experience or []:
        end_date = (entry.get("end_date") or "").strip().lower()
        if end_date in ("", "present", "current"):
            return entry.get("company") or None
    return None


def _first_url(evidence_links: list[str]) -> str | None:
    for link in evidence_links or []:
        if link.strip().lower().startswith(("http://", "https://")):
            return link.strip()
    return None


def _build_candidate_fields(candidate: Candidate, package: ApplicationPackageRecord) -> _CandidateFields:
    first_name, last_name = _split_name(candidate.name)
    return _CandidateFields(
        full_name=candidate.name,
        first_name=first_name,
        last_name=last_name,
        email=candidate.email,
        phone=candidate.phone,
        current_company=_current_company(candidate),
        portfolio_url=_first_url(candidate.evidence_links),
        cover_letter=package.cover_letter_draft,
    )


def _try_fill_by_selectors(page: Page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            locator.fill(value, timeout=settings.form_fill_timeout_ms)
            return True
        except PlaywrightError:
            continue
    return False


def _try_fill_by_label(page: Page, label_patterns: list[str], value: str) -> bool:
    """Fallback for platforms/postings where a fixed selector list misses:
    find a visible label matching one of the patterns and fill its
    associated input, however that association is made (for/id, or the
    input nested inside the label)."""
    for pattern in label_patterns:
        try:
            label: Locator = page.get_by_label(re.compile(pattern, re.IGNORECASE)).first
            if label.count() == 0:
                continue
            label.fill(value, timeout=settings.form_fill_timeout_ms)
            return True
        except PlaywrightError:
            continue
    return False


def _fill_common_fields(
    page: Page,
    fields: _CandidateFields,
    *,
    name_selectors: list[str],
    first_name_selectors: list[str],
    last_name_selectors: list[str],
    email_selectors: list[str],
    phone_selectors: list[str],
) -> tuple[list[str], list[FlaggedField]]:
    filled: list[str] = []
    flagged: list[FlaggedField] = []

    # Prefer a single full-name field where the platform has one; only fall
    # back to first/last if a combined field isn't present, so a page with
    # both doesn't get double-filled.
    if _try_fill_by_selectors(page, name_selectors, fields.full_name):
        filled.append("full_name")
    else:
        first_ok = fields.first_name and _try_fill_by_selectors(page, first_name_selectors, fields.first_name)
        last_ok = fields.last_name and _try_fill_by_selectors(page, last_name_selectors, fields.last_name)
        if first_ok:
            filled.append("first_name")
        elif not _try_fill_by_label(page, [r"first\s*name"], fields.first_name or ""):
            flagged.append(FlaggedField(field="first_name", reason="No matching name field found on the form."))
        if last_ok:
            filled.append("last_name")
        elif fields.last_name and not _try_fill_by_label(page, [r"last\s*name"], fields.last_name):
            flagged.append(FlaggedField(field="last_name", reason="No matching name field found on the form."))

    if fields.email:
        if _try_fill_by_selectors(page, email_selectors, fields.email) or _try_fill_by_label(
            page, [r"email"], fields.email
        ):
            filled.append("email")
        else:
            flagged.append(FlaggedField(field="email", reason="No matching email field found on the form."))
    else:
        flagged.append(FlaggedField(field="email", reason="Candidate profile has no email on file."))

    if fields.phone:
        if _try_fill_by_selectors(page, phone_selectors, fields.phone) or _try_fill_by_label(
            page, [r"phone"], fields.phone
        ):
            filled.append("phone")
        else:
            flagged.append(FlaggedField(field="phone", reason="No matching phone field found on the form."))

    return filled, flagged


def _fill_greenhouse(page: Page, fields: _CandidateFields) -> tuple[list[str], list[FlaggedField]]:
    filled, flagged = _fill_common_fields(
        page,
        fields,
        name_selectors=["#full_name", "input[name='job_application[full_name]']"],
        first_name_selectors=["#first_name", "input[name='job_application[first_name]']"],
        last_name_selectors=["#last_name", "input[name='job_application[last_name]']"],
        email_selectors=["#email", "input[name='job_application[email]']"],
        phone_selectors=["#phone", "input[name='job_application[phone]']"],
    )

    if fields.current_company:
        if _try_fill_by_selectors(page, ["#company", "input[name='job_application[company]']"], fields.current_company):
            filled.append("current_company")
        elif _try_fill_by_label(page, [r"current\s*company", r"^company$"], fields.current_company):
            filled.append("current_company")

    if fields.cover_letter and _try_fill_by_selectors(page, ["#cover_letter_text", "textarea[name*='cover_letter']"], fields.cover_letter):
        filled.append("cover_letter")
    elif fields.cover_letter:
        flagged.append(
            FlaggedField(field="cover_letter", reason="No cover letter text field found — this posting may require a file upload instead.")
        )

    if page.locator("#resume, input[type='file']").first.count() > 0:
        flagged.append(FlaggedField(field="resume", reason=_RESUME_UPLOAD_REASON))

    _flag_unmatched_required_fields(page, filled, flagged)
    return filled, flagged


def _fill_lever(page: Page, fields: _CandidateFields) -> tuple[list[str], list[FlaggedField]]:
    filled, flagged = _fill_common_fields(
        page,
        fields,
        name_selectors=["input[name='name']"],
        first_name_selectors=[],
        last_name_selectors=[],
        email_selectors=["input[name='email']"],
        phone_selectors=["input[name='phone']"],
    )

    if fields.current_company and _try_fill_by_selectors(page, ["input[name='org']"], fields.current_company):
        filled.append("current_company")

    if fields.portfolio_url:
        for selector in ("input[name='urls[Portfolio]']", "input[name='urls[LinkedIn]']", "input[name='urls[GitHub]']"):
            if _try_fill_by_selectors(page, [selector], fields.portfolio_url):
                filled.append("portfolio_url")
                break

    if fields.cover_letter and _try_fill_by_selectors(page, ["textarea[name='comments']"], fields.cover_letter):
        filled.append("cover_letter")
    elif fields.cover_letter:
        flagged.append(
            FlaggedField(field="cover_letter", reason="No additional-information field found for the cover letter text.")
        )

    if page.locator("input[name='resume']").first.count() > 0:
        flagged.append(FlaggedField(field="resume", reason=_RESUME_UPLOAD_REASON))

    _flag_unmatched_required_fields(page, filled, flagged)
    return filled, flagged


_NEAREST_LABEL_JS = """
el => {
    let node = el;
    for (let i = 0; i < 6 && node; i++) {
        node = node.parentElement;
        if (!node) break;
        const label = node.querySelector('label');
        if (label && label.textContent.trim()) return label.textContent.trim();
    }
    return null;
}
"""


def _has_live_value(locator: Locator) -> bool:
    """Whether a field currently holds a real value — reads the *live*
    value, not the static HTML `value` attribute.

    Confirmed necessary by testing against a real posting: `.fill()`
    updates an input's live value/DOM property (what a user would actually
    see and what gets submitted) but not necessarily its HTML attribute,
    especially on framework-controlled inputs. Checking the attribute
    instead of the live value caused a field this agent had just filled
    (under a different semantic name than its raw HTML `name`, e.g.
    filling "full_name" into an element whose HTML name is "name") to be
    re-flagged as unfilled.
    """
    try:
        return bool((locator.input_value() or "").strip())
    except PlaywrightError:
        pass
    try:
        return locator.is_checked()
    except PlaywrightError:
        return False


def _nearest_label_text(locator: Locator) -> str | None:
    """Walk up from a field to find an ancestor's <label> text.

    Confirmed necessary by testing against a real posting: modern
    Greenhouse forms render custom question widgets (dropdowns, radio
    groups) backed by a hidden `aria-hidden` / `tabindex="-1"` proxy
    <input required> for the framework's own validation — that proxy has
    no name/id/aria-label at all, so without this fallback every custom
    question on a real form would get flagged as an unhelpful "unnamed
    field #N" instead of e.g. "Country" or the actual sponsorship
    question text.
    """
    try:
        text = locator.evaluate(_NEAREST_LABEL_JS)
    except PlaywrightError:
        return None
    if not text:
        return None
    return text.strip().rstrip("*").strip()[:150]


def _flag_unmatched_required_fields(page: Page, filled: list[str], flagged: list[FlaggedField]) -> None:
    """Any field the platform marks required that this agent didn't already
    fill or flag gets flagged too — silently leaving a required field blank
    is exactly the "guessing by omission" this agent is supposed to avoid."""
    already = {f.field for f in flagged} | set(filled)
    try:
        required_inputs = page.locator("input[required], textarea[required], select[required]")
        count = min(required_inputs.count(), 50)  # bounded: never scan an unbounded page
    except PlaywrightError:
        return
    for i in range(count):
        input_el = required_inputs.nth(i)
        try:
            if _has_live_value(input_el):
                # Already has a real value — filled above (matched by a
                # different semantic name than its raw HTML attribute,
                # e.g. this agent's "full_name" filled a field whose HTML
                # name is "name") or pre-filled by the page itself.
                continue
            name = (
                input_el.get_attribute("name")
                or input_el.get_attribute("id")
                or input_el.get_attribute("aria-label")
                or _nearest_label_text(input_el)
                or f"unnamed field #{i + 1}"
            )
        except PlaywrightError:
            continue
        if name in already:
            continue
        flagged.append(FlaggedField(field=name, reason="Required field this agent doesn't have a confident mapping for."))
        already.add(name)


def run_assisted_apply(db: Session, job_id: str) -> FormFillResult:
    job = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")

    package = db.query(ApplicationPackageRecord).filter(ApplicationPackageRecord.job_id == job.id).first()
    if package is None or package.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application must be approved before assisted apply can run.",
        )

    candidate = db.query(Candidate).filter(Candidate.id == package.candidate_id).first() if package.candidate_id else None
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No candidate profile is associated with this application.",
        )

    platform = detect_ats_platform(job.url)
    if platform == "unsupported":
        result = FormFillResult(
            job_id=job_id,
            ats_platform="unsupported",
            status="failed",
            error_message="Only Greenhouse and Lever postings are supported for assisted apply.",
        )
        _persist_attempt(db, job.id, result)
        return result

    fields = _build_candidate_fields(candidate, package)
    filled: list[str] = []
    flagged: list[FlaggedField] = list(fields.flagged)
    error_message: str | None = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=settings.form_fill_headless)
            try:
                page = browser.new_page()
                page.goto(
                    _navigation_url(job.url, platform),
                    timeout=settings.form_fill_timeout_ms,
                    wait_until="domcontentloaded",
                )
                if platform == "greenhouse":
                    run_filled, run_flagged = _fill_greenhouse(page, fields)
                else:
                    run_filled, run_flagged = _fill_lever(page, fields)
                filled.extend(run_filled)
                flagged.extend(run_flagged)
                # Deliberately no submit action anywhere in this function —
                # the browser closes with the form filled but unsent.
            finally:
                browser.close()
    except PlaywrightError as exc:
        logger.warning("Assisted apply failed for %s: %s", job_id, exc)
        error_message = f"Could not load or fill the application form: {exc}"

    if error_message:
        status_value = "failed"
    elif flagged:
        status_value = "needs_review"
    else:
        status_value = "filled"

    result = FormFillResult(
        job_id=job_id,
        ats_platform=platform,  # type: ignore[arg-type]
        status=status_value,  # type: ignore[arg-type]
        filled_fields=filled,
        flagged_fields=flagged,
        error_message=error_message,
    )
    _persist_attempt(db, job.id, result)
    return result


def _persist_attempt(db: Session, job_internal_id: int, result: FormFillResult) -> None:
    record = FormFillAttemptRecord(
        job_id=job_internal_id,
        ats_platform=result.ats_platform,
        status=result.status,
        filled_fields=list(result.filled_fields),
        flagged_fields=[f.model_dump() for f in result.flagged_fields],
        error_message=result.error_message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result.created_at = record.created_at

"""Form Fill / Assisted Apply Agent.

Fills what can be confidently mapped from an approved application package
onto a real ATS application form, and stops there. No field is guessed —
anything that can't be confidently matched is flagged for the human to fill
in manually rather than left blank or invented. The automation never
reaches a submit action; this agent prepares an application for a human to
review and submit themselves, it does not apply on anyone's behalf.

The fill itself runs in a throwaway, isolated headless browser session on
the server — it has no connection to the user's own browser and can't leave
anything filled there. What it hands back is the exact field/value mapping
it determined, so the user can copy it into the real form themselves. (An
earlier version returned only field *names*, which was useless for that —
learned this from watching someone actually try to use it.)

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
from backend.db.models import (
    ApplicationPackageRecord,
    Candidate,
    FormFillAttemptRecord,
    JobRecord,
    TargetPreference,
)
from backend.schemas.schemas import AutofillFields, AutofillResponse, FilledField, FlaggedField, FormFillResult

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
    location: str | None
    legal_name: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    cover_letter: str | None
    work_authorization: str | None
    sponsorship_required: bool | None
    earliest_start_date: str | None
    currently_enrolled_in_program: str | None
    expected_graduation: str | None
    degree_pursuing: str | None
    gender: str | None
    race_ethnicity: str | None
    veteran_status: str | None
    disability_status: str | None
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


def _categorize_urls(evidence_links: list[str]) -> tuple[str | None, str | None, str | None]:
    """Split a candidate's evidence links into (linkedin, github, portfolio).

    ATS platforms generally don't have a single generic "links" field —
    Greenhouse's LinkedIn/GitHub questions are platform-specific (confirmed
    live: they're per-posting custom questions, matched by label text, not
    a stable selector) — so a link needs to be routed to the right target
    field rather than dumped into one generic "portfolio" slot.
    """
    linkedin, github, portfolio = None, None, None
    for raw in evidence_links or []:
        link = raw.strip()
        if not link.lower().startswith(("http://", "https://")):
            continue
        host = urlparse(link).netloc.lower()
        if "linkedin.com" in host:
            if linkedin is None:
                linkedin = link
        elif "github.com" in host:
            if github is None:
                github = link
        elif portfolio is None:
            portfolio = link
    return linkedin, github, portfolio


def _load_target_preference(db: Session, candidate: Candidate) -> TargetPreference | None:
    return (
        db.query(TargetPreference)
        .filter(TargetPreference.candidate_id == candidate.id)
        .order_by(TargetPreference.id.desc())
        .first()
    )


def _build_candidate_fields(
    candidate: Candidate,
    package: ApplicationPackageRecord,
    preference: TargetPreference | None = None,
) -> _CandidateFields:
    """`preference` is the candidate's latest saved TargetPreference row —
    everything reusable across applications lives there. A manually-saved
    linkedin_url/github_url/portfolio_url wins over the resume-grounded
    value from evidence_links when both exist, since a deliberate manual
    answer is more trustworthy than what text-extraction happened to find
    (this also covers resumes where the link is a hyperlink rather than
    printed text, which grounding can never see)."""
    first_name, last_name = _split_name(candidate.name)
    grounded_linkedin, grounded_github, grounded_portfolio = _categorize_urls(candidate.evidence_links)
    location = preference.preferred_locations[0] if preference and preference.preferred_locations else None
    return _CandidateFields(
        full_name=candidate.name,
        first_name=first_name,
        last_name=last_name,
        email=candidate.email,
        phone=candidate.phone,
        current_company=_current_company(candidate),
        location=location,
        legal_name=getattr(preference, "legal_name", None),
        linkedin_url=getattr(preference, "linkedin_url", None) or grounded_linkedin,
        github_url=getattr(preference, "github_url", None) or grounded_github,
        portfolio_url=getattr(preference, "portfolio_url", None) or grounded_portfolio,
        cover_letter=package.cover_letter_draft,
        work_authorization=getattr(preference, "work_authorization", None),
        sponsorship_required=getattr(preference, "sponsorship_required", None),
        earliest_start_date=getattr(preference, "earliest_start_date", None),
        currently_enrolled_in_program=getattr(preference, "currently_enrolled_in_program", None),
        expected_graduation=getattr(preference, "expected_graduation", None),
        degree_pursuing=getattr(preference, "degree_pursuing", None),
        gender=getattr(preference, "gender", None),
        race_ethnicity=getattr(preference, "race_ethnicity", None),
        veteran_status=getattr(preference, "veteran_status", None),
        disability_status=getattr(preference, "disability_status", None),
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


def _try_select_by_label(page: Page, label_patterns: list[str], value: str) -> bool:
    """<select> counterpart to _try_fill_by_label. Tries an exact option
    match first, then a case-insensitive substring match against the
    select's option text (a saved answer like "May 2027" won't always
    match a posting's exact option wording) — returns False rather than
    picking an unconfident option when nothing matches closely enough."""
    for pattern in label_patterns:
        try:
            select: Locator = page.get_by_label(re.compile(pattern, re.IGNORECASE)).first
            if select.count() == 0:
                continue
            try:
                select.select_option(label=value, timeout=settings.form_fill_timeout_ms)
                return True
            except PlaywrightError:
                pass
            # Bidirectional: a saved value can be the more specific side
            # ("Bachelor's in Computer Science" vs. a plain option
            # "Bachelor's") or the option can be more specific ("Yes" vs.
            # an option worded "Yes, I will need sponsorship").
            needle = value.strip().lower()
            option_texts = select.locator("option").all_inner_texts()
            match = next(
                (opt for opt in option_texts if needle in opt.strip().lower() or opt.strip().lower() in needle),
                None,
            )
            if match:
                select.select_option(label=match, timeout=settings.form_fill_timeout_ms)
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
) -> tuple[list[FilledField], list[FlaggedField]]:
    filled: list[FilledField] = []
    flagged: list[FlaggedField] = []

    # Prefer a single full-name field where the platform has one; only fall
    # back to first/last if a combined field isn't present, so a page with
    # both doesn't get double-filled.
    if _try_fill_by_selectors(page, name_selectors, fields.full_name):
        filled.append(FilledField(field="full_name", value=fields.full_name))
    else:
        first_ok = fields.first_name and _try_fill_by_selectors(page, first_name_selectors, fields.first_name)
        last_ok = fields.last_name and _try_fill_by_selectors(page, last_name_selectors, fields.last_name)
        if first_ok:
            filled.append(FilledField(field="first_name", value=fields.first_name))
        elif not _try_fill_by_label(page, [r"first\s*name"], fields.first_name or ""):
            flagged.append(FlaggedField(field="first_name", reason="No matching name field found on the form."))
        elif fields.first_name:
            filled.append(FilledField(field="first_name", value=fields.first_name))
        if last_ok:
            filled.append(FilledField(field="last_name", value=fields.last_name))
        elif fields.last_name and not _try_fill_by_label(page, [r"last\s*name"], fields.last_name):
            flagged.append(FlaggedField(field="last_name", reason="No matching name field found on the form."))
        elif fields.last_name:
            filled.append(FilledField(field="last_name", value=fields.last_name))

    if fields.email:
        if _try_fill_by_selectors(page, email_selectors, fields.email) or _try_fill_by_label(
            page, [r"email"], fields.email
        ):
            filled.append(FilledField(field="email", value=fields.email))
        else:
            flagged.append(FlaggedField(field="email", reason="No matching email field found on the form."))
    else:
        flagged.append(FlaggedField(field="email", reason="Candidate profile has no email on file."))

    if fields.phone:
        if _try_fill_by_selectors(page, phone_selectors, fields.phone) or _try_fill_by_label(
            page, [r"phone"], fields.phone
        ):
            filled.append(FilledField(field="phone", value=fields.phone))
        else:
            flagged.append(FlaggedField(field="phone", reason="No matching phone field found on the form."))

    return filled, flagged


def _fill_shared_reusable_fields(
    page: Page, fields: _CandidateFields, filled: list[FilledField], flagged: list[FlaggedField]
) -> None:
    """Fields with no stable per-platform selector on either Greenhouse or
    Lever — label-text matching is the only approach that works across
    postings, and the label wording these patterns match doesn't depend on
    which ATS renders it, so this is shared rather than duplicated per
    platform.

    Deliberately does NOT include: Country (no reliable source of truth),
    "how did you hear about this job" (subjective/per-posting), essay
    questions, area-of-interest choices, or date-range-specific internship
    availability (would go stale — saved once, wrong for the next posting's
    dates). Also never touches a policy/terms acknowledgment checkbox —
    accepting an agreement stays a deliberate human click on every
    application, never something this agent answers on the candidate's
    behalf.
    """
    if fields.legal_name and _try_fill_by_label(page, [r"legal\s*name"], fields.legal_name):
        filled.append(FilledField(field="legal_name", value=fields.legal_name))

    if fields.earliest_start_date and _try_fill_by_label(
        page, [r"start\s*date", r"available.*start", r"earliest.*start"], fields.earliest_start_date
    ):
        filled.append(FilledField(field="earliest_start_date", value=fields.earliest_start_date))

    if fields.expected_graduation and _try_select_by_label(page, [r"graduat"], fields.expected_graduation):
        filled.append(FilledField(field="expected_graduation", value=fields.expected_graduation))

    if fields.degree_pursuing and _try_select_by_label(page, [r"degree"], fields.degree_pursuing):
        filled.append(FilledField(field="degree_pursuing", value=fields.degree_pursuing))

    if fields.currently_enrolled_in_program and _try_select_by_label(
        page, [r"currently\s*enrolled"], fields.currently_enrolled_in_program
    ):
        filled.append(
            FilledField(field="currently_enrolled_in_program", value=fields.currently_enrolled_in_program)
        )

    if fields.sponsorship_required is not None:
        answer = "Yes" if fields.sponsorship_required else "No"
        if _try_select_by_label(page, [r"sponsorship"], answer):
            filled.append(FilledField(field="sponsorship_required", value=answer))

    for attr, patterns in (
        ("gender", [r"^gender$"]),
        ("race_ethnicity", [r"hispanic", r"latino"]),
        ("veteran_status", [r"veteran"]),
        ("disability_status", [r"disability"]),
    ):
        value = getattr(fields, attr)
        if value and _try_select_by_label(page, patterns, value):
            filled.append(FilledField(field=attr, value=value))


def _fill_greenhouse(page: Page, fields: _CandidateFields) -> tuple[list[FilledField], list[FlaggedField]]:
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
        filled_company = _try_fill_by_selectors(
            page, ["#company", "input[name='job_application[company]']"], fields.current_company
        ) or _try_fill_by_label(page, [r"current\s*company", r"^company$"], fields.current_company)
        if filled_company:
            filled.append(FilledField(field="current_company", value=fields.current_company))

    # Location, LinkedIn, and GitHub have no stable Greenhouse selector —
    # confirmed live these are implemented as per-posting custom questions
    # with opaque auto-generated ids, not first-class fields, so label-text
    # matching is the only approach that works across different postings.
    if fields.location and _try_fill_by_label(page, [r"location.*city", r"^location$"], fields.location):
        filled.append(FilledField(field="location", value=fields.location))
    if fields.linkedin_url and _try_fill_by_label(page, [r"linkedin"], fields.linkedin_url):
        filled.append(FilledField(field="linkedin_url", value=fields.linkedin_url))
    if fields.github_url and _try_fill_by_label(page, [r"github"], fields.github_url):
        filled.append(FilledField(field="github_url", value=fields.github_url))
    if fields.portfolio_url and _try_fill_by_label(page, [r"portfolio", r"website"], fields.portfolio_url):
        filled.append(FilledField(field="portfolio_url", value=fields.portfolio_url))

    if fields.cover_letter and _try_fill_by_selectors(
        page, ["#cover_letter_text", "textarea[name*='cover_letter']"], fields.cover_letter
    ):
        filled.append(FilledField(field="cover_letter", value=fields.cover_letter))
    elif fields.cover_letter:
        flagged.append(
            FlaggedField(
                field="cover_letter",
                reason="No cover letter text field found — this posting may require clicking \"Enter manually\" or a file upload instead.",
            )
        )

    if page.locator("#resume, input[type='file']").first.count() > 0:
        flagged.append(FlaggedField(field="resume", reason=_RESUME_UPLOAD_REASON))

    _fill_shared_reusable_fields(page, fields, filled, flagged)
    _flag_unmatched_required_fields(page, filled, flagged)
    return filled, flagged


def _fill_lever(page: Page, fields: _CandidateFields) -> tuple[list[FilledField], list[FlaggedField]]:
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
        filled.append(FilledField(field="current_company", value=fields.current_company))

    if fields.location and (
        _try_fill_by_selectors(page, ["input[name='location']"], fields.location)
        or _try_fill_by_label(page, [r"location.*city", r"^location$"], fields.location)
    ):
        filled.append(FilledField(field="location", value=fields.location))

    if fields.linkedin_url and (
        _try_fill_by_selectors(page, ["input[name='urls[LinkedIn]']"], fields.linkedin_url)
        or _try_fill_by_label(page, [r"linkedin"], fields.linkedin_url)
    ):
        filled.append(FilledField(field="linkedin_url", value=fields.linkedin_url))

    if fields.github_url and (
        _try_fill_by_selectors(page, ["input[name='urls[GitHub]']"], fields.github_url)
        or _try_fill_by_label(page, [r"github"], fields.github_url)
    ):
        filled.append(FilledField(field="github_url", value=fields.github_url))

    if fields.portfolio_url and (
        _try_fill_by_selectors(page, ["input[name='urls[Portfolio]']"], fields.portfolio_url)
        or _try_fill_by_label(page, [r"portfolio", r"website"], fields.portfolio_url)
    ):
        filled.append(FilledField(field="portfolio_url", value=fields.portfolio_url))

    if fields.cover_letter and _try_fill_by_selectors(page, ["textarea[name='comments']"], fields.cover_letter):
        filled.append(FilledField(field="cover_letter", value=fields.cover_letter))
    elif fields.cover_letter:
        flagged.append(
            FlaggedField(field="cover_letter", reason="No additional-information field found for the cover letter text.")
        )

    if page.locator("input[name='resume']").first.count() > 0:
        flagged.append(FlaggedField(field="resume", reason=_RESUME_UPLOAD_REASON))

    _fill_shared_reusable_fields(page, fields, filled, flagged)
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

    Checkboxes/radios are checked via `.is_checked()` *first*, not as an
    exception fallback: `.input_value()` doesn't raise for them the way the
    original fallback assumed — it happily returns the static HTML `value`
    attribute (defaulting to the string "on" when unset), which is truthy
    regardless of whether the box is actually checked. A required,
    unchecked checkbox was silently never flagged because of this — caught
    by a test asserting a required privacy-policy checkbox gets flagged
    when this agent (correctly) never checks it itself.
    """
    try:
        input_type = (locator.get_attribute("type") or "").lower()
    except PlaywrightError:
        input_type = ""
    if input_type in ("checkbox", "radio"):
        try:
            return locator.is_checked()
        except PlaywrightError:
            return False
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


def _flag_unmatched_required_fields(page: Page, filled: list[FilledField], flagged: list[FlaggedField]) -> None:
    """Any field the platform marks required that this agent didn't already
    fill or flag gets flagged too — silently leaving a required field blank
    is exactly the "guessing by omission" this agent is supposed to avoid."""
    already = {f.field for f in flagged} | {f.field for f in filled}
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


def _load_approved_application(
    db: Session, job: JobRecord, user_id: int
) -> tuple[ApplicationPackageRecord, Candidate]:
    """The same approval + candidate gate both fill paths (server-side
    Playwright preview and the extension's live autofill) require."""
    package = (
        db.query(ApplicationPackageRecord)
        .filter(ApplicationPackageRecord.job_id == job.id, ApplicationPackageRecord.user_id == user_id)
        .first()
    )
    if package is None or package.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application must be approved before assisted apply can run.",
        )

    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No candidate profile is associated with this application.",
        )
    return package, candidate


def _strip_lever_apply_suffix(url: str) -> str:
    trimmed = url.rstrip("/")
    if trimmed.endswith("/apply"):
        return trimmed[: -len("/apply")]
    return trimmed


def find_job_by_url(db: Session, url: str) -> JobRecord | None:
    """Match a real browser tab's URL back to a stored job.

    The extension passes whatever URL the user is actually looking at,
    which for Lever is the .../apply form URL — the stored JobRecord.url is
    always the plain posting URL (what job_scout_service persists), so an
    exact match alone would miss every Lever match.
    """
    candidates = {url, url.rstrip("/"), _strip_lever_apply_suffix(url)}
    for candidate_url in candidates:
        record = db.query(JobRecord).filter(JobRecord.url == candidate_url).first()
        if record is not None:
            return record
    return None


def get_autofill_data(db: Session, url: str, user_id: int) -> AutofillResponse:
    """Field values only, no server-side browser — the extension's content
    script does the actual DOM fill live, in the user's own tab."""
    job = find_job_by_url(db, url)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No job in CareerPilot matches this URL.",
        )

    package, candidate = _load_approved_application(db, job, user_id)
    platform = detect_ats_platform(job.url)
    fields = _build_candidate_fields(candidate, package, _load_target_preference(db, candidate))
    return AutofillResponse(
        job_id=job.public_id,
        platform=platform,  # type: ignore[arg-type]
        fields=AutofillFields(
            full_name=fields.full_name,
            first_name=fields.first_name,
            last_name=fields.last_name,
            email=fields.email,
            phone=fields.phone,
            current_company=fields.current_company,
            location=fields.location,
            legal_name=fields.legal_name,
            linkedin_url=fields.linkedin_url,
            github_url=fields.github_url,
            portfolio_url=fields.portfolio_url,
            cover_letter=fields.cover_letter,
            work_authorization=fields.work_authorization,
            sponsorship_required=fields.sponsorship_required,
            earliest_start_date=fields.earliest_start_date,
            currently_enrolled_in_program=fields.currently_enrolled_in_program,
            expected_graduation=fields.expected_graduation,
            degree_pursuing=fields.degree_pursuing,
            gender=fields.gender,
            race_ethnicity=fields.race_ethnicity,
            veteran_status=fields.veteran_status,
            disability_status=fields.disability_status,
        ),
    )


def run_assisted_apply(db: Session, job_id: str, user_id: int) -> FormFillResult:
    job = db.query(JobRecord).filter(JobRecord.public_id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{job_id}' not found")

    package, candidate = _load_approved_application(db, job, user_id)

    platform = detect_ats_platform(job.url)
    if platform == "unsupported":
        result = FormFillResult(
            job_id=job_id,
            ats_platform="unsupported",
            status="failed",
            error_message="Only Greenhouse and Lever postings are supported for assisted apply.",
        )
        _persist_attempt(db, job.id, user_id, result)
        return result

    fields = _build_candidate_fields(candidate, package, _load_target_preference(db, candidate))
    filled: list[FilledField] = []
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
                # the browser closes with the form filled but unsent. This
                # session has no connection to the user's own browser: the
                # actual values are returned below so they can be copied
                # into the real form the user opens themselves.
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
    _persist_attempt(db, job.id, user_id, result)
    return result


def _persist_attempt(db: Session, job_internal_id: int, user_id: int, result: FormFillResult) -> None:
    record = FormFillAttemptRecord(
        job_id=job_internal_id,
        user_id=user_id,
        ats_platform=result.ats_platform,
        status=result.status,
        filled_fields=[f.model_dump() for f in result.filled_fields],
        flagged_fields=[f.model_dump() for f in result.flagged_fields],
        error_message=result.error_message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result.created_at = record.created_at

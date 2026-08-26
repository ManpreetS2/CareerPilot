"""Deterministic resume-input snapshot and fingerprint.

CareerPilot updates the existing Candidate row when another resume is
uploaded, so candidate_id equality does not prove that an application
package or resume version came from the current resume profile. Grounded
generation stamps a private fingerprint on the package; approval and
resume-version creation compare that fingerprint with the current profile
and fail closed on mismatch or a missing legacy fingerprint.

The snapshot is resume-display data only. It omits salary, work
authorization, gender, race/ethnicity, disability, veteran status, and
other sensitive preference fields. It also omits timestamps and internal
row IDs so hashes are stable.

Future boundary (not implemented here): a later Developer A PR will render
one immutable resume version — using this private snapshot plus the saved
bullets — into PDF/DOCX and return an opaque artifact identifier with an
authenticated download. Developer B may later consume that artifact from
the extension only after the user explicitly selects and approves a
version. The extension must never choose or upload a resume version
automatically.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import ApplicationPackageRecord, Candidate, TargetPreference

RESUME_INPUT_FIELDS = (
    "name",
    "email",
    "phone",
    "skills",
    "projects",
    "experience",
    "education",
    "certifications",
    "strengths",
    "evidence_links",
    "legal_name",
    "linkedin_url",
    "github_url",
    "portfolio_url",
)

_DISPLAY_PREFERENCE_FIELDS = ("legal_name", "linkedin_url", "github_url", "portfolio_url")


def _plain_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def canonical_dumps(value: Any) -> str:
    """Serialize with sorted object keys. List order is preserved as content."""
    return json.dumps(_plain_json(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_string_list(values: list | None) -> list[str]:
    return [str(item) for item in _plain_json(list(values or []))]


def hash_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def hash_resume_input_snapshot(snapshot: dict[str, Any]) -> str:
    return hash_canonical(snapshot)


def hash_approved_materials(bullets: list | None, notes: list | None) -> str:
    return hash_canonical(
        {
            "source_traceability_notes": canonical_string_list(notes),
            "tailored_bullets": canonical_string_list(bullets),
        }
    )


def version_content_hash(snapshot: dict[str, Any], bullets: list | None, notes: list | None) -> str:
    return hash_canonical(
        {
            "resume_input_snapshot": snapshot,
            "source_traceability_notes": canonical_string_list(notes),
            "tailored_bullets": canonical_string_list(bullets),
        }
    )


def _latest_preference(db: Session, candidate: Candidate, user_id: int) -> TargetPreference | None:
    pref = (
        db.query(TargetPreference)
        .filter(TargetPreference.candidate_id == candidate.id)
        .order_by(TargetPreference.id.desc())
        .first()
    )
    if pref is not None:
        return pref
    return (
        db.query(TargetPreference)
        .filter(TargetPreference.user_id == user_id)
        .order_by(TargetPreference.id.desc())
        .first()
    )


def build_resume_input_snapshot(
    db: Session, candidate: Candidate, user_id: int
) -> dict[str, Any]:
    """Return the canonical resume-input dict for hashing and private storage."""
    pref = _latest_preference(db, candidate, user_id)
    snapshot: dict[str, Any] = {
        "name": candidate.name,
        "email": candidate.email,
        "phone": candidate.phone,
        "skills": _plain_json(list(candidate.skills or [])),
        "projects": _plain_json(list(candidate.projects or [])),
        "experience": _plain_json(list(candidate.experience or [])),
        "education": _plain_json(list(candidate.education or [])),
        "certifications": _plain_json(list(candidate.certifications or [])),
        "strengths": _plain_json(list(candidate.strengths or [])),
        "evidence_links": _plain_json(list(candidate.evidence_links or [])),
        "legal_name": None,
        "linkedin_url": None,
        "github_url": None,
        "portfolio_url": None,
    }
    if pref is not None:
        for field in _DISPLAY_PREFERENCE_FIELDS:
            snapshot[field] = getattr(pref, field, None)
    return snapshot


def fingerprint_for_candidate(db: Session, candidate: Candidate, user_id: int) -> str:
    return hash_resume_input_snapshot(build_resume_input_snapshot(db, candidate, user_id))


def current_candidate(db: Session, user_id: int, *, refresh: bool = False) -> Candidate | None:
    query = db.query(Candidate).filter(Candidate.user_id == user_id)
    if refresh:
        query = query.populate_existing()
    return query.first()


def current_resume_input_fingerprint(
    db: Session, user_id: int, *, refresh: bool = False
) -> str | None:
    candidate = current_candidate(db, user_id, refresh=refresh)
    if candidate is None:
        return None
    return fingerprint_for_candidate(db, candidate, user_id)


def package_matches_current_resume_profile(
    db: Session, package: ApplicationPackageRecord | None, user_id: int
) -> bool:
    """True only when a stored fingerprint matches the current resume profile.

    Missing legacy fingerprints are never treated as current.
    """
    if package is None:
        return False
    stored = getattr(package, "candidate_profile_fingerprint", None)
    if not stored:
        return False
    current = current_resume_input_fingerprint(db, user_id)
    if current is None:
        return False
    return stored == current

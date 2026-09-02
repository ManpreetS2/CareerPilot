"""Canonical, deterministic profile readiness for discovery and matching.

CareerPilot must not spend job-provider or AI budget before the authenticated
user has enough grounded profile + job-preference data. This module is the
single source of truth for that contract. No LLM is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from backend.db.models import Candidate, TargetPreference

PROFILE_REQUIRED_CODE = "profile_required"
DEFAULT_NEXT_ROUTE = "/profile"

MISSING_CANDIDATE_PROFILE = "candidate_profile"
MISSING_CANDIDATE_EVIDENCE = "candidate_evidence"
MISSING_TARGET_ROLES = "target_roles"


@dataclass(frozen=True)
class ProfileReadiness:
    ready: bool
    code: str | None
    missing: tuple[str, ...]
    next_route: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "code": self.code,
            "missing": list(self.missing),
            "next_route": self.next_route,
        }


class ProfileNotReadyError(Exception):
    """Raised when profile-dependent work is requested before readiness."""

    def __init__(self, readiness: ProfileReadiness) -> None:
        self.readiness = readiness
        super().__init__("Complete your profile before CareerPilot searches for matches.")


def _as_mapping(item: Any) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        return item
    if hasattr(item, "model_dump"):
        dumped = item.model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    data: dict[str, Any] = {}
    for key in (
        "name",
        "title",
        "company",
        "institution",
        "degree",
        "field",
        "highlights",
        "description",
        "technologies",
    ):
        if hasattr(item, key):
            data[key] = getattr(item, key)
    return data


def _nonempty_strings(values: Sequence[Any] | None) -> bool:
    return any(str(item).strip() for item in (values or []) if item is not None)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def has_usable_candidate_name(candidate: Any) -> bool:
    return bool(str(_attr(candidate, "name") or "").strip())


def _education_evidence(items: Sequence[Any] | None) -> bool:
    for item in items or []:
        data = _as_mapping(item)
        if any(str(data.get(key) or "").strip() for key in ("institution", "degree", "field")):
            return True
    return False


def _experience_evidence(items: Sequence[Any] | None) -> bool:
    for item in items or []:
        data = _as_mapping(item)
        if any(str(data.get(key) or "").strip() for key in ("title", "company")):
            return True
        if _nonempty_strings(data.get("highlights") or []):
            return True
    return False


def _project_evidence(items: Sequence[Any] | None) -> bool:
    for item in items or []:
        data = _as_mapping(item)
        if any(str(data.get(key) or "").strip() for key in ("name", "description")):
            return True
        if _nonempty_strings(data.get("technologies") or []):
            return True
    return False


def has_candidate_evidence(candidate: Any) -> bool:
    """True when at least one grounded evidence category is present."""
    if candidate is None:
        return False
    return (
        _nonempty_strings(_attr(candidate, "skills") or [])
        or _education_evidence(_attr(candidate, "education") or [])
        or _experience_evidence(_attr(candidate, "experience") or [])
        or _project_evidence(_attr(candidate, "projects") or [])
    )


def has_target_roles(preferences: Any) -> bool:
    return _nonempty_strings(_attr(preferences, "target_roles") or [])


def evaluate_candidate_grounding(candidate: Any) -> ProfileReadiness:
    """A+B only: scoring/materials/interview need grounded evidence, not target roles."""
    missing: list[str] = []
    if not has_usable_candidate_name(candidate):
        missing.append(MISSING_CANDIDATE_PROFILE)
    if not has_candidate_evidence(candidate):
        missing.append(MISSING_CANDIDATE_EVIDENCE)
    if missing:
        return ProfileReadiness(
            ready=False,
            code=PROFILE_REQUIRED_CODE,
            missing=tuple(missing),
            next_route=DEFAULT_NEXT_ROUTE,
        )
    return ProfileReadiness(ready=True, code=None, missing=(), next_route=None)


def evaluate_profile_readiness(candidate: Any, preferences: Any) -> ProfileReadiness:
    """Deterministic readiness. Locations/work-mode/opportunity are optional."""
    grounding = evaluate_candidate_grounding(candidate)
    missing = list(grounding.missing)
    if not has_target_roles(preferences):
        missing.append(MISSING_TARGET_ROLES)
    if missing:
        return ProfileReadiness(
            ready=False,
            code=PROFILE_REQUIRED_CODE,
            missing=tuple(missing),
            next_route=DEFAULT_NEXT_ROUTE,
        )
    return ProfileReadiness(ready=True, code=None, missing=(), next_route=None)


def load_user_profile_inputs(
    db: Session, user_id: int
) -> tuple[Candidate | None, TargetPreference | None]:
    candidate = db.query(Candidate).filter(Candidate.user_id == user_id).first()
    preference = (
        db.query(TargetPreference)
        .filter(TargetPreference.user_id == user_id)
        .order_by(TargetPreference.id.desc())
        .first()
    )
    return candidate, preference


def evaluate_user_profile_readiness(db: Session, user_id: int) -> ProfileReadiness:
    candidate, preference = load_user_profile_inputs(db, user_id)
    return evaluate_profile_readiness(candidate, preference)


def evaluate_user_candidate_grounding(db: Session, user_id: int) -> ProfileReadiness:
    candidate, _preference = load_user_profile_inputs(db, user_id)
    return evaluate_candidate_grounding(candidate)


def require_ready_profile(db: Session, user_id: int) -> ProfileReadiness:
    readiness = evaluate_user_profile_readiness(db, user_id)
    if not readiness.ready:
        raise ProfileNotReadyError(readiness)
    return readiness


def require_grounded_candidate(db: Session, user_id: int) -> ProfileReadiness:
    readiness = evaluate_user_candidate_grounding(db, user_id)
    if not readiness.ready:
        raise ProfileNotReadyError(readiness)
    return readiness

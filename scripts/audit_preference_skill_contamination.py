#!/usr/bin/env python3
"""Read-only / opt-in audit for preference skills that polluted Candidate.skills.

Before PR #140, saving TargetPreference.skill_preferences also merged those
strings into Candidate.skills. Fit treats Candidate.skills as resume-grounded
evidence, so preference-only entries could inflate matched skills.

This script never opens data/careerpilot.db unless you pass that path
explicitly. Default mode is dry-run JSON report. --apply removes only
high-confidence preference-only skills (present in skill_preferences, present
in Candidate.skills, and absent from other candidate evidence text). Ambiguous
overlaps require human review and are never deleted automatically.

Usage:
  python scripts/audit_preference_skill_contamination.py --database /tmp/qa.sqlite
  python scripts/audit_preference_skill_contamination.py --database /tmp/qa.sqlite --apply --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.models import Candidate, TargetPreference  # noqa: E402
from backend.services.candidate_provenance import fingerprint_for_candidate  # noqa: E402


@dataclass
class SkillFinding:
    user_id: int | None
    candidate_id: int
    skill: str
    classification: str  # preference_only_suspect | ambiguous_overlap | preference_only_removed
    evidence_hits: list[str]


@dataclass
class AuditReport:
    database: str
    mode: str
    candidates_scanned: int
    preference_only_suspects: list[SkillFinding]
    ambiguous_overlaps: list[SkillFinding]
    removed: list[SkillFinding]
    users_with_removals: list[int]
    note: str


def _normalize(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _as_strings(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = str(item).strip() if item is not None else ""
        if text:
            out.append(text)
    return out


def _evidence_blob(candidate: Candidate) -> str:
    """Serialize non-skills profile fields that can ground a skill claim."""
    chunks: list[str] = []
    for field in (
        candidate.projects,
        candidate.experience,
        candidate.education,
        candidate.certifications,
        candidate.strengths,
        candidate.evidence_links,
    ):
        chunks.append(json.dumps(field or [], ensure_ascii=True))
    return "\n".join(chunks).lower()


def _evidence_hits(skill: str, blob: str) -> list[str]:
    needle = _normalize(skill)
    if not needle:
        return []
    hits: list[str] = []
    if needle in blob:
        hits.append("profile_text")
    compact = needle.replace(" ", "")
    if compact and compact != needle and compact in blob.replace(" ", ""):
        hits.append("profile_text_compact")
    return hits


def _preferences_for_candidate(db: Session, candidate: Candidate) -> list[str]:
    prefs: list[str] = []
    rows = (
        db.query(TargetPreference)
        .filter(
            (TargetPreference.candidate_id == candidate.id)
            | (TargetPreference.user_id == candidate.user_id)
        )
        .all()
    )
    seen: set[str] = set()
    for row in rows:
        for skill in _as_strings(row.skill_preferences):
            key = _normalize(skill)
            if key and key not in seen:
                seen.add(key)
                prefs.append(skill)
    return prefs


def audit_database(db: Session, *, apply: bool = False) -> AuditReport:
    suspects: list[SkillFinding] = []
    ambiguous: list[SkillFinding] = []
    removed: list[SkillFinding] = []
    users_with_removals: list[int] = []
    candidates = db.query(Candidate).order_by(Candidate.id.asc()).all()

    for candidate in candidates:
        skills = _as_strings(candidate.skills)
        prefs = _preferences_for_candidate(db, candidate)
        pref_keys = {_normalize(s) for s in prefs}
        if not skills or not pref_keys:
            continue
        blob = _evidence_blob(candidate)
        keep: list[str] = []
        changed = False
        for skill in skills:
            key = _normalize(skill)
            if key not in pref_keys:
                keep.append(skill)
                continue
            hits = _evidence_hits(skill, blob)
            finding = SkillFinding(
                user_id=candidate.user_id,
                candidate_id=candidate.id,
                skill=skill,
                classification="ambiguous_overlap" if hits else "preference_only_suspect",
                evidence_hits=hits,
            )
            if hits:
                ambiguous.append(finding)
                keep.append(skill)
                continue
            suspects.append(finding)
            if apply:
                changed = True
                removed.append(
                    SkillFinding(
                        user_id=finding.user_id,
                        candidate_id=finding.candidate_id,
                        skill=finding.skill,
                        classification="preference_only_removed",
                        evidence_hits=[],
                    )
                )
            else:
                keep.append(skill)
        if apply and changed:
            candidate.skills = keep
            if candidate.user_id is not None:
                users_with_removals.append(int(candidate.user_id))
                # Skills participate in fingerprint_for_candidate; stored Fit /
                # Evidence rows become stale on the next score path automatically.
                fingerprint_for_candidate(db, candidate, candidate.user_id)
    if apply:
        db.commit()

    return AuditReport(
        database=str(db.get_bind().url),
        mode="apply" if apply else "dry-run",
        candidates_scanned=len(candidates),
        preference_only_suspects=[] if apply else suspects,
        ambiguous_overlaps=ambiguous,
        removed=removed,
        users_with_removals=sorted(set(users_with_removals)),
        note=(
            "Ambiguous overlaps are never deleted automatically. "
            "After --apply, Fit/Evidence recompute via candidate fingerprint mismatch "
            "on the next score path; no MatchScore rows are force-deleted."
        ),
    )


def _refuse_production_apply(path: Path, *, apply: bool, confirm: bool) -> Path:
    resolved = path.expanduser().resolve()
    if apply and resolved == PRODUCTION_DATABASE and not confirm:
        raise SystemExit(
            "Refusing to mutate data/careerpilot.db without --confirm. "
            "Prefer copying with scripts/make_temp_qa_db.py --from <copy> first."
        )
    if apply and not confirm:
        raise SystemExit("--apply requires --confirm after reviewing a dry-run report.")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite path to audit. Use an isolated copy for writes.",
    )
    parser.add_argument("--apply", action="store_true", help="Remove high-confidence preference-only skills.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --apply. Explicit acknowledgement after reviewing dry-run output.",
    )
    args = parser.parse_args(argv)

    db_path = _refuse_production_apply(args.database, apply=args.apply, confirm=args.confirm)
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        report = audit_database(db, apply=args.apply)
    engine.dispose()

    payload = asdict(report)
    payload["database"] = str(db_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

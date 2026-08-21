#!/usr/bin/env python3
"""Idempotently backfill grounded requirements for described stored jobs."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.database import SessionLocal
from backend.db.models import JobIntelligenceRecord, JobRecord
from backend.services.job_intelligence_service import (
    extract_job_intelligence,
    has_usable_posting_evidence,
)

PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()

GenerateFn = Callable[[str, str | None], str]


@dataclass(frozen=True)
class BackfillCounts:
    scanned: int = 0
    eligible: int = 0
    extracted: int = 0
    skipped: int = 0
    failed: int = 0


def assert_safe_database_path(database_path: Path) -> Path:
    """Refuse the production SQLite file during automated or disposable runs."""
    resolved = database_path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise ValueError("Refusing to run backfill against the production database.")
    return resolved


def sqlite_path_from_url(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else (ROOT / path).resolve()


def run_backfill(
    db: Session,
    *,
    generate_fn: GenerateFn | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    reextract: bool = False,
) -> BackfillCounts:
    """Process jobs independently and return privacy-safe aggregate counts."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be zero or greater")

    jobs = db.query(JobRecord).order_by(JobRecord.id.asc()).all()
    eligible = 0
    extracted = 0
    skipped = 0
    failed = 0
    attempted = 0

    for job in jobs:
        if not has_usable_posting_evidence(job):
            skipped += 1
            continue
        exists = (
            db.query(JobIntelligenceRecord.id)
            .filter(JobIntelligenceRecord.job_id == job.id)
            .first()
            is not None
        )
        if exists and not reextract:
            skipped += 1
            continue

        eligible += 1
        if dry_run or (limit is not None and attempted >= limit):
            skipped += 1
            continue

        attempted += 1
        try:
            extract_job_intelligence(
                db,
                job.public_id,
                generate_fn=generate_fn,
            )
        except Exception:  # noqa: BLE001 — one job must not stop the maintenance run
            db.rollback()
            failed += 1
            continue
        extracted += 1

    return BackfillCounts(
        scanned=len(jobs),
        eligible=eligible,
        extracted=extracted,
        skipped=skipped,
        failed=failed,
    )


def format_backfill_counts(counts: BackfillCounts) -> str:
    return (
        f"scanned={counts.scanned} eligible={counts.eligible} "
        f"extracted={counts.extracted} skipped={counts.skipped} failed={counts.failed}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill grounded requirements for stored jobs.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--re-extract", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")

    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with SessionLocal() as db:
            counts = run_backfill(
                db,
                dry_run=args.dry_run,
                limit=args.limit,
                reextract=args.re_extract,
            )
    finally:
        logging.disable(previous_logging_disable)
    print(format_backfill_counts(counts))
    return 1 if counts.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

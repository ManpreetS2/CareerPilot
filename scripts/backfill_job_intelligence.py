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

from backend.core.config import settings
from backend.db.database import SessionLocal
from backend.db.models import JobIntelligenceRecord, JobRecord
from backend.services.job_intelligence_service import (
    extract_job_intelligence_batch,
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


def assert_safe_database_path(
    database_path: Path,
    *,
    dry_run: bool = False,
    confirm: bool = False,
) -> Path:
    """Refuse unconfirmed production writes; dry-run and confirmed writes are allowed."""
    resolved = database_path.expanduser().resolve()
    if resolved != PRODUCTION_DATABASE:
        return resolved
    if dry_run or confirm:
        return resolved
    raise ValueError("Refusing to mutate the production database without --confirm.")


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
    eligible_ids: list[str] = []
    skipped = 0

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
        eligible_ids.append(job.public_id)

    eligible = len(eligible_ids)
    to_run = eligible_ids
    if limit is not None:
        to_run = eligible_ids[:limit]
        skipped += len(eligible_ids) - len(to_run)

    if dry_run:
        skipped += len(to_run)
        return BackfillCounts(
            scanned=len(jobs),
            eligible=eligible,
            extracted=0,
            skipped=skipped,
            failed=0,
        )

    extracted = 0
    failed = 0
    if to_run:
        results = extract_job_intelligence_batch(
            db,
            to_run,
            generate_fn=generate_fn,
            force=reextract,
        )
        from backend.schemas.schemas import JobIntelligence

        for result in results:
            if isinstance(result, JobIntelligence):
                extracted += 1
            else:
                failed += 1

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
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Allow writing to the production database.",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or greater")

    database_path = sqlite_path_from_url(settings.database_url)
    if database_path is not None:
        try:
            assert_safe_database_path(
                database_path,
                dry_run=args.dry_run,
                confirm=args.confirm,
            )
        except ValueError:
            print(f"{format_backfill_counts(BackfillCounts())} result=refused")
            return 2

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

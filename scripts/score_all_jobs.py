#!/usr/bin/env python3
"""Explicit batch scoring. Never imported by the app, tests, CI, or page load.

Counts only. Does not print candidate, job, prompt, or provider content.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import settings
from backend.db.models import JobIntelligenceRecord, JobRecord, MatchScoreRecord

PRODUCTION_SQLITE = (ROOT / "data" / "careerpilot.db").resolve()
logger = logging.getLogger("score_all_jobs")


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    if url.endswith(":memory:") or "mode=memory" in url:
        return None
    raw = url.split(":///", 1)[-1]
    if raw.startswith("/") and not raw.startswith("//"):
        return Path(raw).resolve()
    return (Path.cwd() / raw).resolve()


def _is_production_url(url: str) -> bool:
    path = _sqlite_path(url)
    return path is not None and path == PRODUCTION_SQLITE


def run_batch_scoring(
    *,
    database_url: str,
    dry_run: bool = False,
    limit: int | None = None,
    only_unscored: bool = False,
    status_filter: str | None = None,
    confirm_production: bool = False,
) -> dict[str, int]:
    if _is_production_url(database_url) and not dry_run and not confirm_production:
        logger.info("batch_score refused reason=production_unconfirmed")
        print("refused reason=production_unconfirmed written=0")
        return {
            "selected": 0,
            "scored": 0,
            "skipped_already_scored": 0,
            "skipped_missing_intelligence": 0,
            "failed": 0,
            "written": 0,
            "refused": 1,
        }

    from backend.services.analysis_service import score_job

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    selected = 0
    scored = 0
    skipped_already_scored = 0
    skipped_missing_intelligence = 0
    failed = 0
    try:
        with SessionLocal() as db:
            query = db.query(JobRecord)
            if status_filter:
                query = query.filter(JobRecord.status == status_filter)
            jobs = query.order_by(JobRecord.id.asc()).all()
            if limit is not None:
                jobs = jobs[: max(0, limit)]
            selected = len(jobs)
            for job in jobs:
                has_intelligence = (
                    db.query(JobIntelligenceRecord.id)
                    .filter(JobIntelligenceRecord.job_id == job.id)
                    .first()
                    is not None
                )
                has_score = (
                    db.query(MatchScoreRecord.id).filter(MatchScoreRecord.job_id == job.id).first()
                    is not None
                )
                if only_unscored and has_score:
                    skipped_already_scored += 1
                    continue
                if not has_intelligence:
                    skipped_missing_intelligence += 1
                    continue
                if dry_run:
                    scored += 1
                    continue
                try:
                    score_job(db, job.public_id)
                    scored += 1
                except Exception:
                    db.rollback()
                    failed += 1
                    logger.info("batch_score job_failed job_pk=%s", job.id)
    finally:
        engine.dispose()

    written = 0 if dry_run else scored
    result = {
        "selected": selected,
        "scored": scored,
        "skipped_already_scored": skipped_already_scored,
        "skipped_missing_intelligence": skipped_missing_intelligence,
        "failed": failed,
        "written": written,
        "refused": 0,
        "dry_run": int(dry_run),
    }
    print(
        "selected={selected} scored={scored} skipped_already_scored={skipped_already_scored} "
        "skipped_missing_intelligence={skipped_missing_intelligence} failed={failed} "
        "written={written} dry_run={dry_run}".format(**result)
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score stored jobs using stored Job Intelligence.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-unscored", action="store_true")
    parser.add_argument("--status", dest="status_filter", default=None)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--confirm-production", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = run_batch_scoring(
        database_url=args.database_url,
        dry_run=args.dry_run,
        limit=args.limit,
        only_unscored=args.only_unscored,
        status_filter=args.status_filter,
        confirm_production=args.confirm_production,
    )
    if result.get("refused"):
        return 2
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

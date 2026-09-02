#!/usr/bin/env python3
"""Benchmark bounded parallel Job Intelligence extraction.

Default mode uses a deterministic fake provider. Live provider mode is
opt-in, never used by CI, writes only a temporary database, and never
prints secrets, prompts, or model responses.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _synthetic_description(index: int) -> str:
    return (
        f"Software Engineer role {index}.\n"
        "Requirements:\n"
        "- Python\n"
        "- 2 years of professional experience\n"
        "Preferred:\n"
        "- Docker\n"
        "Responsibilities:\n"
        "- Build APIs.\n"
        "Must be eligible to work in the United States.\n"
        "Bachelor's degree enrollment required.\n"
        "This posting ends with an eligibility clause for work authorization."
    )


def _payload() -> dict:
    return {
        "required_skills": ["Python"],
        "preferred_skills": ["Docker"],
        "years_experience": 2,
        "education_requirements": [],
        "tech_stack": [],
        "seniority": None,
        "responsibilities": ["Build APIs."],
        "likely_interview_focus": [],
    }


def _report(jobs: int, workers: int, wall_s: float, cache_hits: int, failures: int) -> None:
    throughput = jobs / wall_s if wall_s > 0 else 0.0
    print(
        f"jobs={jobs} workers={workers} wall_s={wall_s:.3f} "
        f"throughput={throughput:.2f}/s cache_hits={cache_hits} failures={failures}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--delay-ms", type=int, default=200)
    parser.add_argument("--live", action="store_true", help="Opt-in live provider (never CI).")
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        parser.error("--jobs and --workers must be >= 1")
    if args.delay_ms < 0:
        parser.error("--delay-ms must be >= 0")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.core.config import settings
    from backend.db.database import Base
    from backend.db.models import JobRecord
    from backend.services.extraction_pool import peak_workers_used, reset_extraction_runtime
    from backend.services.job_intelligence_service import extract_job_intelligence_batch
    from backend.schemas.schemas import JobIntelligence

    reset_extraction_runtime()
    settings.job_extraction_max_workers = args.workers

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "benchmark.sqlite"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        delay_s = args.delay_ms / 1000.0
        calls = {"n": 0}

        def fake_generate(prompt: str, system: str | None) -> str:
            del prompt, system
            calls["n"] += 1
            if delay_s:
                time.sleep(delay_s)
            return json.dumps(_payload())

        generate_fn = None if args.live else fake_generate
        try:
            with SessionLocal() as db:
                public_ids: list[str] = []
                for index in range(args.jobs):
                    public_id = f"bench-{index + 1}"
                    db.add(
                        JobRecord(
                            public_id=public_id,
                            title=f"Software Engineer {index + 1}",
                            company="Benchmark Co",
                            location="Remote",
                            url=f"https://example.invalid/jobs/{public_id}",
                            description=_synthetic_description(index),
                            source="test",
                            status="verified",
                        )
                    )
                    public_ids.append(public_id)
                db.commit()
                started = time.perf_counter()
                results = extract_job_intelligence_batch(
                    db,
                    public_ids,
                    generate_fn=generate_fn,
                    force=True,
                )
                wall_s = time.perf_counter() - started
                successes = sum(1 for item in results if isinstance(item, JobIntelligence))
                failures = args.jobs - successes
                cache_hits = args.jobs - calls["n"] if not args.live else 0
                _report(args.jobs, peak_workers_used() or args.workers, wall_s, cache_hits, failures)
                if failures:
                    return 1
        finally:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

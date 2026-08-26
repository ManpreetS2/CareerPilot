#!/usr/bin/env python3
"""Privacy-safe manual Job Intelligence QA using real stored posting
descriptions, following LLM_PROVIDER_ORDER (Ollama-first if configured that
way, not hardcoded to Gemini)."""

from __future__ import annotations

import logging
import re
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import settings
from backend.db.database import Base
from backend.db.models import JobRecord
from backend.services.job_intelligence_service import extract_job_intelligence
from backend.services.llm_client import LLMConfigurationError, LLMProviderError, get_llm_client
from backend.services.llm_provider_sequence import configured_provider_names

MIN_SCENARIOS = 5
MAX_SCENARIOS = 8


@dataclass(frozen=True)
class SourcePosting:
    title: str
    description: str


def _length_bucket(description: str) -> str:
    length = len(description)
    if length < 400:
        return "sparse"
    if length < 1_500:
        return "ordinary"
    return "long"


def _is_mixed(description: str) -> bool:
    return bool(
        re.search(r"\b(?:required|requirements|must have)\b", description, flags=re.I)
        and re.search(r"\b(?:preferred|nice to have|bonus)\b", description, flags=re.I)
    )


def _is_poorly_formatted(description: str) -> bool:
    lines = [line for line in description.splitlines() if line.strip()]
    return len(lines) <= 2 or max((len(line) for line in lines), default=0) > 600


def _select_postings(rows: list[SourcePosting]) -> list[SourcePosting]:
    ordered = sorted(rows, key=lambda row: len(row.description))
    selected: list[SourcePosting] = []

    def add(posting: SourcePosting | None) -> None:
        if posting is not None and posting not in selected:
            selected.append(posting)

    for bucket in ("sparse", "ordinary", "long"):
        add(next((row for row in ordered if _length_bucket(row.description) == bucket), None))
    add(next((row for row in ordered if _is_mixed(row.description)), None))
    add(next((row for row in ordered if _is_poorly_formatted(row.description)), None))

    for posting in ordered:
        add(posting)
        if len(selected) >= MAX_SCENARIOS:
            break
    return selected[:MAX_SCENARIOS]


def _has_required_variety(postings: list[SourcePosting]) -> bool:
    buckets = {_length_bucket(posting.description) for posting in postings}
    return (
        {"sparse", "ordinary", "long"} <= buckets
        and any(_is_mixed(posting.description) for posting in postings)
        and any(_is_poorly_formatted(posting.description) for posting in postings)
    )


def _source_database_path() -> Path | None:
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    path = Path(url.database)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _load_source_postings() -> list[SourcePosting]:
    path = _source_database_path()
    if path is None or not path.exists():
        return []
    uri = f"file:{quote(str(path))}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            """
            SELECT title, description
            FROM jobs
            WHERE trim(coalesce(title, '')) <> ''
              AND trim(coalesce(description, '')) <> ''
            ORDER BY id
            """
        ).fetchall()
    return [
        SourcePosting(title=str(title), description=str(description))
        for title, description in rows
    ]


def _counts_line(scenario: int, bucket: str, intelligence) -> str:
    return (
        f"scenario={scenario} length={bucket} "
        f"required={len(intelligence.required_skills)} "
        f"preferred={len(intelligence.preferred_skills)} "
        f"stack={len(intelligence.tech_stack)} "
        f"years={int(intelligence.years_experience is not None)} "
        f"education={len(intelligence.education_requirements)} "
        f"seniority={int(intelligence.seniority is not None)} "
        f"responsibilities={len(intelligence.responsibilities)} "
        f"focus={len(intelligence.likely_interview_focus)} "
        "status=extracted result=pass"
    )


def _first_configured_provider() -> str | None:
    """Return the first LLM_PROVIDER_ORDER entry that is actually usable."""
    for name in configured_provider_names():
        try:
            get_llm_client(name)
        except LLMConfigurationError:
            continue
        return name
    return None


def _final_result(
    *,
    failed: int,
    provider_blocked: bool,
    validation_failed: bool,
) -> tuple[str, int]:
    if validation_failed:
        return "fail", 1
    if provider_blocked:
        return "blocked", 2
    return ("pass", 0) if failed == 0 else ("fail", 1)


def main() -> int:
    if _first_configured_provider() is None:
        print("scenarios=0 status=blocked reason=configuration result=blocked")
        return 2

    selected = _select_postings(_load_source_postings())
    if len(selected) < MIN_SCENARIOS:
        print(
            f"scenarios={len(selected)} status=blocked "
            "reason=insufficient_descriptions result=blocked"
        )
        return 2
    if not _has_required_variety(selected):
        print(
            f"scenarios={len(selected)} status=blocked "
            "reason=insufficient_variety result=blocked"
        )
        return 2

    passed = 0
    failed = 0
    attempted = 0
    provider_blocked = False
    validation_failed = False
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with tempfile.TemporaryDirectory(prefix="careerpilot-real-description-qa-") as temp_dir:
            database_path = Path(temp_dir) / "qa.sqlite"
            engine = create_engine(
                f"sqlite:///{database_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
            Base.metadata.create_all(bind=engine)
            try:
                with Session(engine) as db:
                    for index, posting in enumerate(selected, start=1):
                        attempted += 1
                        job = JobRecord(
                            public_id=f"qa-job-{index:02d}",
                            title=posting.title,
                            company="Anonymous QA Source",
                            location=None,
                            salary=None,
                            url=f"https://example.invalid/qa/{index}",
                            description=posting.description,
                            source="manual-qa",
                            status="discovered",
                        )
                        db.add(job)
                        db.commit()
                        try:
                            intelligence = extract_job_intelligence(db, job.public_id)
                        except LLMConfigurationError:
                            print(
                                f"scenario={index} length={_length_bucket(posting.description)} "
                                "categories=0 status=configuration result=fail"
                            )
                            failed += 1
                            provider_blocked = True
                            break
                        except LLMProviderError:
                            print(
                                f"scenario={index} length={_length_bucket(posting.description)} "
                                "categories=0 status=provider result=fail"
                            )
                            failed += 1
                            provider_blocked = True
                            break
                        except Exception:
                            print(
                                f"scenario={index} length={_length_bucket(posting.description)} "
                                "categories=0 status=validation result=fail"
                            )
                            failed += 1
                            validation_failed = True
                            continue
                        print(_counts_line(index, _length_bucket(posting.description), intelligence))
                        passed += 1
            finally:
                engine.dispose()
    finally:
        logging.disable(previous_logging_disable)

    result, exit_code = _final_result(
        failed=failed,
        provider_blocked=provider_blocked,
        validation_failed=validation_failed,
    )
    print(
        f"scenarios={attempted} passed={passed} failed={failed} "
        f"result={result}"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

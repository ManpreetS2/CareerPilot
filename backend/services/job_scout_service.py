"""Day 2 Job Scout — integration stubs only.

Human Developer B owns Adzuna/RemoteOK/manual URL ingestion, normalization,
deduplication, and SQLite persistence. Keep GET/POST job routes mocked until wired.
"""

from __future__ import annotations

from backend.schemas.schemas import Job


def scout_adzuna(query: str, location: str | None = None) -> list[dict]:
    """TODO(Dev B): call Adzuna (or chosen free source) and return raw listings."""
    raise NotImplementedError("Adzuna integration is owned by Developer B (Day 2).")


def scout_remoteok(query: str | None = None) -> list[dict]:
    """TODO(Dev B): optionally pull RemoteOK listings."""
    raise NotImplementedError("RemoteOK integration is owned by Developer B (Day 2).")


def ingest_job_url(url: str) -> dict:
    """TODO(Dev B): fetch/parse a single job posting URL into a raw record."""
    raise NotImplementedError("Manual job URL ingestion is owned by Developer B (Day 2).")


def normalize_job(raw: dict, source: str) -> Job:
    """TODO(Dev B): map provider payloads into the shared Job schema."""
    raise NotImplementedError("Job normalization is owned by Developer B (Day 2).")


def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    """TODO(Dev B): dedupe by URL / company+title+location fingerprint."""
    raise NotImplementedError("Job deduplication is owned by Developer B (Day 2).")


def persist_jobs(jobs: list[Job]) -> list[Job]:
    """TODO(Dev B): upsert normalized jobs into SQLite and return stored records."""
    raise NotImplementedError("Job persistence is owned by Developer B (Day 2).")

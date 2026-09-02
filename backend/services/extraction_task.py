"""Immutable posting snapshot for provider-backed extraction workers.

Workers must never receive a SQLAlchemy Session or a live ORM graph.
"""

from __future__ import annotations

from dataclasses import dataclass


INTELLIGENCE_EXTRACTION_VERSION = 1


@dataclass(frozen=True)
class ExtractionTask:
    kind: str
    job_public_id: str
    job_pk: int
    source_fingerprint: str
    extraction_version: int
    title: str
    company: str
    description: str
    content_status: str | None

    @property
    def public_id(self) -> str:
        return self.job_public_id

    @property
    def id(self) -> int:
        return self.job_pk

    @property
    def cache_key(self) -> str:
        return (
            f"{self.kind}:{self.job_pk}:{self.source_fingerprint}:"
            f"{self.extraction_version}"
        )

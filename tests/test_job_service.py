"""job_service.record_to_job tests. Constructs JobRecord instances directly
(no DB session needed — record_to_job only reads Python attributes)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.db.models import JobRecord
from backend.services.job_service import record_to_job


def _record(**overrides) -> JobRecord:
    defaults = dict(
        public_id="manual-abc123",
        title="Software Engineer Intern",
        company="Acme",
        location=None,
        salary=None,
        url="https://example.com/jobs/1",
        description="Build things.",
        source="manual",
        date_posted=None,
        date_scraped=datetime.now(timezone.utc),
        ats=None,
        status="discovered",
        verification_notes=None,
        verified_at=None,
    )
    defaults.update(overrides)
    return JobRecord(**defaults)


def test_record_to_job_passes_through_valid_status() -> None:
    job = record_to_job(_record(status="verified"))
    assert job.status == "verified"


def test_record_to_job_coalesces_out_of_domain_status_to_flagged() -> None:
    job = record_to_job(_record(status="some-future-status-not-yet-known"))
    assert job.status == "flagged"

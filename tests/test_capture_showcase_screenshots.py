"""Showcase screenshot capture: loopback + synthetic identity only."""

from __future__ import annotations

import pytest

from scripts.capture_showcase_screenshots import (
    LOOPBACK_REJECT_MESSAGE,
    extract_jobs_from_payload,
    require_showcase_identity,
    require_showcase_job_id,
    validate_loopback_base_url,
)
from scripts.seed_showcase_demo import (
    SHOWCASE_COMPANY_PRIMARY,
    SHOWCASE_COMPANY_SECOND,
    SHOWCASE_EMAIL,
    SHOWCASE_NAME,
    SHOWCASE_PRIMARY_JOB,
    SHOWCASE_SECOND_JOB,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://localhost",
        "http://localhost:5174",
        "http://[::1]",
        "http://[::1]:5173",
        "http://127.0.0.1/",
        "http://localhost:8000/",
    ],
)
def test_accepts_loopback_http_urls(url: str) -> None:
    normalized = validate_loopback_base_url(url)
    assert normalized.startswith("http://")
    assert "127.0.0.1" in normalized or "localhost" in normalized or "[::1]" in normalized


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:5173",
        "https://example.com",
        "http://example.com",
        "http://192.168.1.10:5173",
        "http://10.0.0.8:5173",
        "http://172.16.0.4:5173",
        "http://172.31.255.1:5173",
        "http://host.example.ts.net",
        "http://device.ts.net:5173",
        "http://8.8.8.8:5173",
        "http://careerpilot.example",
        "file:///tmp/index.html",
        "javascript:alert(1)",
        "http://127.0.0.1:5173/login",
        "http://127.0.0.1:5173/?next=http://evil.example",
        "http://127.0.0.1:5173#/jobs",
        "http://user:pass@127.0.0.1:5173",
        "http://127.0.0.1:5173@evil.example",
        "http://127.0.0.1.evil.example",
        "http://localhost.evil.example",
        "http://[::ffff:127.0.0.1]:5173",
        "http://0.0.0.0:5173",
        "ftp://127.0.0.1:5173",
        "http://127.0.0.1:99999",
        " http://127.0.0.1:5173",
        "http://127.0.0.1:5173 ",
    ],
)
def test_rejects_non_loopback_and_unsafe_urls(url: str) -> None:
    with pytest.raises(SystemExit, match="loopback"):
        validate_loopback_base_url(url)


def test_job_id_must_be_synthetic_primary() -> None:
    assert require_showcase_job_id(SHOWCASE_PRIMARY_JOB) == SHOWCASE_PRIMARY_JOB
    with pytest.raises(SystemExit, match="synthetic job"):
        require_showcase_job_id("some-other-job")


def test_identity_requires_showcase_markers() -> None:
    require_showcase_identity(
        email=SHOWCASE_EMAIL,
        name=SHOWCASE_NAME,
        job_ids={SHOWCASE_PRIMARY_JOB, SHOWCASE_SECOND_JOB},
        companies={SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND},
    )


def test_identity_rejects_other_email() -> None:
    with pytest.raises(SystemExit, match="authenticated email"):
        require_showcase_identity(
            email="real.user@example.com",
            name=SHOWCASE_NAME,
            job_ids={SHOWCASE_PRIMARY_JOB, SHOWCASE_SECOND_JOB},
            companies={SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND},
        )


def test_identity_rejects_missing_synthetic_jobs() -> None:
    with pytest.raises(SystemExit, match="showcase jobs"):
        require_showcase_identity(
            email=SHOWCASE_EMAIL,
            name=SHOWCASE_NAME,
            job_ids={"unrelated-job"},
            companies={SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND},
        )


def test_extract_jobs_from_query_payload() -> None:
    ids, companies = extract_jobs_from_payload(
        {
            "items": [
                {"job": {"id": SHOWCASE_PRIMARY_JOB, "company": SHOWCASE_COMPANY_PRIMARY}},
                {"job": {"id": SHOWCASE_SECOND_JOB, "company": SHOWCASE_COMPANY_SECOND}},
            ]
        }
    )
    assert ids == {SHOWCASE_PRIMARY_JOB, SHOWCASE_SECOND_JOB}
    assert companies == {SHOWCASE_COMPANY_PRIMARY, SHOWCASE_COMPANY_SECOND}


def test_loopback_reject_message_is_explicit() -> None:
    assert "127.0.0.1" in LOOPBACK_REJECT_MESSAGE
    assert "localhost" in LOOPBACK_REJECT_MESSAGE

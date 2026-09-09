#!/usr/bin/env python3
"""Capture desktop showcase screenshots for the isolated synthetic dataset.

Designed only for the isolated synthetic showcase dataset. The script restricts
capture to loopback and verifies the seeded showcase identity before authenticated
screenshots. It does not click Submit. It does not fill EEO fields.

This is not a generic “capture any account” tool. It logs in only as the
synthetic showcase user from scripts/seed_showcase_demo.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from scripts.seed_showcase_demo import (
    SHOWCASE_COMPANY_PRIMARY,
    SHOWCASE_COMPANY_SECOND,
    SHOWCASE_EMAIL,
    SHOWCASE_NAME,
    SHOWCASE_PASSWORD,
    SHOWCASE_PRIMARY_JOB,
    SHOWCASE_SECOND_JOB,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "showcase" / "screenshots"
FIXTURE = ROOT / "docs" / "showcase" / "fixtures" / "generic-ats-form.html"
MOCK_SCREENSHOT = "08-assisted-fill-boundary-mock.png"
ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOOPBACK_REJECT_MESSAGE = (
    "Showcase capture accepts only loopback http://127.0.0.1, "
    "http://localhost, or http://[::1]."
)


def validate_loopback_base_url(raw: str) -> str:
    """Accept only loopback HTTP origins. Fail closed on anything else."""
    if not isinstance(raw, str) or not raw or any(ch.isspace() for ch in raw):
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    lowered = raw.strip().lower()
    if lowered.startswith(("javascript:", "data:", "file:", "vbscript:", "https:")):
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    parsed = urlparse(raw)
    if parsed.scheme != "http":
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    if parsed.query or parsed.fragment:
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    if parsed.path not in ("", "/"):
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit(LOOPBACK_REJECT_MESSAGE) from exc
    if port is not None and not (1 <= port <= 65535):
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_LOOPBACK_HOSTS:
        raise SystemExit(LOOPBACK_REJECT_MESSAGE)
    host_out = "[::1]" if host == "::1" else host
    if port:
        return f"http://{host_out}:{port}"
    return f"http://{host_out}"


def require_showcase_job_id(job_id: str) -> str:
    if job_id != SHOWCASE_PRIMARY_JOB:
        raise SystemExit(
            "Showcase capture is locked to the synthetic job "
            f"{SHOWCASE_PRIMARY_JOB}."
        )
    return job_id


def _path_without_query(url: str) -> str:
    return url.split("?", 1)[0]


def extract_jobs_from_payload(payload: object) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    companies: set[str] = set()
    rows: list[object]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        rows = payload["items"]
    elif isinstance(payload, list):
        rows = payload
    else:
        return ids, companies
    for row in rows:
        job = row
        if isinstance(row, dict) and isinstance(row.get("job"), dict):
            job = row["job"]
        if not isinstance(job, dict):
            continue
        job_id = job.get("id") or job.get("public_id")
        company = job.get("company")
        if isinstance(job_id, str) and job_id:
            ids.add(job_id)
        if isinstance(company, str) and company:
            companies.add(company)
    return ids, companies


def require_showcase_identity(
    *,
    email: str | None,
    name: str | None,
    job_ids: set[str],
    companies: set[str],
) -> None:
    if email != SHOWCASE_EMAIL:
        raise SystemExit(
            "Showcase capture refused: authenticated email is not the synthetic showcase account."
        )
    if name != SHOWCASE_NAME:
        raise SystemExit(
            "Showcase capture refused: candidate name is not the synthetic showcase identity."
        )
    if SHOWCASE_PRIMARY_JOB not in job_ids or SHOWCASE_SECOND_JOB not in job_ids:
        raise SystemExit(
            "Showcase capture refused: synthetic showcase jobs were not present."
        )
    if SHOWCASE_COMPANY_PRIMARY not in companies or SHOWCASE_COMPANY_SECOND not in companies:
        raise SystemExit(
            "Showcase capture refused: synthetic showcase companies were not present."
        )


def _record_identity_payloads(page, collected: dict[str, object]) -> None:
    def on_response(response) -> None:
        path = _path_without_query(response.url)
        if not response.ok:
            return
        try:
            payload = response.json()
        except Exception:
            return
        if path.endswith("/api/auth/me"):
            collected["me"] = payload
        elif path.endswith("/api/profile"):
            collected["profile"] = payload
        elif path.endswith("/api/jobs/query") or path.endswith("/api/jobs"):
            collected["jobs"] = payload

    page.on("response", on_response)


def _identity_from_collected(collected: dict[str, object]) -> tuple[str | None, str | None, set[str], set[str]]:
    me = collected.get("me") if isinstance(collected.get("me"), dict) else {}
    profile = collected.get("profile") if isinstance(collected.get("profile"), dict) else {}
    email = me.get("email") if isinstance(me, dict) else None
    candidate = profile.get("candidate") if isinstance(profile, dict) else None
    name = candidate.get("name") if isinstance(candidate, dict) else None
    job_ids, companies = extract_jobs_from_payload(collected.get("jobs"))
    return (
        email if isinstance(email, str) else None,
        name if isinstance(name, str) else None,
        job_ids,
        companies,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--job-id", default=SHOWCASE_PRIMARY_JOB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    base = validate_loopback_base_url(args.base_url)
    job_id = require_showcase_job_id(args.job_id)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": args.width, "height": args.height})
        page = context.new_page()
        page.emulate_media(reduced_motion="reduce")
        collected: dict[str, object] = {}
        _record_identity_payloads(page, collected)

        page.goto(f"{base}/privacy", wait_until="networkidle")
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "01-landing.png"), full_page=False)

        page.goto(f"{base}/login", wait_until="networkidle")
        page.get_by_label("Email").fill(SHOWCASE_EMAIL)
        page.get_by_label("Password").fill(SHOWCASE_PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_function("() => !location.pathname.includes('/login')", timeout=20000)

        page.goto(f"{base}/profile", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.goto(f"{base}/jobs", wait_until="networkidle")
        page.wait_for_timeout(600)
        email, name, job_ids, companies = _identity_from_collected(collected)
        require_showcase_identity(email=email, name=name, job_ids=job_ids, companies=companies)
        if page.locator(f"[title='{SHOWCASE_EMAIL}']").count() == 0:
            raise SystemExit("Showcase capture refused: UI session is not the synthetic showcase account.")

        page.goto(f"{base}/profile", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "02-profile-readiness.png"), full_page=False)

        page.goto(f"{base}/jobs", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "03-discover.png"), full_page=False)

        page.goto(f"{base}/jobs/{job_id}", wait_until="networkidle")
        page.get_by_role("tab", name="Evidence").click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / "04-match-evidence.png"), full_page=False)

        page.goto(f"{base}/jobs/{job_id}/prepare", wait_until="networkidle")
        page.wait_for_timeout(400)
        approval = page.get_by_test_id("approval-rail")
        if approval.count():
            approval.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
        page.screenshot(path=str(out / "05-prepare.png"), full_page=False)

        page.goto(f"{base}/track", wait_until="networkidle")
        page.get_by_role("button", name="List").click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "06-track.png"), full_page=False)

        page.goto(f"{base}/analytics", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "06b-analytics.png"), full_page=False)

        page.goto(f"{base}/growth", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "07-career-growth.png"), full_page=False)

        page.goto(FIXTURE.resolve().as_uri(), wait_until="networkidle")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out / MOCK_SCREENSHOT), full_page=False)

        browser.close()
    print(f"Wrote screenshots to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

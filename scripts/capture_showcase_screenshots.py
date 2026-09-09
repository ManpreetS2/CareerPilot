#!/usr/bin/env python3
"""Capture desktop showcase screenshots against a seeded isolated database.

Requires a running frontend and backend. Does not use data/careerpilot.db.
Does not click Submit. Does not fill EEO fields.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "showcase" / "screenshots"
FIXTURE = ROOT / "docs" / "showcase" / "fixtures" / "generic-ats-form.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--job-id", default="showcase-harborline-intern")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.emulate_media(reduced_motion="reduce")

        page.goto(f"{args.base_url}/privacy", wait_until="networkidle")
        page.goto(f"{args.base_url}/", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "01-landing.png"), full_page=False)

        page.goto(f"{args.base_url}/login", wait_until="networkidle")
        page.get_by_label("Email").fill(args.email)
        page.get_by_label("Password").fill(args.password)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_function("() => !location.pathname.includes('/login')", timeout=20000)

        page.goto(f"{args.base_url}/profile", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "02-profile-readiness.png"), full_page=False)

        page.goto(f"{args.base_url}/jobs", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out / "03-discover.png"), full_page=False)

        page.goto(f"{args.base_url}/jobs/{args.job_id}", wait_until="networkidle")
        page.get_by_role("tab", name="Evidence").click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / "04-match-evidence.png"), full_page=False)

        page.goto(f"{args.base_url}/jobs/{args.job_id}/prepare", wait_until="networkidle")
        page.wait_for_timeout(400)
        approval = page.get_by_test_id("approval-rail")
        if approval.count():
            approval.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
        page.screenshot(path=str(out / "05-prepare.png"), full_page=False)

        page.goto(f"{args.base_url}/track", wait_until="networkidle")
        page.get_by_role("button", name="List").click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "06-track.png"), full_page=False)

        page.goto(f"{args.base_url}/analytics", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "06b-analytics.png"), full_page=False)

        page.goto(f"{args.base_url}/growth", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "07-career-growth.png"), full_page=False)

        page.goto(FIXTURE.resolve().as_uri(), wait_until="networkidle")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out / "08-extension-fill.png"), full_page=False)

        browser.close()
    print(f"Wrote screenshots to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

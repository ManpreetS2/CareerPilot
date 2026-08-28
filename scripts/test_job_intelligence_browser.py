#!/usr/bin/env python3
"""Chromium verification for explicit grounded requirement extraction."""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_url(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Local test service did not become ready.")


def _npm_bin() -> str:
    found = shutil.which("npm") or shutil.which("npm.cmd")
    if not found:
        raise RuntimeError("npm is not on PATH. Install Node.js 20+ and retry.")
    return found


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        print("browser_checks=0 result=blocked reason=playwright_unavailable")
        return 2

    with tempfile.TemporaryDirectory(prefix="careerpilot-intelligence-browser-") as temp_dir:
        database_path = Path(temp_dir) / "requirements.sqlite"
        if database_path.resolve() == (ROOT / "data" / "careerpilot.db").resolve():
            raise RuntimeError("Refusing to use the production database.")
        backend_port = _free_port()
        frontend_port = _free_port()
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
        # The backend runs in-process below (imports backend.main directly,
        # not a subprocess), so settings reads this from the same
        # os.environ. Every mutating request made once a session cookie
        # exists is checked against this list by OriginCSRFMiddleware —
        # without it matching this run's actual dynamic frontend port, every
        # authenticated POST here (Calculate fit, Extract, Re-verify) is
        # rejected with "Invalid request origin," which is what this line
        # fixes rather than a bug in that middleware.
        os.environ["ALLOWED_ORIGINS"] = f"http://127.0.0.1:{frontend_port}"

        import uvicorn
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from backend.db.database import Base
        from backend.db.models import (
            Candidate,
            JobIntelligenceRecord,
            JobRecord,
            MatchScoreRecord,
            User,
        )
        from backend.main import app
        from backend.services import job_intelligence_service

        engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        job_id = "browser-grounded-requirements"
        candidate_email = "intelligence-browser@example.com"
        candidate_password = "intelligence-browser-password-1"
        description = (
            "Requirements:\n"
            "Python\n"
            "Terraform\n"
            "4 years of professional experience\n"
            "Bachelor's degree in Computer Science\n"
            "Preferred:\n"
            "PostgreSQL\n"
            "Technology stack:\n"
            "Docker\n"
            "Responsibilities:\n"
            "Improve API latency by 20%.\n"
            "Interview topics:\n"
            "Distributed systems"
        )
        with Session(engine) as session:
            session.add(
                JobRecord(
                    public_id=job_id,
                    title="Senior Platform Engineer",
                    company="Fictional Meridian Systems",
                    location=None,
                    salary=None,
                    url=f"http://127.0.0.1:{backend_port}/health",
                    description=description,
                    source="browser",
                    status="verified",
                    verification_notes="Stored verification result.",
                    verified_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

        def _seed_candidate_for(email: str) -> None:
            # Every route the rest of this script exercises requires an
            # authenticated session (ProtectedRoute redirects anonymous
            # visitors to /login), so the candidate profile must be attached
            # to whichever user actually signs up in the browser below,
            # not created ahead of time with no owner.
            with Session(engine) as session:
                user = session.query(User).filter(User.email == email).one()
                session.add(
                    Candidate(
                        user_id=user.id,
                        name="Synthetic Browser Candidate",
                        skills=["Python", "Terraform", "PostgreSQL", "Docker"],
                        projects=[],
                        experience=[
                            {
                                "title": "Platform Engineer",
                                "company": "Fictional Harbor Labs",
                                "start_date": "2020-01-01",
                                "end_date": "Present",
                                "highlights": ["Worked with Python and Terraform."],
                            }
                        ],
                        education=[
                            {
                                "institution": "Fictional Lakeside University",
                                "degree": "Bachelor's degree",
                                "field": "Computer Science",
                                "graduation_year": "2019",
                            }
                        ],
                        certifications=[],
                        strengths=[],
                        evidence_links=[],
                    )
                )
                session.commit()

        response_payload = {
            "job_id": None,
            "required_skills": ["Python", "Terraform"],
            "preferred_skills": ["PostgreSQL"],
            "years_experience": 4,
            "education_requirements": ["Bachelor's degree in Computer Science"],
            "tech_stack": ["Docker"],
            "seniority": "Senior",
            "responsibilities": ["Improve API latency by 20%."],
            "likely_interview_focus": ["Distributed systems"],
        }

        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, _prompt: str, system_prompt: str | None = None) -> str:
                del system_prompt
                self.calls += 1
                if self.calls == 1:
                    return json.dumps(response_payload)
                replacement = dict(response_payload)
                replacement["required_skills"] = ["Python"]
                replacement["preferred_skills"] = []
                replacement["years_experience"] = None
                replacement["education_requirements"] = []
                replacement["tech_stack"] = ["Docker"]
                replacement["responsibilities"] = []
                replacement["likely_interview_focus"] = []
                return json.dumps(replacement)

        fake_client = FakeClient()
        job_intelligence_service.get_llm_client = lambda _provider=None: fake_client

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=backend_port,
            log_level="critical",
        )
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}"
        frontend = subprocess.Popen(
            [
                _npm_bin(),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
            ],
            cwd=ROOT / "frontend",
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        intelligence_gets: list[str] = []
        intelligence_posts: list[str] = []
        score_posts: list[str] = []
        checks = 0
        previous_logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            server_thread.start()
            _wait_for_url(f"http://127.0.0.1:{backend_port}/health")
            _wait_for_url(f"http://127.0.0.1:{frontend_port}/")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--disable-web-security"],
                )
                page = browser.new_page()

                def _track_request(request) -> None:
                    if request.method == "GET" and request.url.endswith("/intelligence"):
                        intelligence_gets.append(request.url)
                    if request.method != "POST":
                        return
                    if request.url.endswith("/intelligence"):
                        intelligence_posts.append(request.url)
                    if request.url.endswith("/score"):
                        score_posts.append(request.url)

                page.on("request", _track_request)

                page.goto(f"http://127.0.0.1:{frontend_port}/signup")
                page.locator('input[type="email"]').fill(candidate_email)
                page.locator('input[type="password"]').fill(candidate_password)
                page.get_by_role("button", name="Sign up").click()
                page.wait_for_url("**/onboarding")
                _seed_candidate_for(candidate_email)

                job_url = f"http://127.0.0.1:{frontend_port}/jobs/{job_id}"
                page.goto(job_url)
                expect(page.get_by_role("heading", name="Senior Platform Engineer")).to_be_visible()
                expect(page.get_by_role("heading", name="Verification")).to_be_visible()
                expect(page.get_by_role("heading", name="Extracted requirements")).to_be_visible()
                checks += 3
                if intelligence_posts or score_posts:
                    raise AssertionError("Page load triggered a write request.")
                if len(intelligence_gets) != 1:
                    raise AssertionError("Page load did not read stored requirements exactly once.")
                checks += 1
                expect(
                    page.get_by_text("Requirements have not been extracted for this job.")
                ).to_be_visible()
                checks += 1
                intelligence_region = page.get_by_role(
                    "region",
                    name="Extracted requirements",
                )

                extract_button = page.get_by_role("button", name="Extract requirements")
                page.get_by_role("tab", name="Match").click()
                fit_button = page.get_by_role("button", name="Calculate fit")
                extract_button.evaluate(
                    """(button) => {
                      window.__extractButtonWasDisabledDuringScoring = button.disabled;
                      new MutationObserver(() => {
                        if (button.disabled) {
                          window.__extractButtonWasDisabledDuringScoring = true;
                        }
                      }).observe(button, { attributes: true, attributeFilter: ["disabled"] });
                    }"""
                )

                def _delay_score_post(route) -> None:
                    if route.request.method == "POST":
                        time.sleep(0.2)
                    route.continue_()

                page.route("**/api/jobs/*/score", _delay_score_post)
                fit_button.evaluate(
                    """(button) => {
                      window.__fitButtonWasDisabled = button.disabled;
                      new MutationObserver(() => {
                        if (button.disabled) window.__fitButtonWasDisabled = true;
                      }).observe(button, { attributes: true, attributeFilter: ["disabled"] });
                      button.click();
                      button.click();
                    }"""
                )
                expect(intelligence_region.get_by_role("heading", name="Required skills")).to_be_visible()
                expect(intelligence_region.get_by_text("Terraform", exact=True)).to_be_visible()
                expect(intelligence_region.get_by_role("heading", name="Preferred skills")).to_be_visible()
                expect(intelligence_region.get_by_role("heading", name="Technology stack")).to_be_visible()
                expect(intelligence_region.get_by_text("Experience requirement:", exact=False)).to_be_visible()
                expect(intelligence_region.get_by_role("heading", name="Education requirements")).to_be_visible()
                expect(intelligence_region.get_by_text("Seniority:", exact=False)).to_be_visible()
                expect(intelligence_region.get_by_role("heading", name="Responsibilities")).to_be_visible()
                expect(intelligence_region.get_by_role("heading", name="Likely interview focus")).to_be_visible()
                expect(page.get_by_text("full Job Intelligence", exact=False).first).to_be_visible()
                checks += 10
                if intelligence_posts or len(score_posts) != 1:
                    raise AssertionError("Calculate fit did not issue exactly one score request.")
                if len(intelligence_gets) != 2:
                    raise AssertionError("Scoring did not refresh stored requirements.")
                if not page.evaluate("window.__fitButtonWasDisabled"):
                    raise AssertionError("Fit action was not disabled while pending.")
                if not page.evaluate("window.__extractButtonWasDisabledDuringScoring"):
                    raise AssertionError("Extraction stayed enabled during scoring.")
                if fake_client.calls != 1:
                    raise AssertionError("Scoring did not extract requirements exactly once.")
                with Session(engine) as session:
                    if session.query(JobIntelligenceRecord).count() != 1:
                        raise AssertionError("Scoring did not persist one intelligence row.")
                    if session.query(MatchScoreRecord).count() != 1:
                        raise AssertionError("Scoring did not persist one score row.")
                checks += 3
                page.unroute("**/api/jobs/*/score", _delay_score_post)

                page.reload()
                intelligence_region = page.get_by_role("region", name="Extracted requirements")
                expect(intelligence_region.get_by_role("heading", name="Required skills")).to_be_visible()
                if intelligence_posts or len(score_posts) != 1:
                    raise AssertionError("Refresh regenerated requirements or calculated fit.")
                checks += 1

                page.get_by_role("tab", name="Match").click()
                with page.expect_request(
                    lambda request: request.method == "GET"
                    and request.url.rstrip("/").endswith("/intelligence")
                ):
                    page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_text("full Job Intelligence", exact=False).first).to_be_visible()
                if len(score_posts) != 2 or fake_client.calls != 1:
                    raise AssertionError("Repeat scoring regenerated stored requirements.")
                checks += 1

                def _delay_intelligence_post(route) -> None:
                    if route.request.method == "POST":
                        time.sleep(0.2)
                    route.continue_()

                page.route("**/api/jobs/*/intelligence", _delay_intelligence_post)
                reextract_button = page.get_by_role("button", name="Re-extract requirements")
                reextract_button.evaluate(
                    """(button) => {
                      button.click();
                      button.click();
                    }"""
                )
                expect(reextract_button).to_be_enabled()
                expect(intelligence_region.get_by_role("heading", name="Required skills")).to_be_visible()
                expect(intelligence_region.get_by_text("Terraform", exact=True)).to_have_count(0)
                expect(page.get_by_text("No fit score yet.", exact=False)).to_be_visible()
                with Session(engine) as session:
                    if session.query(JobIntelligenceRecord).count() != 1:
                        raise AssertionError("Re-extraction created a duplicate row.")
                    stored = session.query(JobIntelligenceRecord).one()
                    if stored.required_skills != ["Python"]:
                        raise AssertionError("Re-extraction did not replace the stored requirements.")
                    if session.query(MatchScoreRecord).count() != 1:
                        raise AssertionError("Fit calculation did not persist one score row.")
                if len(intelligence_posts) != 1 or fake_client.calls != 2:
                    raise AssertionError("Re-extraction did not issue one request.")
                checks += 1

                page.unroute("**/api/jobs/*/intelligence", _delay_intelligence_post)
                page.get_by_role("button", name="Re-verify").click()
                expect(page.get_by_role("button", name="Re-verify")).to_be_visible()
                expect(page.get_by_text("Current status:", exact=False)).to_be_visible()
                checks += 1

                page.route(
                    "**/api/jobs/*/intelligence",
                    lambda route: route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"Unable to save extracted job requirements."}',
                    )
                    if route.request.method == "POST"
                    else route.continue_(),
                )
                page.get_by_role("button", name="Re-extract requirements").click()
                expect(intelligence_region.get_by_role("alert")).to_contain_text(
                    "Unable to save extracted job requirements."
                )
                expect(page.get_by_role("heading", name="Verification")).to_be_visible()
                checks += 1

                page.route(
                    "**/api/jobs/*/verify",
                    lambda route: route.fulfill(
                        status=500,
                        content_type="application/json",
                        body='{"detail":"Unable to verify job."}',
                    ),
                )
                page.get_by_role("button", name="Re-verify").click()
                expect(page.get_by_role("alert").filter(has_text="Unable to verify job.")).to_be_visible()
                expect(intelligence_region.get_by_role("alert")).to_contain_text(
                    "Unable to save extracted job requirements."
                )
                checks += 1
                browser.close()
        finally:
            _stop_process(frontend)
            server.should_exit = True
            server_thread.join(timeout=5)
            engine.dispose()
            logging.disable(previous_logging_disable)

        print(
            f"browser_checks={checks} intelligence_gets={len(intelligence_gets)} "
            f"intelligence_posts={len(intelligence_posts)} "
            f"score_posts={len(score_posts)} result=pass"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

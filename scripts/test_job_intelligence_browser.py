#!/usr/bin/env python3
"""Chromium verification for explicit grounded requirement extraction."""

from __future__ import annotations

import json
import logging
import os
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

        import uvicorn
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from backend.db.database import Base
        from backend.db.models import (
            Candidate,
            JobIntelligenceRecord,
            JobRecord,
            MatchScoreRecord,
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
                Candidate(
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
                "npm",
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
                job_url = f"http://127.0.0.1:{frontend_port}/jobs/{job_id}"
                page.goto(job_url)
                expect(page.get_by_role("heading", name="Senior Platform Engineer")).to_be_visible()
                expect(page.get_by_role("heading", name="Verification")).to_be_visible()
                expect(page.get_by_role("heading", name="Job overview")).to_be_visible()
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

                def _delay_intelligence_post(route) -> None:
                    if route.request.method == "POST":
                        time.sleep(0.2)
                    route.continue_()

                page.route("**/api/jobs/*/intelligence", _delay_intelligence_post)
                extract_button = page.get_by_role("button", name="Extract requirements")
                fit_button = page.get_by_role("button", name="Calculate fit")
                fit_button.evaluate(
                    """(button) => {
                      window.__fitButtonWasDisabledDuringExtraction = button.disabled;
                      new MutationObserver(() => {
                        if (button.disabled) {
                          window.__fitButtonWasDisabledDuringExtraction = true;
                        }
                      }).observe(button, { attributes: true, attributeFilter: ["disabled"] });
                    }"""
                )
                extract_button.evaluate(
                    """(button) => {
                      window.__extractButtonWasDisabled = button.disabled;
                      new MutationObserver(() => {
                        if (button.disabled) window.__extractButtonWasDisabled = true;
                      }).observe(button, { attributes: true, attributeFilter: ["disabled"] });
                      button.click();
                      button.click();
                    }"""
                )
                expect(page.get_by_role("heading", name="Required skills")).to_be_visible()
                expect(page.get_by_text("Terraform", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="Preferred skills")).to_be_visible()
                expect(page.get_by_role("heading", name="Technology stack")).to_be_visible()
                expect(page.get_by_text("Experience requirement:", exact=False)).to_be_visible()
                expect(page.get_by_role("heading", name="Education requirements")).to_be_visible()
                expect(page.get_by_text("Seniority:", exact=False)).to_be_visible()
                expect(page.get_by_role("heading", name="Responsibilities")).to_be_visible()
                expect(page.get_by_role("heading", name="Likely interview focus")).to_be_visible()
                checks += 9
                if len(intelligence_posts) != 1 or score_posts:
                    raise AssertionError("Extraction did not issue exactly one write request.")
                if not page.evaluate("window.__extractButtonWasDisabled"):
                    raise AssertionError("Extraction button was not disabled while pending.")
                if not page.evaluate("window.__fitButtonWasDisabledDuringExtraction"):
                    raise AssertionError("Fit action stayed enabled during extraction.")
                with Session(engine) as session:
                    if session.query(JobIntelligenceRecord).count() != 1:
                        raise AssertionError("Extraction did not persist exactly one row.")
                checks += 2

                page.reload()
                expect(page.get_by_role("heading", name="Required skills")).to_be_visible()
                if len(intelligence_posts) != 1 or score_posts or len(intelligence_gets) != 2:
                    raise AssertionError("Refresh regenerated requirements or calculated fit.")
                checks += 1

                page.get_by_role("button", name="Calculate fit").click()
                expect(page.get_by_text("full Job Intelligence", exact=False)).to_be_visible()
                if len(score_posts) != 1:
                    raise AssertionError("Calculate fit did not issue exactly one score request.")
                checks += 1

                reextract_button = page.get_by_role("button", name="Re-extract requirements")
                reextract_button.click()
                expect(reextract_button).to_be_enabled()
                expect(page.get_by_role("heading", name="Required skills")).to_be_visible()
                expect(page.get_by_text("Terraform", exact=True)).to_have_count(0)
                expect(page.get_by_text("No fit score yet.", exact=False)).to_be_visible()
                with Session(engine) as session:
                    if session.query(JobIntelligenceRecord).count() != 1:
                        raise AssertionError("Re-extraction created a duplicate row.")
                    stored = session.query(JobIntelligenceRecord).one()
                    if stored.required_skills != ["Python"]:
                        raise AssertionError("Re-extraction did not replace the stored requirements.")
                    if session.query(MatchScoreRecord).count() != 1:
                        raise AssertionError("Fit calculation did not persist one score row.")
                if len(intelligence_posts) != 2:
                    raise AssertionError("Re-extraction did not issue one request.")
                checks += 1

                page.unroute("**/api/jobs/*/intelligence", _delay_intelligence_post)
                page.get_by_role("button", name="Re-verify").click()
                expect(page.get_by_role("button", name="Re-verify")).to_be_visible()
                expect(page.get_by_text("Current status:", exact=False)).to_be_visible()
                checks += 1

                intelligence_region = page.get_by_role(
                    "region",
                    name="Extracted requirements",
                )
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

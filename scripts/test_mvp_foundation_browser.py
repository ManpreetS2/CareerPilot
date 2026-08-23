#!/usr/bin/env python3
"""Privacy-safe Playwright workflow for MVP dashboard, tracker, and interview prep.

Uses a temporary SQLite database, unique local ports, fake/no providers, and
count-only output. Never touches data/careerpilot.db.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import Base
from backend.db.models import (
    ApplicationTrackerRecord,
    Candidate,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    TargetPreference,
)

PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()
JOB_PUBLIC_ID = "mvp-browser-job"
JOB_TITLE = "Synthetic Browser Engineer"
JOB_COMPANY = "Fictional Browser Works"
_FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


def assert_safe_database_path(database_path: Path) -> Path:
    resolved = database_path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise ValueError("Refusing to run the MVP browser workflow against the production database.")
    if resolved.suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Browser workflow database must be a dedicated SQLite file.")
    return resolved


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_url(url: str, timeout: float = 45.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:  # noqa: BLE001 - readiness retry
            time.sleep(0.2)
    raise RuntimeError("Local test service did not become ready.")


def _stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _python_bin() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return sys.executable


def _metric(page: Any, label: str) -> str:
    return page.locator("dt", has_text=re.compile(rf"^{re.escape(label)}$")).locator(
        "xpath=following-sibling::dd"
    )


def _is_local(url: str, backend_port: int, frontend_port: int) -> bool:
    allowed = (
        f"127.0.0.1:{backend_port}",
        f"localhost:{backend_port}",
        f"127.0.0.1:{frontend_port}",
        f"localhost:{frontend_port}",
        "ws://127.0.0.1",
        "ws://localhost",
    )
    if url.startswith(("data:", "blob:", "about:", "chrome://", "devtools://")):
        return True
    return any(token in url for token in allowed)


def _is_stylesheet_font(url: str) -> bool:
    return any(host in url for host in _FONT_HOSTS)


def _seed(session: Session, *, tracker_status: str = "saved") -> None:
    candidate = Candidate(
        name="Synthetic Browser Candidate",
        email="browser@example.invalid",
        skills=["Python"],
        projects=[{"name": "Synthetic Planner", "description": "Python app", "technologies": ["Python"]}],
        experience=[
            {
                "title": "Intern",
                "company": "Fictional Harbor Labs",
                "highlights": ["Wrote Python tests."],
            }
        ],
        education=[{"institution": "Fictional Lakeside University", "degree": "B.S."}],
        certifications=[],
        strengths=["Backend"],
        evidence_links=[],
    )
    session.add(candidate)
    session.flush()
    session.add(
        TargetPreference(
            candidate_id=candidate.id,
            target_roles=["Software Engineer"],
            preferred_locations=["Remote"],
        )
    )
    job = JobRecord(
        public_id=JOB_PUBLIC_ID,
        title=JOB_TITLE,
        company=JOB_COMPANY,
        location=None,
        salary=None,
        url="http://127.0.0.1/health",
        description="Required: Python.",
        source="manual",
        status="verified",
        verification_notes="Synthetic posting passed verification.",
        verified_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()
    session.add(
        JobIntelligenceRecord(
            job_id=job.id,
            required_skills=["Python"],
            preferred_skills=[],
            years_experience=None,
            education_requirements=[],
            tech_stack=["Python"],
            seniority="mid",
            responsibilities=["Build APIs"],
            likely_interview_focus=["Python fundamentals"],
        )
    )
    session.add(ApplicationTrackerRecord(job_id=job.id, status=tracker_status))
    session.commit()


def run_browser_workflow() -> dict[str, int]:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError as exc:  # pragma: no cover - tooling blocker
        raise RuntimeError("Python Playwright is unavailable.") from exc

    with tempfile.TemporaryDirectory(prefix="careerpilot-mvp-browser-") as temp_dir:
        database_path = assert_safe_database_path(Path(temp_dir) / "mvp-browser.sqlite")
        backend_port = _free_port()
        frontend_port = _free_port()
        engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

        backend_env = os.environ.copy()
        backend_env["DATABASE_URL"] = f"sqlite:///{database_path}"
        backend_env["GEMINI_API_KEY"] = ""
        backend_env["ANTHROPIC_API_KEY"] = ""
        backend_env["OPENAI_API_KEY"] = ""
        backend_env["ADZUNA_APP_ID"] = ""
        backend_env["ADZUNA_APP_KEY"] = ""
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}"
        backend = subprocess.Popen(
            [
                _python_bin(),
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            cwd=ROOT,
            env=backend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        checks = 0
        patch_calls: list[str] = []
        interview_posts: list[str] = []
        interview_gets: list[str] = []
        blocked_external: list[str] = []
        try:
            _wait_for_url(f"http://127.0.0.1:{backend_port}/health")
            _wait_for_url(f"http://127.0.0.1:{frontend_port}/")
            with sync_playwright() as playwright:
                executable = (
                    Path("/usr/bin/google-chrome")
                    if Path("/usr/bin/google-chrome").exists()
                    else None
                )
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=str(executable) if executable else None,
                    args=["--disable-web-security"],
                )
                page = browser.new_page()

                def _route(route: Any) -> None:
                    url = route.request.url
                    if _is_local(url, backend_port, frontend_port):
                        route.continue_()
                        return
                    if _is_stylesheet_font(url):
                        route.abort()
                        return
                    blocked_external.append(url)
                    route.abort()

                page.route("**/*", _route)

                def _track(request: Any) -> None:
                    url = request.url
                    method = request.method
                    if method == "PATCH" and "/tracking" in url:
                        patch_calls.append(url)
                    if method == "POST" and url.rstrip("/").endswith("/prepare-interview"):
                        interview_posts.append(url)
                    if method == "GET" and url.rstrip("/").endswith("/interview-prep"):
                        interview_gets.append(url)

                page.on("request", _track)
                base = f"http://127.0.0.1:{frontend_port}"

                page.goto(f"{base}/dashboard")
                expect(page.get_by_role("heading", name="Find the right jobs", exact=False)).to_be_visible()
                expect(_metric(page, "Discovered")).to_have_text("0")
                expect(_metric(page, "Interviews")).to_have_text("0")
                checks += 1

                with SessionLocal() as session:
                    _seed(session)

                page.reload()
                expect(_metric(page, "Discovered")).to_have_text("1")
                expect(_metric(page, "Verified")).to_have_text("1")
                expect(_metric(page, "Interviews")).to_have_text("0")
                checks += 1

                before_patches = len(patch_calls)
                before_posts = len(interview_posts)
                page.goto(f"{base}/applications")
                expect(page.get_by_role("heading", name=JOB_TITLE)).to_be_visible()
                if len(patch_calls) != before_patches:
                    raise AssertionError("Applications list load issued a tracker PATCH.")
                if len(interview_posts) != before_posts:
                    raise AssertionError("Applications list load issued an interview POST.")
                checks += 1

                select = page.get_by_label(f"Tracking status for {JOB_TITLE} at {JOB_COMPANY}")
                option_values = select.evaluate(
                    "el => Array.from(el.options).map(option => option.value)"
                )
                if "applied" in option_values:
                    raise AssertionError("Invalid saved -> applied transition was offered.")
                if "pending_review" not in option_values:
                    raise AssertionError("Valid saved -> pending_review transition was missing.")
                checks += 1

                select.select_option("pending_review")
                expect(select).to_have_value("pending_review")
                if len(patch_calls) != before_patches + 1:
                    raise AssertionError("Valid tracker selection did not issue exactly one PATCH.")
                page.reload()
                expect(page.get_by_label(f"Tracking status for {JOB_TITLE} at {JOB_COMPANY}")).to_have_value(
                    "pending_review"
                )
                if len(patch_calls) != before_patches + 1:
                    raise AssertionError("Applications refresh issued another tracker PATCH.")
                checks += 1

                page.get_by_role("link", name="Open application").click()
                expect(page).to_have_url(re.compile(rf"/applications/{JOB_PUBLIC_ID}$"))
                checks += 1

                before_interview_posts = len(interview_posts)
                before_interview_gets = len(interview_gets)
                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}")
                expect(page.get_by_role("heading", name=JOB_TITLE)).to_be_visible()
                expect(page.get_by_text("No interview prep stored yet.")).to_be_visible()
                expect(page.get_by_text("Loading interview prep")).to_have_count(0)
                if len(interview_posts) != before_interview_posts:
                    raise AssertionError("Job Detail load issued an interview POST.")
                if len(interview_gets) < before_interview_gets + 1:
                    raise AssertionError("Job Detail load did not GET stored interview prep.")
                checks += 1

                page.get_by_role("button", name="Prepare interview").click()
                expect(page.get_by_text("What would you expect to discuss about Python fundamentals for this role?", exact=True)).to_be_visible()
                expect(page.get_by_text("How would you demonstrate Python for this role?", exact=True)).to_be_visible()
                if len(interview_posts) != before_interview_posts + 1:
                    raise AssertionError("Prepare Interview did not issue exactly one POST.")
                page.reload()
                expect(page.get_by_text("How would you demonstrate Python for this role?", exact=True)).to_be_visible()
                if len(interview_posts) != before_interview_posts + 1:
                    raise AssertionError("Job Detail refresh issued another interview POST.")
                checks += 1

                page.goto(f"{base}/dashboard")
                expect(_metric(page, "Interviews")).to_have_text("0")
                with SessionLocal() as session:
                    prep_count = session.query(InterviewPrepRecord).count()
                    tracker = session.query(ApplicationTrackerRecord).one()
                    if prep_count != 1:
                        raise AssertionError("Interview prep was not stored once.")
                    if tracker.status != "pending_review":
                        raise AssertionError("Interview prep mutated tracker status.")
                checks += 1

                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}")
                expect(page.get_by_text("Loading interview prep")).to_have_count(0)
                expect(page.get_by_role("alert")).to_have_count(0)
                expect(page.get_by_text("How would you demonstrate Python for this role?", exact=True)).to_be_visible()
                checks += 1

                if blocked_external:
                    unique = sorted(set(blocked_external))
                    raise AssertionError(
                        "Provider or external network requests were attempted count="
                        + str(len(unique))
                    )
                browser.close()
            return {
                "checks": checks,
                "tracker_patches": len(patch_calls),
                "interview_posts": len(interview_posts),
                "interview_gets": len(interview_gets),
                "external_requests": len(blocked_external),
            }
        finally:
            _stop_process(frontend)
            _stop_process(backend)
            engine.dispose()
            database_path.unlink(missing_ok=True)


def main() -> int:
    result = run_browser_workflow()
    print(
        "mvp_browser_checks={checks} tracker_patches={tracker_patches} "
        "interview_posts={interview_posts} interview_gets={interview_gets} "
        "external_requests={external_requests} result=pass".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

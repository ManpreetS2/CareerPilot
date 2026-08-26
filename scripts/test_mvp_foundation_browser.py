#!/usr/bin/env python3
"""Privacy-safe Playwright workflow for authenticated multi-user MVP.

Uses a temporary SQLite database, unique local ports, fake/no providers, and
count-only output. Never touches data/careerpilot.db.
"""

from __future__ import annotations

import os
import re
import shutil
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
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    InterviewPrepRecord,
    JobIntelligenceRecord,
    JobRecord,
    MatchScoreRecord,
    TargetPreference,
    User,
)

PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()
JOB_PUBLIC_ID = "mvp-browser-job"
JOB_TITLE = "Synthetic Browser Engineer"
JOB_COMPANY = "Fictional Browser Works"
USER_A_EMAIL = "browser-a@example.com"
USER_B_EMAIL = "browser-b@example.com"
USER_PASSWORD = "browser-password-123"
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


def _log_snippet(path: Path | None, limit: int = 1200) -> str:
    if path is None or not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-limit:]


def _wait_for_url(
    url: str,
    timeout: float = 60.0,
    *,
    process: subprocess.Popen[Any] | None = None,
    log_path: Path | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                f"Local test service exited early code={process.returncode} "
                f"url={url} log={_log_snippet(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:  # noqa: BLE001 - readiness retry
            time.sleep(0.2)
    raise RuntimeError(
        f"Local test service did not become ready url={url} log={_log_snippet(log_path)}"
    )


def _stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _ensure_frontend_dependencies() -> None:
    vite = ROOT / "frontend" / "node_modules" / "vite"
    if not vite.exists():
        raise RuntimeError("Frontend dependencies are not installed. Run npm ci in frontend/ first.")


def _python_bin() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return sys.executable


def _npm_bin() -> str:
    found = shutil.which("npm") or shutil.which("npm.cmd")
    if not found:
        raise RuntimeError("npm is not on PATH. Install Node.js 20+ and retry.")
    return found


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


def _signup(page: Any, base: str, email: str, password: str) -> None:
    page.goto(f"{base}/signup")
    page.locator('input[type="email"]').fill(email)
    page.locator('input[type="password"]').fill(password)
    page.get_by_role("button", name=re.compile(r"Sign up", re.I)).click()
    page.wait_for_url(re.compile(r"/onboarding"))
    page.get_by_test_id("onboarding-skip").click()
    page.wait_for_url(re.compile(r"/dashboard"))


def _login(page: Any, base: str, email: str, password: str) -> None:
    # Full navigation clears any ProtectedRoute "from" state left by logout.
    page.goto(f"{base}/login")
    page.locator('input[type="email"]').fill(email)
    page.locator('input[type="password"]').fill(password)
    page.get_by_role("button", name=re.compile(r"^Log in$", re.I)).click()
    page.wait_for_function("() => !window.location.pathname.includes('/login')")
    page.goto(f"{base}/dashboard")
    page.wait_for_url(re.compile(r"/dashboard"))


def _logout(page: Any) -> None:
    page.get_by_role("button", name=re.compile(r"Log out", re.I)).click()
    page.wait_for_url(re.compile(r"/login"))


def _seed_shared_job(session: Session) -> JobRecord:
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
    session.commit()
    session.refresh(job)
    return job


def _seed_user_private_rows(
    session: Session,
    *,
    email: str,
    job: JobRecord,
    tracker_status: str = "saved",
    name: str = "Synthetic Browser Candidate",
) -> tuple[User, Candidate]:
    user = session.query(User).filter(User.email == email).one()
    candidate = Candidate(
        user_id=user.id,
        name=name,
        email=email,
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
            user_id=user.id,
            candidate_id=candidate.id,
            target_roles=["Harbor Robotics Intern"],
            preferred_locations=["Remote"],
        )
    )
    existing_tracker = (
        session.query(ApplicationTrackerRecord)
        .filter(
            ApplicationTrackerRecord.job_id == job.id,
            ApplicationTrackerRecord.user_id == user.id,
        )
        .first()
    )
    if existing_tracker is None:
        session.add(
            ApplicationTrackerRecord(job_id=job.id, user_id=user.id, status=tracker_status)
        )
    session.commit()
    session.refresh(candidate)
    return user, candidate


def run_browser_workflow() -> dict[str, int]:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError as exc:  # pragma: no cover - tooling blocker
        raise RuntimeError("Python Playwright is unavailable.") from exc

    with tempfile.TemporaryDirectory(
        prefix="careerpilot-mvp-browser-",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        _ensure_frontend_dependencies()
        database_path = assert_safe_database_path(Path(temp_dir) / "mvp-browser.sqlite")
        backend_port = _free_port()
        frontend_port = _free_port()
        backend_log = Path(temp_dir) / "backend.log"
        frontend_log = Path(temp_dir) / "frontend.log"
        engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

        origin = f"http://127.0.0.1:{frontend_port}"
        backend_env = os.environ.copy()
        backend_env["DATABASE_URL"] = f"sqlite:///{database_path}"
        backend_env["GEMINI_API_KEY"] = ""
        backend_env["ANTHROPIC_API_KEY"] = ""
        backend_env["OPENAI_API_KEY"] = ""
        backend_env["ADZUNA_APP_ID"] = ""
        backend_env["ADZUNA_APP_KEY"] = ""
        backend_env["APP_ENV"] = "development"
        backend_env["COOKIE_SECURE"] = "false"
        backend_env["ALLOWED_ORIGINS"] = origin
        backend_env["EXTENSION_ORIGIN"] = ""
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}"
        backend_log_handle = backend_log.open("w", encoding="utf-8")
        frontend_log_handle = frontend_log.open("w", encoding="utf-8")
        backend = subprocess.Popen(
            [
                _python_bin(),
                "-m",
                "uvicorn",
                "backend.testing.browser_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ],
            cwd=ROOT,
            env=backend_env,
            stdout=backend_log_handle,
            stderr=subprocess.STDOUT,
        )
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
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=frontend_env,
            stdout=frontend_log_handle,
            stderr=subprocess.STDOUT,
        )
        checks = 0
        patch_calls: list[str] = []
        interview_posts: list[str] = []
        interview_gets: list[str] = []
        score_posts: list[str] = []
        intelligence_posts: list[str] = []
        materials_posts: list[str] = []
        resume_posts: list[str] = []
        me_gets: list[str] = []
        blocked_external: list[str] = []
        try:
            _wait_for_url(
                f"http://127.0.0.1:{backend_port}/health",
                process=backend,
                log_path=backend_log,
            )
            _wait_for_url(
                f"http://127.0.0.1:{frontend_port}/",
                process=frontend,
                log_path=frontend_log,
            )
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
                context = browser.new_context()
                page = context.new_page()

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
                    path = url.split("?", 1)[0].rstrip("/")
                    if method == "PATCH" and "/tracking" in url:
                        patch_calls.append(url)
                    if method == "POST" and path.endswith("/prepare-interview"):
                        interview_posts.append(url)
                    if method == "GET" and path.endswith("/interview-prep"):
                        interview_gets.append(url)
                    if method == "POST" and path.endswith("/score"):
                        score_posts.append(url)
                    if method == "POST" and path.endswith("/intelligence"):
                        intelligence_posts.append(url)
                    if method == "POST" and path.endswith("/generate-materials"):
                        materials_posts.append(url)
                    if method == "POST" and "/resume-versions" in path:
                        resume_posts.append(url)
                    if method == "GET" and path.endswith("/api/auth/me"):
                        me_gets.append(url)

                page.on("request", _track)
                base = origin

                page.goto(f"{base}/dashboard")
                expect(page).to_have_url(re.compile(r"/login"))
                checks += 1

                _signup(page, base, USER_A_EMAIL, USER_PASSWORD)
                expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
                expect(page.get_by_test_id("dashboard-next-action")).to_be_visible()
                expect(_metric(page, "Jobs discovered")).to_have_text("0")
                checks += 1

                with SessionLocal() as session:
                    job = _seed_shared_job(session)
                    _seed_user_private_rows(session, email=USER_A_EMAIL, job=job)

                page.reload()
                expect(_metric(page, "Jobs discovered")).to_have_text("1")
                page.goto(f"{base}/profile")
                expect(page.get_by_text("Synthetic Browser Candidate")).to_be_visible()
                expect(page.get_by_text("Harbor Robotics Intern")).to_be_visible()
                _logout(page)
                _login(page, base, USER_A_EMAIL, USER_PASSWORD)
                page.goto(f"{base}/profile")
                expect(page.get_by_text("Synthetic Browser Candidate")).to_be_visible()
                expect(page.get_by_text("Harbor Robotics Intern")).to_be_visible()
                checks += 1

                before_score_posts = len(score_posts)
                before_intelligence_posts = len(intelligence_posts)
                before_materials_posts = len(materials_posts)
                before_resume_posts = len(resume_posts)
                page.goto(f"{base}/jobs")
                expect(page.get_by_role("heading", name="Jobs", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name=JOB_TITLE)).to_be_visible()
                if len(score_posts) != before_score_posts:
                    raise AssertionError("Jobs page load issued a scoring POST.")
                if len(intelligence_posts) != before_intelligence_posts:
                    raise AssertionError("Jobs page load issued an intelligence POST.")
                if len(materials_posts) != before_materials_posts:
                    raise AssertionError("Jobs page load issued a materials POST.")
                checks += 1

                page.get_by_role("link", name="View Analysis").first.click()
                expect(page).to_have_url(re.compile(rf"/jobs/{JOB_PUBLIC_ID}"))
                expect(page.get_by_role("heading", name=JOB_TITLE)).to_be_visible()
                checks += 1

                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}/prepare")
                expect(page.get_by_role("heading", name="Prepare application", exact=True)).to_be_visible()
                expect(page.get_by_text("No grounded materials stored yet.")).to_be_visible()
                if len(score_posts) != before_score_posts:
                    raise AssertionError("Prepare page load issued a scoring POST.")
                if len(materials_posts) != before_materials_posts:
                    raise AssertionError("Prepare page load issued a materials POST.")
                checks += 1

                page.get_by_test_id("calculate-fit").click()
                expect(page.get_by_text("Not scored yet. Calculate fit to store a score.")).to_have_count(0)
                if len(score_posts) != before_score_posts + 1:
                    raise AssertionError("Calculate fit did not issue exactly one scoring POST.")
                with SessionLocal() as session:
                    user_a = session.query(User).filter(User.email == USER_A_EMAIL).one()
                    candidate = session.query(Candidate).filter(Candidate.user_id == user_a.id).one()
                    score = (
                        session.query(MatchScoreRecord)
                        .filter(MatchScoreRecord.candidate_id == candidate.id)
                        .one()
                    )
                    score.matched_skills = ["UniqueMatchedSkillAlpha"]
                    score.missing_skills = ["UniqueMissingSkillOmega"]
                    session.commit()
                checks += 1

                page.get_by_test_id("generate-materials").click()
                expect(page.get_by_text("Python is listed in the stored candidate skill evidence.")).to_be_visible()
                if len(materials_posts) != before_materials_posts + 1:
                    raise AssertionError("Generate materials did not issue exactly one materials POST.")
                checks += 1

                page.reload()
                expect(page.get_by_text("Python is listed in the stored candidate skill evidence.")).to_be_visible()
                if len(materials_posts) != before_materials_posts + 1:
                    raise AssertionError("Prepare refresh issued another materials POST.")
                checks += 1

                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}/prepare")
                approve = page.get_by_role("button", name="Approve")
                expect(approve).to_be_disabled()
                page.get_by_role("checkbox").check()
                expect(approve).to_be_enabled()
                approve.click()
                expect(page.get_by_text("approved", exact=False)).to_be_visible()
                checks += 1

                page.get_by_test_id("save-resume-version").click()
                expect(page.get_by_test_id("resume-version-1")).to_be_visible()
                if len(resume_posts) != before_resume_posts + 1:
                    raise AssertionError("Save resume version did not issue exactly one create POST.")
                checks += 1

                page.goto(f"{base}/resume")
                expect(page.get_by_text("Version 1").first).to_be_visible()
                href = page.locator('a[href^="/resume/"]').first.get_attribute("href")
                if not href:
                    raise AssertionError("Resume library did not expose a version deep link.")
                page.goto(f"{base}{href}")
                expect(page.get_by_test_id("resume-preview")).to_be_visible()
                checks += 1

                page.goto(f"{base}/track")
                expect(page.get_by_role("heading", name="Track", exact=True)).to_be_visible()
                status_select = page.get_by_label(re.compile(r"Tracking status for"))
                expect(status_select).to_be_visible()
                status_select.select_option("pending_review")
                expect(status_select).to_have_value("pending_review")
                if len(patch_calls) != 1:
                    raise AssertionError("Track status change did not issue exactly one tracking PATCH.")
                checks += 1

                before_interview_posts = len(interview_posts)
                before_interview_gets = len(interview_gets)
                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}")
                expect(page.get_by_role("heading", name=JOB_TITLE)).to_be_visible()
                expect(page.get_by_text("No interview prep stored yet.")).to_be_visible()
                if len(interview_posts) != before_interview_posts:
                    raise AssertionError("Job Detail load issued an interview POST.")
                if len(interview_gets) < before_interview_gets + 1:
                    raise AssertionError("Job Detail load did not GET stored interview prep.")
                checks += 1

                page.get_by_role("button", name="Prepare interview").click()
                # .first, not a bare locator: the same question text is now also an
                # <option> in the "Practice an answer" question <select> rendered below
                # the likely-questions list, which would otherwise trip Playwright's
                # strict-mode uniqueness check. The <li> renders before the <select> in
                # DOM order, so .first is the list item.
                expect(
                    page.get_by_text(
                        "What would you expect to discuss about Python fundamentals for this role?",
                        exact=True,
                    ).first
                ).to_be_visible()
                if len(interview_posts) != before_interview_posts + 1:
                    raise AssertionError("Prepare Interview did not issue exactly one POST.")
                checks += 1

                # Cross-user isolation: jobs are shared; private records are not.
                _logout(page)
                _signup(page, base, USER_B_EMAIL, USER_PASSWORD)
                page.goto(f"{base}/profile")
                expect(page.get_by_text("Synthetic Browser Candidate")).to_have_count(0)
                expect(page.get_by_text("Harbor Robotics Intern")).to_have_count(0)
                page.goto(f"{base}/dashboard")
                expect(page.get_by_text("Loading dashboard…")).to_have_count(0)
                expect(_metric(page, "Skills")).to_have_text("0")
                page.goto(f"{base}/resume")
                expect(page.get_by_text("No resume versions")).to_be_visible()
                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}/prepare")
                expect(page.get_by_text("No grounded materials stored yet.")).to_be_visible()
                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}")
                expect(page.get_by_text("No interview prep stored yet.")).to_be_visible()
                page.get_by_role("button", name="Prepare interview").click()
                expect(page.get_by_text("UniqueMatchedSkillAlpha")).to_have_count(0)
                expect(page.get_by_text("UniqueMissingSkillOmega")).to_have_count(0)
                checks += 1

                # Explicit stale reviewed reset for user A.
                _logout(page)
                _login(page, base, USER_A_EMAIL, USER_PASSWORD)
                page.goto(f"{base}/profile")
                expect(page.get_by_text("Synthetic Browser Candidate")).to_be_visible()
                expect(page.get_by_text("Harbor Robotics Intern")).to_be_visible()
                with SessionLocal() as session:
                    user_a = session.query(User).filter(User.email == USER_A_EMAIL).one()
                    package = (
                        session.query(ApplicationPackageRecord)
                        .filter(ApplicationPackageRecord.user_id == user_a.id)
                        .one()
                    )
                    package.approval_status = "approved"
                    old_candidate = (
                        session.query(Candidate).filter(Candidate.user_id == user_a.id).one()
                    )
                    old_candidate.user_id = None
                    session.flush()
                    session.add(
                        Candidate(
                            user_id=user_a.id,
                            name="Synthetic Browser Candidate v2",
                            email=USER_A_EMAIL,
                            skills=["Python"],
                            projects=[
                                {
                                    "name": "Synthetic Planner",
                                    "description": "Python app",
                                    "technologies": ["Python"],
                                }
                            ],
                            experience=[
                                {
                                    "title": "Intern",
                                    "company": "Fictional Harbor Labs",
                                    "highlights": ["Wrote Python tests."],
                                }
                            ],
                            education=[
                                {
                                    "institution": "Fictional Lakeside University",
                                    "degree": "B.S.",
                                }
                            ],
                            certifications=[],
                            strengths=["Backend"],
                            evidence_links=[],
                        )
                    )
                    session.commit()

                page.goto(f"{base}/jobs/{JOB_PUBLIC_ID}/prepare")
                discard = page.get_by_test_id("discard-stale-materials")
                expect(discard).to_be_visible()
                before_materials = len(materials_posts)
                discard.click()
                expect(page.get_by_test_id("generate-materials")).to_be_visible()
                if len(materials_posts) != before_materials:
                    raise AssertionError("Discard stale materials issued a materials POST.")
                checks += 1

                # Extension header isolation against ordinary routes.
                cookies = context.cookies()
                session_cookie = next(
                    (item for item in cookies if item["name"] == "careerpilot_session"),
                    None,
                )
                if session_cookie is None:
                    raise AssertionError("Missing careerpilot_session cookie after login.")
                import urllib.error
                import urllib.request as ureq

                req = ureq.Request(
                    f"http://127.0.0.1:{backend_port}/api/jobs",
                    headers={"X-CareerPilot-Session": session_cookie["value"]},
                    method="GET",
                )
                try:
                    with ureq.urlopen(req, timeout=5) as response:
                        status = response.status
                except urllib.error.HTTPError as err:
                    status = err.code
                if status != 401:
                    raise AssertionError(
                        f"Extension header authenticated an ordinary route status={status}"
                    )
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
                "score_posts": len(score_posts),
                "intelligence_posts": len(intelligence_posts),
                "materials_posts": len(materials_posts),
                "me_gets": len(me_gets),
                "external_requests": len(blocked_external),
            }
        finally:
            _stop_process(frontend)
            _stop_process(backend)
            backend_log_handle.close()
            frontend_log_handle.close()
            engine.dispose()
            database_path.unlink(missing_ok=True)


def main() -> int:
    result = run_browser_workflow()
    print(
        "mvp_browser_checks={checks} tracker_patches={tracker_patches} "
        "interview_posts={interview_posts} interview_gets={interview_gets} "
        "score_posts={score_posts} intelligence_posts={intelligence_posts} "
        "materials_posts={materials_posts} me_gets={me_gets} "
        "external_requests={external_requests} result=pass".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

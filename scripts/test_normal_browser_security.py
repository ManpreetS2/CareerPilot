#!/usr/bin/env python3
"""Real-browser CORS/cookie/origin security check — no --disable-web-security.

The other Playwright workflows in this directory launch Chromium with
--disable-web-security so a broad "don't let anything outside localhost
through" route filter is enough to keep them deterministic. That flag also
turns off the browser's own same-origin/CORS enforcement, so a real backend
misconfiguration (wrong allowed origin, a cookie missing SameSite/HttpOnly)
would silently pass those scripts while still breaking every real user's
browser. This script runs with Chromium's default security intact and
proves the opposite of both directions: the real frontend origin can sign
up, get an HttpOnly session cookie, and stay authenticated across a reload;
a different origin holding the same browser's cookie jar cannot read
authenticated data because CORS refuses it.

Uses a temporary SQLite database and unique local ports. Never touches
data/careerpilot.db.
"""

from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _best_effort_unlink(path: Path) -> None:
    """SQLite can stay locked on Windows until the backend process fully exits."""
    for delay in (0.0, 0.2, 0.5, 1.0):
        if delay:
            time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            continue


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine

from backend.db.database import Base

PRODUCTION_DATABASE = (ROOT / "data" / "careerpilot.db").resolve()
USER_EMAIL = "security-check@example.com"
USER_PASSWORD = "security-check-password-1"

_ROGUE_PAGE = b"""<!doctype html><html><body><script>
window.__result = null;
fetch("__BACKEND_ORIGIN__/api/auth/me", { credentials: "include" })
  .then((res) => { window.__result = { blocked: false, status: res.status }; })
  .catch((err) => { window.__result = { blocked: true, error: String(err) }; });
</script></body></html>"""


def assert_safe_database_path(database_path: Path) -> Path:
    resolved = database_path.expanduser().resolve()
    if resolved == PRODUCTION_DATABASE:
        raise ValueError("Refusing to run the security check against the production database.")
    if resolved.suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Security check database must be a dedicated SQLite file.")
    return resolved


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _log_snippet(path: Path | None, limit: int = 1200) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


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
    raise RuntimeError(f"Local test service did not become ready url={url} log={_log_snippet(log_path)}")


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


def _start_rogue_origin_server(backend_origin: str) -> tuple[http.server.HTTPServer, threading.Thread, int]:
    """A different-origin page that tries to read the backend using whatever
    cookies this browser holds for it — the "some other site in the same
    browser" case CORS exists to stop, not something running under our own
    frontend origin."""
    page_body = _ROGUE_PAGE.replace(b"__BACKEND_ORIGIN__", backend_origin.encode())

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required name
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(page_body)

        def log_message(self, *_args: object) -> None:  # silence per-request logging
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def run_security_check() -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - tooling blocker
        raise RuntimeError("Python Playwright is unavailable.") from exc

    with tempfile.TemporaryDirectory(
        prefix="careerpilot-security-check-",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        _ensure_frontend_dependencies()
        database_path = assert_safe_database_path(Path(temp_dir) / "security-check.sqlite")
        backend_port = _free_port()
        frontend_port = _free_port()
        backend_log = Path(temp_dir) / "backend.log"
        frontend_log = Path(temp_dir) / "frontend.log"

        engine = create_engine(f"sqlite:///{database_path}", future=True)
        Base.metadata.create_all(bind=engine)
        engine.dispose()

        frontend_origin = f"http://127.0.0.1:{frontend_port}"
        backend_origin = f"http://127.0.0.1:{backend_port}"

        backend_env = os.environ.copy()
        backend_env["DATABASE_URL"] = f"sqlite:///{database_path}"
        backend_env["GEMINI_API_KEY"] = ""
        backend_env["ANTHROPIC_API_KEY"] = ""
        backend_env["OPENAI_API_KEY"] = ""
        backend_env["APP_ENV"] = "development"
        backend_env["COOKIE_SECURE"] = "false"
        # Only the real frontend origin is allowed — the rogue origin below
        # is deliberately never listed here.
        backend_env["ALLOWED_ORIGINS"] = frontend_origin
        backend_env["EXTENSION_ORIGIN"] = ""

        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = backend_origin

        backend_log_handle = backend_log.open("w", encoding="utf-8")
        frontend_log_handle = frontend_log.open("w", encoding="utf-8")
        rogue_server, rogue_thread, rogue_port = _start_rogue_origin_server(backend_origin)
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
        try:
            _wait_for_url(f"{backend_origin}/health", process=backend, log_path=backend_log)
            _wait_for_url(f"{frontend_origin}/", process=frontend, log_path=frontend_log)

            with sync_playwright() as playwright:
                # Deliberately no --disable-web-security: this is the whole
                # point of the script. Default Chromium security applies.
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                page.goto(f"{frontend_origin}/signup")
                page.locator('input[type="email"]').fill(USER_EMAIL)
                page.locator('input[type="password"]').fill(USER_PASSWORD)
                page.locator('button[type="submit"]').click()
                # Signup redirects to onboarding, not the app shell — the
                # real assertion here is that the cross-origin, credentialed
                # signup request succeeded at all, which this redirect
                # proves. /dashboard is also protected but shell-wrapped,
                # so it's the direct way to confirm the session is valid for
                # this check without also exercising onboarding.
                page.wait_for_url("**/onboarding", timeout=15000)
                page.goto(f"{frontend_origin}/dashboard")
                page.wait_for_selector('[data-testid="app-shell"]', timeout=15000)

                cookies = context.cookies(backend_origin)
                session_cookies = [c for c in cookies if c["name"] == "careerpilot_session"]
                if len(session_cookies) != 1:
                    raise AssertionError(f"Expected exactly one session cookie, found {len(session_cookies)}")
                session_cookie = session_cookies[0]
                if not session_cookie["httpOnly"]:
                    raise AssertionError("Session cookie is not HttpOnly")
                if session_cookie["sameSite"] not in ("Lax", "lax"):
                    raise AssertionError(f"Session cookie SameSite is {session_cookie['sameSite']!r}, expected Lax")
                if session_cookie["secure"]:
                    raise AssertionError("Session cookie is Secure on a plain-http dev origin")

                visible_to_js = page.evaluate("() => document.cookie")
                if "careerpilot_session" in visible_to_js:
                    raise AssertionError("Session cookie is readable via document.cookie despite HttpOnly")

                # Real cross-origin GET, real enforcement: does the session
                # actually survive a fresh page load, not just the tab that
                # set it.
                page.reload()
                page.wait_for_selector('[data-testid="app-shell"]', timeout=15000)

                # A different origin holding this browser's cookie jar must
                # not be able to read authenticated backend data.
                rogue_page = context.new_page()
                rogue_page.goto(f"http://127.0.0.1:{rogue_port}/")
                rogue_page.wait_for_function("() => window.__result !== null", timeout=10000)
                rogue_result = rogue_page.evaluate("() => window.__result")
                if not rogue_result.get("blocked"):
                    raise AssertionError(
                        f"Rogue origin read authenticated data: {rogue_result}"
                    )
                rogue_page.close()

                page.get_by_role("button", name="Log out").click()
                page.wait_for_selector('[data-testid="app-shell"]', state="detached", timeout=15000)
                cookies_after_logout = [
                    c for c in context.cookies(backend_origin) if c["name"] == "careerpilot_session"
                ]
                if cookies_after_logout:
                    raise AssertionError("Session cookie survived logout")

                page.goto(f"{frontend_origin}/dashboard")
                page.wait_for_selector('[data-testid="app-shell"]', state="detached", timeout=15000)

                browser.close()

            return {
                "signup_and_session": "pass",
                "http_only_enforced": "pass",
                "cross_origin_persists_after_reload": "pass",
                "rogue_origin_blocked": "pass",
                "logout_clears_session": "pass",
                "post_logout_route_protected": "pass",
            }
        finally:
            rogue_server.shutdown()
            rogue_thread.join(timeout=5)
            _stop_process(frontend)
            _stop_process(backend)
            backend_log_handle.close()
            frontend_log_handle.close()
            _best_effort_unlink(database_path)


def main() -> int:
    result = run_security_check()
    print(
        "normal_browser_security "
        + " ".join(f"{key}={value}" for key, value in result.items())
        + " result=pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

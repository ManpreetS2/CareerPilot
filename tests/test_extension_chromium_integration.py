"""Browser-level CareerPilot extension checks in a real Chromium context.

Uses Playwright's persistent context with --load-extension against the unpacked
browser-extension package (plus a small fillForm harness for Greenhouse/Lever
fixtures). Isolated from production data; no paid APIs; never submits forms.
"""

from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO / "browser-extension"
FIXTURES = REPO / "tests" / "fixtures" / "ats_forms"
HARNESS_ENTRY = EXTENSION_DIR / "tests" / "harness" / "fill-page.ts"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def extension_built() -> Path:
    subprocess.run(["npm", "run", "build"], cwd=EXTENSION_DIR, check=True)
    assert (EXTENSION_DIR / "dist" / "background.js").is_file()
    assert (EXTENSION_DIR / "dist" / "sidepanel.js").is_file()
    return EXTENSION_DIR


@pytest.fixture(scope="module")
def fill_harness_js(extension_built: Path) -> Path:
    out = Path(tempfile.mkdtemp(prefix="cp-fill-harness-")) / "fill-harness.js"
    esbuild = EXTENSION_DIR / "node_modules" / "esbuild" / "bin" / "esbuild"
    subprocess.run(
        [
            str(esbuild),
            str(HARNESS_ENTRY),
            "--bundle",
            "--format=iife",
            f"--outfile={out}",
            "--platform=browser",
        ],
        cwd=EXTENSION_DIR,
        check=True,
    )
    assert out.is_file()
    return out


@pytest.fixture(scope="module")
def fixture_server():
    port = _free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="module")
def extension_context(extension_built: Path):
    user_data = tempfile.mkdtemp(prefix="cp-ext-profile-")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data,
            # Chromium's new headless mode supports unpacked extensions on
            # GitHub Linux runners without Xvfb or a DISPLAY server.
            channel="chromium",
            headless=True,
            args=[
                f"--disable-extensions-except={extension_built}",
                f"--load-extension={extension_built}",
                "--no-default-browser-check",
            ],
        )
        # Service worker URL reveals the generated extension id.
        if not context.service_workers:
            context.wait_for_event("serviceworker", timeout=15000)
        worker = context.service_workers[0]
        extension_id = worker.url.split("/")[2]
        context.extension_id = extension_id  # type: ignore[attr-defined]
        context.service_worker = worker  # type: ignore[attr-defined]
        yield context
        context.close()


def test_extension_service_worker_and_sidepanel_load(extension_context) -> None:
    extension_id = extension_context.extension_id
    assert len(extension_id) == 32
    worker = extension_context.service_worker
    assert worker.url.startswith(f"chrome-extension://{extension_id}/")
    page = extension_context.new_page()
    page.goto(f"chrome-extension://{extension_id}/dist/sidepanel.html")
    page.wait_for_selector("#app", timeout=10000)
    # Side panel boot paints something into #app (loading / idle / error).
    assert page.locator("#app").inner_html().strip() != ""


def test_manifest_keeps_optional_ats_permissions_and_no_submit_surface(extension_built: Path) -> None:
    manifest = json.loads((extension_built / "manifest.json").read_text())
    assert "https://*.greenhouse.io/*" in manifest["optional_host_permissions"]
    assert "https://*.lever.co/*" in manifest["optional_host_permissions"]
    assert manifest["host_permissions"] == [
        "http://127.0.0.1:8000/*",
        "http://localhost:8000/*",
    ]
    sidepanel = (extension_built / "src" / "sidepanel.ts").read_text()
    assert ".submit(" not in sidepanel.replace(" ", "")
    assert "requestSubmit" not in sidepanel


def test_chromium_fills_greenhouse_react_select_and_skips_eeo(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    """Realistic Greenhouse react-select DOM in Chromium (not jsdom)."""
    page = extension_context.new_page()
    html = f"""<!doctype html>
<html><body>
  <form id="application_form">
    <div class="select__container">
      <label for="react-select-2-input">Expected graduation date</label>
      <div class="select__control"><div class="select__value-container">
        <div class="select__single-value"></div>
        <input id="react-select-2-input" role="combobox" aria-controls="react-select-2-listbox" />
      </div></div>
      <div id="react-select-2-listbox" role="listbox">
        <div role="option" id="react-select-2-option-0">May 2027</div>
        <div role="option" id="react-select-2-option-1">December 2027</div>
      </div>
    </div>
    <div class="select__container">
      <label for="react-select-3-input">Are you currently enrolled in a university or program?</label>
      <div class="select__control"><div class="select__value-container">
        <div class="select__single-value"></div>
        <input id="react-select-3-input" role="combobox" aria-controls="react-select-3-listbox" />
      </div></div>
      <div id="react-select-3-listbox" role="listbox">
        <div role="option" id="react-select-3-option-0">Yes</div>
        <div role="option" id="react-select-3-option-1">No</div>
      </div>
    </div>
    <div class="select__container">
      <label for="react-select-4-input">Degree</label>
      <div class="select__control"><div class="select__value-container">
        <div class="select__single-value"></div>
        <input id="react-select-4-input" role="combobox" aria-controls="react-select-4-listbox" />
      </div></div>
      <div id="react-select-4-listbox" role="listbox">
        <div role="option" id="react-select-4-option-0">Bachelor's</div>
        <div role="option" id="react-select-4-option-1">Master's</div>
      </div>
    </div>
    <div class="select__container">
      <label for="react-select-5-input">Do you require sponsorship?</label>
      <div class="select__control"><div class="select__value-container">
        <div class="select__single-value"></div>
        <input id="react-select-5-input" role="combobox" aria-controls="react-select-5-listbox" />
      </div></div>
      <div id="react-select-5-listbox" role="listbox">
        <div role="option" id="react-select-5-option-0">Yes</div>
        <div role="option" id="react-select-5-option-1">No</div>
      </div>
    </div>
    <div class="select__container">
      <label for="react-select-6-input">Gender</label>
      <div class="select__control"><div class="select__value-container">
        <div class="select__single-value" id="gender-value"></div>
        <input id="react-select-6-input" role="combobox" aria-controls="react-select-6-listbox" />
      </div></div>
      <div id="react-select-6-listbox" role="listbox">
        <div role="option" id="react-select-6-option-0">Female</div>
        <div role="option" id="react-select-6-option-1">Male</div>
      </div>
    </div>
    <label for="email">Email</label>
    <input id="email" name="job_application[email]" />
    <button type="submit" id="submit_app">Submit Application</button>
  </form>
  <script>
    document.querySelectorAll('[role="option"]').forEach((option) => {{
      option.addEventListener('click', () => {{
        const listbox = option.parentElement;
        listbox.querySelectorAll('[role="option"]').forEach((o) => o.setAttribute('aria-selected', 'false'));
        option.setAttribute('aria-selected', 'true');
        const root = listbox.parentElement;
        const single = root.querySelector('.select__single-value');
        if (single) single.textContent = option.textContent;
      }});
    }});
    document.getElementById('application_form').addEventListener('submit', (e) => {{
      e.preventDefault();
      window.__submitted = true;
    }});
  </script>
</body></html>"""
    page.set_content(html)
    page.add_script_tag(path=str(fill_harness_js))
    result = page.evaluate(
        """async () => {
          const buggy = document.querySelectorAll(
            '[id^="react-select-' + CSS.escape('react-select-2-input') + '-option-"]'
          );
          const result = await window.fillFormInPage({
            platform: 'greenhouse',
            fields: {
              email: 'ada@example.com',
              expected_graduation: 'May 2027',
              currently_enrolled_in_program: 'Yes',
              degree_pursuing: "Bachelor's",
              sponsorship_required: false,
              gender: 'Female',
            },
          });
          return {
            buggyCount: buggy.length,
            email: document.getElementById('email').value,
            graduation: document.querySelector('#react-select-2-listbox [aria-selected="true"]')?.textContent || '',
            enrolled: document.querySelector('#react-select-3-listbox [aria-selected="true"]')?.textContent || '',
            degree: document.querySelector('#react-select-4-listbox [aria-selected="true"]')?.textContent || '',
            sponsorship: document.querySelector('#react-select-5-listbox [aria-selected="true"]')?.textContent || '',
            gender: document.getElementById('gender-value').textContent || '',
            filled: result.filled.map((row) => row.name),
            flagged: result.flagged.map((row) => row.name),
            submitted: Boolean(window.__submitted),
          };
        }"""
    )
    assert result["buggyCount"] == 0
    assert result["email"] == "ada@example.com"
    assert result["graduation"] == "May 2027"
    assert result["enrolled"] == "Yes"
    assert result["degree"] == "Bachelor's"
    assert result["sponsorship"] == "No"
    assert result["gender"] == ""
    assert "gender" in result["flagged"]
    assert result["submitted"] is False


def test_chromium_fills_lever_standard_text_fields(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    page = extension_context.new_page()
    page.goto(f"{fixture_server}/lever_standard.html")
    page.add_script_tag(path=str(fill_harness_js))
    result = page.evaluate(
        """async () => {
          const beforeSubmit = document.querySelectorAll('form').length;
          const result = await window.fillFormInPage({
            platform: 'lever',
            fields: {
              full_name: 'Ada Lovelace',
              email: 'ada@example.com',
              phone: '555-0100',
              cover_letter: 'Dear team,',
            },
          });
          return {
            name: document.querySelector('input[name="name"]')?.value || '',
            email: document.querySelector('input[name="email"]')?.value || '',
            phone: document.querySelector('input[name="phone"]')?.value || '',
            filled: result.filled.map((row) => row.name),
            formCount: beforeSubmit,
          };
        }"""
    )
    assert result["name"] == "Ada Lovelace"
    assert result["email"] == "ada@example.com"
    assert result["phone"] == "555-0100"
    assert "email" in result["filled"]


def test_chromium_greenhouse_native_select_fixture_still_works(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    page = extension_context.new_page()
    page.goto(f"{fixture_server}/greenhouse_standard.html")
    page.add_script_tag(path=str(fill_harness_js))
    outcome = page.evaluate(
        """async () => {
          let submitted = false;
          document.getElementById('application_form').addEventListener('submit', (e) => {
            e.preventDefault();
            submitted = true;
          });
          const result = await window.fillFormInPage({
            platform: 'greenhouse',
            fields: {
              first_name: 'Ada',
              last_name: 'Lovelace',
              email: 'ada@example.com',
              sponsorship_required: false,
              currently_enrolled_in_program: 'Yes',
              gender: 'Female',
            },
          });
          return {
            email: document.getElementById('email').value,
            sponsorship: document.getElementById('question_5').value,
            enrolled: document.getElementById('question_6').value,
            gender: document.getElementById('question_8').value,
            filled: result.filled.map((row) => row.name),
            flagged: result.flagged.map((row) => row.name),
            submitted,
          };
        }"""
    )
    assert outcome["email"] == "ada@example.com"
    assert outcome["sponsorship"] == "No"
    assert outcome["enrolled"] == "Yes"
    assert outcome["gender"] == ""
    assert "gender" in outcome["flagged"]
    assert outcome["submitted"] is False

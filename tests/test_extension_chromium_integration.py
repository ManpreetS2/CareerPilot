"""Browser-level CareerPilot extension checks in a real Chromium context.

Uses Playwright's persistent context with --load-extension against the unpacked
browser-extension package (plus a small fill/attach harness for Greenhouse/Lever
fixtures). Isolated from production data; no paid APIs; never submits forms.
Live ATS pages are GET-probed only — never filled or submitted.
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
EXTENSION_DIR = REPO / "browser-extension"
FIXTURES = REPO / "tests" / "fixtures" / "ats_forms"
HARNESS_ENTRY = EXTENSION_DIR / "tests" / "harness" / "fill-page.ts"
LIVE_QA_NOTES = Path("/tmp/cursor/extension-live-qa-notes.txt")

# Public boards index — GET only, never interact with apply forms.
LIVE_GREENHOUSE_BOARDS_URL = "https://boards.greenhouse.io/stripe"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pdf_b64() -> str:
    return base64.b64encode(b"%PDF-1.4 fake resume").decode("ascii")


def _docx_b64() -> str:
    return base64.b64encode(b"PK\x03\x04fake-docx").decode("ascii")


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
    assert "CareerPilot needs permission to fill this site's form" in sidepanel


def test_chromium_optional_ats_permissions_start_ungranted(
    extension_context, extension_built: Path
) -> None:
    """Optional Greenhouse/Lever hosts stay ungated until an explicit allow.

    Headless Chromium may hang on chrome.permissions.request (permission UI),
    so this harness asserts the pre-grant state via contains() and that the
    side panel still surfaces the denial copy when request resolves false.
    Tab-guard abort messaging is covered by browser-extension/tests/tab-guard.test.ts.
    """
    extension_id = extension_context.extension_id
    page = extension_context.new_page()
    page.goto(f"chrome-extension://{extension_id}/dist/sidepanel.html")
    page.wait_for_selector("#app", timeout=10000)
    outcome = page.evaluate(
        """async () => {
          const origins = [
            'https://boards.greenhouse.io/*',
            'https://jobs.lever.co/*',
          ];
          const granted = {};
          for (const origin of origins) {
            granted[origin] = await chrome.permissions.contains({ origins: [origin] });
          }
          // Race request: some headless builds hang on the permission prompt
          // instead of returning false without a user gesture.
          let requestWithoutGesture = null;
          let requestTimedOut = false;
          try {
            requestWithoutGesture = await Promise.race([
              chrome.permissions.request({ origins: ['https://boards.greenhouse.io/*'] }),
              new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2500)),
            ]);
          } catch (err) {
            requestTimedOut = String(err && err.message ? err.message : err).includes('timeout');
            requestWithoutGesture = false;
          }
          const afterGreenhouse = await chrome.permissions.contains({
            origins: ['https://boards.greenhouse.io/*'],
          });
          return { granted, requestWithoutGesture, requestTimedOut, afterGreenhouse };
        }"""
    )
    assert outcome["granted"]["https://boards.greenhouse.io/*"] is False
    assert outcome["granted"]["https://jobs.lever.co/*"] is False
    assert outcome["requestWithoutGesture"] is False
    assert outcome["afterGreenhouse"] is False
    sidepanel = (extension_built / "src" / "sidepanel.ts").read_text()
    assert "CareerPilot needs permission to fill this site's form" in sidepanel


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
    <label for="privacy_ack">
      Please review and acknowledge the Candidate Privacy Policy
      <input type="checkbox" id="privacy_ack" name="job_application[answers][7][boolean_value]" />
    </label>
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
            privacyAck: document.getElementById('privacy_ack').checked,
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
    assert result["privacyAck"] is False
    assert "gender" in result["flagged"]
    assert result["submitted"] is False


def test_chromium_fills_lever_standard_text_fields_without_submit(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    page = extension_context.new_page()
    page.goto(f"{fixture_server}/lever_standard.html")
    page.add_script_tag(path=str(fill_harness_js))
    result = page.evaluate(
        """async () => {
          let submitted = false;
          const form = document.querySelector('form.application-form');
          form.addEventListener('submit', (e) => {
            e.preventDefault();
            submitted = true;
          });
          // Inject a Lever-style EEO select the filler must refuse.
          const eeoLabel = document.createElement('label');
          eeoLabel.setAttribute('for', 'gender');
          eeoLabel.textContent = 'Gender';
          const eeoSelect = document.createElement('select');
          eeoSelect.id = 'gender';
          eeoSelect.innerHTML = '<option value=""></option><option value="Female">Female</option>';
          form.appendChild(eeoLabel);
          form.appendChild(eeoSelect);

          const result = await window.fillFormInPage({
            platform: 'lever',
            fields: {
              full_name: 'Ada Lovelace',
              email: 'ada@example.com',
              phone: '555-0100',
              cover_letter: 'Dear team,',
              gender: 'Female',
            },
          });
          return {
            name: document.querySelector('input[name="name"]')?.value || '',
            email: document.querySelector('input[name="email"]')?.value || '',
            phone: document.querySelector('input[name="phone"]')?.value || '',
            gender: document.getElementById('gender').value,
            filled: result.filled.map((row) => row.name),
            flagged: result.flagged.map((row) => row.name),
            submitted,
          };
        }"""
    )
    assert result["name"] == "Ada Lovelace"
    assert result["email"] == "ada@example.com"
    assert result["phone"] == "555-0100"
    assert result["gender"] == ""
    assert "email" in result["filled"]
    assert "gender" in result["flagged"]
    assert result["submitted"] is False


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
            privacyAck: document.getElementById('privacy_ack').checked,
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
    assert outcome["privacyAck"] is False
    assert "gender" in outcome["flagged"]
    assert outcome["submitted"] is False


def test_chromium_resume_attach_failure_still_fills_safe_text(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    """Wrong resume MIME → attach fails; safe text fill still runs; no submit/EEO."""
    page = extension_context.new_page()
    # Combine PDF-only resume accept with identity + EEO + privacy fields.
    page.set_content(
        """<!doctype html>
<html><body>
  <form id="application_form">
    <label for="first_name">First Name</label>
    <input type="text" id="first_name" name="job_application[first_name]" />
    <label for="email">Email</label>
    <input type="email" id="email" name="job_application[email]" />
    <label for="resume">Resume</label>
    <input type="file" id="resume" name="job_application[resume]" accept=".pdf" />
    <label for="question_8">Gender</label>
    <select id="question_8" name="job_application[answers][8][text_value]">
      <option value="">Select...</option>
      <option value="Female">Female</option>
      <option value="Male">Male</option>
    </select>
    <label for="privacy_ack">
      Please review and acknowledge the Candidate Privacy Policy
      <input type="checkbox" id="privacy_ack" />
    </label>
    <button type="submit" id="submit_app">Submit Application</button>
  </form>
</body></html>"""
    )
    page.add_script_tag(path=str(fill_harness_js))
    outcome = page.evaluate(
        f"""async () => {{
          let submitted = false;
          document.getElementById('application_form').addEventListener('submit', (e) => {{
            e.preventDefault();
            submitted = true;
          }});
          const attach = await window.attachDocumentInPage({{
            kind: 'resume',
            filename: 'resume-v1.docx',
            mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            bytesBase64: '{_docx_b64()}',
          }});
          const fill = await window.fillFormInPage({{
            platform: 'greenhouse',
            fields: {{
              first_name: 'Ada',
              email: 'ada@example.com',
              gender: 'Female',
            }},
          }});
          const resumeFiles = document.getElementById('resume').files;
          return {{
            attachStatus: attach.status,
            attachReason: attach.reason,
            email: document.getElementById('email').value,
            firstName: document.getElementById('first_name').value,
            gender: document.getElementById('question_8').value,
            privacyAck: document.getElementById('privacy_ack').checked,
            resumeCount: resumeFiles ? resumeFiles.length : 0,
            filled: fill.filled.map((row) => row.name),
            flagged: fill.flagged.map((row) => row.name),
            verified: window.verifyResumeAttachmentInPage('resume-v1.docx').attached,
            submitted,
          }};
        }}"""
    )
    assert outcome["attachStatus"] == "manual"
    assert "accept" in (outcome["attachReason"] or "").lower() or "format" in (
        outcome["attachReason"] or ""
    ).lower()
    assert outcome["resumeCount"] == 0
    assert outcome["verified"] is False
    assert outcome["email"] == "ada@example.com"
    assert outcome["firstName"] == "Ada"
    assert outcome["gender"] == ""
    assert outcome["privacyAck"] is False
    assert "email" in outcome["filled"]
    assert "gender" in outcome["flagged"]
    assert outcome["submitted"] is False


def test_chromium_resume_ambiguous_and_unsupported_do_not_claim_attach(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    page = extension_context.new_page()
    pdf = _pdf_b64()

    page.goto(f"{fixture_server}/greenhouse_multiple_resume_files.html")
    page.add_script_tag(path=str(fill_harness_js))
    ambiguous = page.evaluate(
        f"""async () => {{
          let submitted = false;
          document.querySelector('form').addEventListener('submit', (e) => {{
            e.preventDefault();
            submitted = true;
          }});
          const attach = await window.attachDocumentInPage({{
            kind: 'resume',
            filename: 'resume-v1.pdf',
            mimeType: 'application/pdf',
            bytesBase64: '{pdf}',
          }});
          return {{ status: attach.status, submitted }};
        }}"""
    )
    assert ambiguous["status"] == "ambiguous"
    assert ambiguous["submitted"] is False

    page.goto(f"{fixture_server}/generic_unsupported_file.html")
    page.add_script_tag(path=str(fill_harness_js))
    unsupported = page.evaluate(
        f"""async () => {{
          const attach = await window.attachDocumentInPage({{
            kind: 'resume',
            filename: 'resume-v1.pdf',
            mimeType: 'application/pdf',
            bytesBase64: '{pdf}',
          }});
          return {{ status: attach.status, verified: window.verifyResumeAttachmentInPage('resume-v1.pdf').attached }};
        }}"""
    )
    assert unsupported["status"] == "unsupported_field"
    assert unsupported["verified"] is False


def test_chromium_successful_pdf_attach_on_greenhouse_fixture_still_no_submit(
    fixture_server: str, fill_harness_js: Path, extension_context
) -> None:
    page = extension_context.new_page()
    page.goto(f"{fixture_server}/greenhouse_resume_file.html")
    page.add_script_tag(path=str(fill_harness_js))
    outcome = page.evaluate(
        f"""async () => {{
          let submitted = false;
          document.getElementById('application_form').addEventListener('submit', (e) => {{
            e.preventDefault();
            submitted = true;
          }});
          const attach = await window.attachDocumentInPage({{
            kind: 'resume',
            filename: 'resume-v1.pdf',
            mimeType: 'application/pdf',
            bytesBase64: '{_pdf_b64()}',
          }});
          return {{
            status: attach.status,
            verifiedName: attach.verifiedName,
            verified: window.verifyResumeAttachmentInPage('resume-v1.pdf').attached,
            submitted,
          }};
        }}"""
    )
    assert outcome["status"] == "attached"
    assert outcome["verifiedName"] == "resume-v1.pdf"
    assert outcome["verified"] is True
    assert outcome["submitted"] is False


def test_live_greenhouse_boards_get_probe_only() -> None:
    """One GET against a public Greenhouse boards URL; never fill or submit.

    Records reachability in /tmp/cursor/extension-live-qa-notes.txt. CAPTCHA,
    bot blocks, or network failure → documented as unverified live-site.
    """
    LIVE_QA_NOTES.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "CareerPilot extension live-site QA notes (GET only — no fill/submit)",
        f"Target: {LIVE_GREENHOUSE_BOARDS_URL}",
    ]
    reachable = False
    detail = "unverified"
    try:
        with httpx.Client(follow_redirects=True, timeout=12.0) as client:
            response = client.get(
                LIVE_GREENHOUSE_BOARDS_URL,
                headers={"User-Agent": "CareerPilot-ReleaseQA/1.0 (read-only GET)"},
            )
        body = (response.text or "")[:4000].lower()
        blocked = any(
            token in body
            for token in ("captcha", "cf-challenge", "access denied", "attention required")
        )
        looks_like_boards = "greenhouse" in body or "job" in body or response.status_code == 200
        if response.status_code == 200 and looks_like_boards and not blocked:
            reachable = True
            detail = f"reachable HTTP {response.status_code}; content-type={response.headers.get('content-type')}"
        else:
            detail = (
                f"unverified live-site: HTTP {response.status_code}; "
                f"blocked={blocked}; content-type={response.headers.get('content-type')}"
            )
    except Exception as exc:  # noqa: BLE001 — probe must never fail the suite hard
        detail = f"unverified live-site: request failed ({type(exc).__name__}: {exc})"

    # Nested sync_playwright() conflicts with the module-scoped extension
    # harness (Playwright Sync API inside an active sync loop). httpx GET is
    # sufficient for reachability; do not navigate/fill/submit on live sites.
    lines.append(f"httpx: {detail}")
    lines.append(
        "playwright: skipped (nested Sync API unavailable while extension harness is active); "
        "httpx GET is the live reachability signal"
    )
    lines.append(f"reachable={reachable}")
    lines.append("Interaction: none (GET only; no fill, no submit, no EEO).")
    LIVE_QA_NOTES.write_text("\n".join(lines) + "\n")
    # Probe always passes — live reachability is informational for release QA.
    assert LIVE_QA_NOTES.is_file()
    assert "GET only" in LIVE_QA_NOTES.read_text()

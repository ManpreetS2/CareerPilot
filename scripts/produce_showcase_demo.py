#!/usr/bin/env python3
"""Produce a premium CareerPilot portfolio demo video.

Design goals (v2 redesign):
- Continuous authenticated session (login never shown)
- Dark theme + real mouse/click/scroll interactions
- Injected visible cursor (Playwright video has no OS cursor)
- High source capture, 1080p delivery, crisp H.264
- Brief kinetic ASS callouts — not permanent caption bars
- Feature-focused cuts with subtle zoom/pan

Uses isolated synthetic showcase data only. Never touches data/careerpilot.db.
Does not click Submit or fill EEO fields. Extension beat uses the labeled
illustrative fixture — never presented as a live employer page.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_showcase_screenshots import (  # noqa: E402
    _identity_from_collected,
    _record_identity_payloads,
    require_showcase_identity,
    validate_loopback_base_url,
)
from scripts._demo_cursor_utils import MouseTracker, burn_cursor  # noqa: E402
from scripts.seed_showcase_demo import (  # noqa: E402
    SHOWCASE_EMAIL,
    SHOWCASE_PASSWORD,
    SHOWCASE_PRIMARY_JOB,
)

FIXTURE = ROOT / "docs" / "showcase" / "fixtures" / "generic-ats-form.html"
DEFAULT_OUT = ROOT / "docs" / "showcase" / "video" / "careerpilot-demo.mp4"
ARTIFACT_OUT = Path("/opt/cursor/artifacts/careerpilot-demo.mp4")
ARCHIVE_OUT = ROOT / "docs" / "showcase" / "video" / "careerpilot-demo.v1-archive.mp4"

INTER_BOLD = "/usr/share/fonts/truetype/macos/Inter-Bold.ttf"
INTER_SEMI = "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf"
INTER_MED = "/usr/share/fonts/truetype/macos/Inter-Medium.ttf"

# Capture larger than deliverable so zooms stay sharp.
CAPTURE_W = 2560
CAPTURE_H = 1440
OUT_W = 1920
OUT_H = 1080
FPS = 30

CURSOR_INIT_SCRIPT = """
(() => {
  const install = () => {
    if (document.getElementById('__cp_demo_cursor')) return;
    const style = document.createElement('style');
    style.textContent = `
      #__cp_demo_cursor {
        position: fixed; left: 80px; top: 80px; width: 28px; height: 28px;
        margin-left: -14px; margin-top: -14px; border-radius: 999px;
        border: 2.5px solid rgba(237, 233, 254, 0.98);
        background: rgba(139, 92, 246, 0.62);
        box-shadow: 0 0 0 8px rgba(139, 92, 246, 0.16), 0 10px 28px rgba(0,0,0,0.45);
        pointer-events: none; z-index: 2147483647;
        transition: transform 70ms ease, background 70ms ease, box-shadow 70ms ease;
      }
      #__cp_demo_cursor.is-down {
        transform: scale(0.68);
        background: rgba(196, 181, 253, 0.88);
        box-shadow: 0 0 0 14px rgba(196, 181, 253, 0.2);
      }
      html, body, * { cursor: none !important; }
    `;
    document.documentElement.appendChild(style);
    const c = document.createElement('div');
    c.id = '__cp_demo_cursor';
    document.documentElement.appendChild(c);
    window.__cpMoveCursor = (x, y) => {
      c.style.left = x + 'px';
      c.style.top = y + 'px';
      window.__cpLastX = x;
      window.__cpLastY = y;
    };
    window.addEventListener('mousemove', (e) => window.__cpMoveCursor(e.clientX, e.clientY), true);
    window.addEventListener('mousedown', () => c.classList.add('is-down'), true);
    window.addEventListener('mouseup', () => c.classList.remove('is-down'), true);
  };
  install();
  new MutationObserver(install).observe(document.documentElement, { childList: true, subtree: true });
})();
"""


def _run(cmd: list[str], *, quiet: bool = False) -> None:
    if not quiet:
        print("+", " ".join(cmd[:14]), ("..." if len(cmd) > 14 else ""), flush=True)
    subprocess.run(cmd, check=True, capture_output=quiet)


def _probe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return float(json.loads(raw)["format"]["duration"])


def _mark(markers: list[dict[str, object]], t0: float, name: str, **extra: object) -> None:
    markers.append({"t": round(time.monotonic() - t0, 3), "name": name, **extra})
    print(f"  mark @{markers[-1]['t']:.2f}s  {name}", flush=True)


def _bootstrap_storage(base: str, work: Path) -> Path:
    """Login once (unrecorded) and persist dark-theme storage state."""
    from playwright.sync_api import sync_playwright

    state_path = work / "storage.json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": CAPTURE_W, "height": CAPTURE_H})
        page = context.new_page()
        collected: dict[str, object] = {}
        _record_identity_payloads(page, collected)
        page.goto(f"{base}/login", wait_until="networkidle")
        page.evaluate(
            """() => {
              localStorage.setItem('careerpilot-theme', 'dark');
              document.documentElement.classList.add('dark');
            }"""
        )
        page.get_by_label("Email").fill(SHOWCASE_EMAIL)
        page.get_by_label("Password").fill(SHOWCASE_PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_function(
            "() => !location.pathname.includes('/login')", timeout=20000
        )
        page.goto(f"{base}/jobs", wait_until="networkidle")
        page.wait_for_timeout(500)
        email, name, job_ids, companies = _identity_from_collected(collected)
        require_showcase_identity(
            email=email, name=name, job_ids=job_ids, companies=companies
        )
        context.storage_state(path=str(state_path))
        browser.close()
    return state_path


def _record_guest_landing(base: str, work: Path) -> Path:
    """Unauthenticated dark landing — needed because / redirects when logged in."""
    from playwright.sync_api import sync_playwright

    raw_dir = work / "raw-landing"
    raw_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": CAPTURE_W, "height": CAPTURE_H},
            color_scheme="dark",
            reduced_motion="no-preference",
            record_video_dir=str(raw_dir),
            record_video_size={"width": CAPTURE_W, "height": CAPTURE_H},
        )
        context.add_init_script(CURSOR_INIT_SCRIPT)
        context.add_init_script(
            """() => {
              localStorage.setItem('careerpilot-theme', 'dark');
              document.documentElement.classList.add('dark');
            }"""
        )
        page = context.new_page()
        page.emulate_media(color_scheme="dark", reduced_motion="no-preference")
        t0 = time.monotonic()
        mouse = MouseTracker(t0)
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_timeout(500)
        mouse.move(page, CAPTURE_W * 0.28, CAPTURE_H * 0.28, steps=30)
        page.wait_for_timeout(450)
        cta = page.get_by_role("link", name="Get Started").or_(
            page.get_by_role("button", name="Get Started")
        ).first
        if cta.count():
            box = cta.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=40,
                )
        page.wait_for_timeout(1400)
        mouse.move(page, CAPTURE_W * 0.55, CAPTURE_H * 0.52, steps=28)
        page.wait_for_timeout(900)
        video = page.video
        page.close()
        assert video is not None
        dest = work / "landing.webm"
        shutil.move(str(video.path()), str(dest))
        mouse.save(work / "landing-mouse.json")
        context.close()
        browser.close()
        burned = work / "landing.mp4"
        burn_cursor(
            dest,
            burned,
            mouse.log,
            src_w=CAPTURE_W,
            src_h=CAPTURE_H,
            fps=FPS,
        )
    return burned


def _record_session(base: str, work: Path, state_path: Path) -> tuple[Path, list[dict[str, object]]]:
    from playwright.sync_api import sync_playwright

    markers: list[dict[str, object]] = []
    raw_dir = work / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": CAPTURE_W, "height": CAPTURE_H},
            device_scale_factor=1,
            color_scheme="dark",
            reduced_motion="no-preference",
            storage_state=str(state_path),
            record_video_dir=str(raw_dir),
            record_video_size={"width": CAPTURE_W, "height": CAPTURE_H},
        )
        context.add_init_script(CURSOR_INIT_SCRIPT)
        page = context.new_page()
        page.emulate_media(color_scheme="dark", reduced_motion="no-preference")

        t0 = time.monotonic()
        mouse = MouseTracker(t0)
        _mark(markers, t0, "start")

        # --- Overview ---
        page.goto(f"{base}/dashboard", wait_until="networkidle")
        page.wait_for_timeout(500)
        _mark(markers, t0, "overview_in")
        mouse.move(page, CAPTURE_W * 0.48, CAPTURE_H * 0.36, steps=30)
        page.wait_for_timeout(700)
        mouse.move(page, CAPTURE_W * 0.62, CAPTURE_H * 0.55, steps=26)
        page.wait_for_timeout(1800)
        _mark(markers, t0, "overview_out")

        # --- Profile ---
        page.goto(f"{base}/profile", wait_until="networkidle")
        page.wait_for_timeout(500)
        _mark(markers, t0, "profile_in")
        page.get_by_text("Jordan Avery", exact=False).first.wait_for(timeout=15000)
        mouse.move(page, CAPTURE_W * 0.42, CAPTURE_H * 0.32, steps=28)
        page.wait_for_timeout(500)
        mouse.scroll_by(page, 520, ticks=10)
        page.wait_for_timeout(600)
        skills = page.get_by_text("Python", exact=True).first
        if skills.count():
            box = skills.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=26,
                )
        page.wait_for_timeout(2200)
        _mark(markers, t0, "profile_out")

        # --- Discover ---
        page.goto(f"{base}/jobs", wait_until="networkidle")
        page.wait_for_timeout(500)
        _mark(markers, t0, "discover_in")
        harbor = page.get_by_role(
            "button",
            name="Select Software Engineer Intern at Harborline Analytics",
        )
        harbor.wait_for(timeout=15000)
        page.wait_for_timeout(400)
        mouse.click_locator(page, harbor, steps=34)
        page.wait_for_timeout(900)
        fit = page.get_by_text("96", exact=True).first
        if fit.count():
            box = fit.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                    steps=28,
                )
                _mark(
                    markers,
                    t0,
                    "discover_zoom",
                    fx=(box["x"] + box["width"] / 2) / CAPTURE_W,
                    fy=(box["y"] + box["height"] / 2) / CAPTURE_H,
                )
        page.wait_for_timeout(1400)
        prepare_btn = page.get_by_role("button", name="Prepare Application").or_(
            page.get_by_role("link", name="Prepare Application")
        )
        if prepare_btn.count():
            box = prepare_btn.first.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] * 0.4,
                    box["y"] + box["height"] / 2,
                    steps=24,
                )
        page.wait_for_timeout(1800)
        _mark(markers, t0, "discover_out")

        # --- Evidence ---
        page.goto(f"{base}/jobs/{SHOWCASE_PRIMARY_JOB}", wait_until="networkidle")
        page.wait_for_timeout(450)
        _mark(markers, t0, "evidence_in")
        evidence_tab = page.get_by_role("tab", name="Evidence")
        mouse.click_locator(page, evidence_tab, steps=26)
        page.get_by_test_id("match-evidence").wait_for(timeout=15000)
        page.wait_for_timeout(700)
        python_factor = (
            page.get_by_test_id("evidence-section-required_skills")
            .locator('[data-testid^="factor-factor_skill_required_"]')
            .filter(has_text="Python")
            .first
        )
        view_btn = python_factor.get_by_role("button", name="View evidence")
        mouse.click_locator(page, view_btn, steps=28)
        drawer = page.get_by_test_id("evidence-drawer")
        drawer.get_by_text("Candidate evidence", exact=True).wait_for(timeout=10000)
        page.wait_for_timeout(700)
        cite = drawer.get_by_text("Campus Planner", exact=False).first
        if cite.count():
            box = cite.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + min(box["width"] * 0.4, 180),
                    box["y"] + box["height"] / 2,
                    steps=24,
                )
                _mark(
                    markers,
                    t0,
                    "evidence_zoom",
                    fx=(box["x"] + box["width"] * 0.3) / CAPTURE_W,
                    fy=(box["y"] + box["height"] / 2) / CAPTURE_H,
                )
        page.wait_for_timeout(1800)
        close = page.get_by_role("button", name="Close menu")
        if close.count():
            mouse.click_locator(page, close, steps=18)
            page.wait_for_timeout(400)
        docker_factor = (
            page.get_by_test_id("evidence-section-preferred_skills")
            .locator('[data-testid^="factor-factor_skill_preferred_"]')
            .filter(has_text="Docker")
            .first
        )
        if docker_factor.count():
            docker_factor.scroll_into_view_if_needed()
            box = docker_factor.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] * 0.5,
                    box["y"] + box["height"] * 0.5,
                    steps=24,
                )
        page.wait_for_timeout(2000)
        _mark(markers, t0, "evidence_out")

        # --- Prepare ---
        page.goto(
            f"{base}/jobs/{SHOWCASE_PRIMARY_JOB}/prepare", wait_until="networkidle"
        )
        page.wait_for_timeout(500)
        _mark(markers, t0, "prepare_in")
        page.get_by_role("heading", name="Cover letter").wait_for(timeout=15000)
        page.get_by_test_id("approval-status").wait_for(timeout=15000)
        cover = page.get_by_role("heading", name="Cover letter")
        cover.evaluate("el => el.scrollIntoView({ block: 'start', inline: 'nearest' })")
        page.wait_for_timeout(500)
        mouse.move(page, CAPTURE_W * 0.48, CAPTURE_H * 0.55, steps=26)
        mouse.scroll_by(page, 320, ticks=6)
        page.wait_for_timeout(600)
        approval = page.get_by_test_id("approval-status")
        if approval.count():
            box = approval.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + box["width"] * 0.4,
                    box["y"] + box["height"] * 0.5,
                    steps=26,
                )
                _mark(
                    markers,
                    t0,
                    "prepare_zoom",
                    fx=(box["x"] + box["width"] * 0.4) / CAPTURE_W,
                    fy=(box["y"] + box["height"] * 0.5) / CAPTURE_H,
                )
        page.wait_for_timeout(2400)
        _mark(markers, t0, "prepare_out")

        # --- Track ---
        page.goto(f"{base}/track", wait_until="networkidle")
        page.wait_for_timeout(450)
        _mark(markers, t0, "track_in")
        list_btn = page.get_by_role("button", name="List")
        if list_btn.count():
            mouse.click_locator(page, list_btn, steps=22)
        page.wait_for_timeout(700)
        row = page.get_by_text("Harborline Analytics", exact=False).first
        if row.count():
            box = row.bounding_box()
            if box:
                mouse.move(
                    page,
                    box["x"] + 80,
                    box["y"] + box["height"] / 2,
                    steps=24,
                )
        page.wait_for_timeout(2200)
        _mark(markers, t0, "track_out")

        # --- Analytics ---
        page.goto(f"{base}/analytics", wait_until="networkidle")
        page.wait_for_timeout(500)
        _mark(markers, t0, "analytics_in")
        mouse.move(page, CAPTURE_W * 0.5, CAPTURE_H * 0.38, steps=26)
        page.wait_for_timeout(700)
        mouse.scroll_by(page, 260, ticks=5)
        page.wait_for_timeout(2200)
        _mark(markers, t0, "analytics_out")

        # --- Illustrative extension fixture ---
        page.goto(FIXTURE.resolve().as_uri(), wait_until="networkidle")
        page.wait_for_timeout(400)
        _mark(markers, t0, "extension_in")
        mouse.move(page, CAPTURE_W * 0.32, CAPTURE_H * 0.38, steps=22)
        page.wait_for_timeout(900)
        mouse.move(page, CAPTURE_W * 0.68, CAPTURE_H * 0.48, steps=30)
        page.wait_for_timeout(2000)
        _mark(markers, t0, "extension_out")

        # Closing base on dashboard
        page.goto(f"{base}/dashboard", wait_until="networkidle")
        page.wait_for_timeout(400)
        _mark(markers, t0, "closing_in")
        page.wait_for_timeout(4200)
        _mark(markers, t0, "end")

        video = page.video
        page.close()
        assert video is not None
        webm = Path(video.path())
        context.close()
        browser.close()
        dest = work / "session.webm"
        shutil.move(str(webm), str(dest))
        mouse.save(work / "session-mouse.json")
        burned = work / "session.mp4"
        burn_cursor(
            dest,
            burned,
            mouse.log,
            src_w=CAPTURE_W,
            src_h=CAPTURE_H,
            fps=FPS,
        )
    (work / "markers.json").write_text(json.dumps(markers, indent=2), encoding="utf-8")
    return burned, markers


def _marker_map(markers: list[dict[str, object]]) -> dict[str, float]:
    return {str(m["name"]): float(m["t"]) for m in markers}


def _cut(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    *,
    zoom_end: float = 1.0,
    focus_x: float = 0.5,
    focus_y: float = 0.45,
) -> None:
    """Cut [start,end) and optionally ease zoom toward focus, scaled to 1080p."""
    duration = max(end - start, 0.2)
    # Soft zoom via crop+scale. z goes from 1.0 → zoom_end over the clip.
    if abs(zoom_end - 1.0) < 0.01:
        vf = (
            f"scale={OUT_W}:{OUT_H}:flags=lanczos,"
            f"setsar=1,fps={FPS},format=yuv420p"
        )
    else:
        # Slow push-in via zoompan on an upscaled buffer.
        vf = (
            f"scale={int(OUT_W * zoom_end)}:{int(OUT_H * zoom_end)}:flags=lanczos,"
            f"zoompan=z='min({zoom_end:.4f},1+({zoom_end:.4f}-1)*on/({max(duration * FPS, 1):.1f}))'"
            f":x='iw/2-(iw/zoom/2)+({focus_x:.4f}-0.5)*iw*(1-1/zoom)*0.35'"
            f":y='ih/2-(ih/zoom/2)+({focus_y:.4f}-0.5)*ih*(1-1/zoom)*0.35'"
            f":d=1:s={OUT_W}x{OUT_H}:fps={FPS},"
            f"setsar=1,format=yuv420p"
        )
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            str(dst),
        ]
    )


def _write_ass(path: Path, events: list[tuple[float, float, str]]) -> None:
    # ASS colours are &HAABBGGRR
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Inter,68,&H00F5F3FF,&H000000FF,&H66140A2E,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: HookSub,Inter,30,&H00D4C4FF,&H000000FF,&H66140A2E,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,80,80,72,1
Style: Callout,Inter,30,&H00F5F3FF,&H000000FF,&H00000000,&HAA0B0618,0,0,0,0,100,100,0.3,0,3,0,0,7,72,72,56,1
Style: CloseTitle,Inter,58,&H00F5F3FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,80,80,0,1
Style: CloseSub,Inter,28,&H00E9D5FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,80,80,68,1
Style: CloseUrl,Inter,26,&H00C4B5FD,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,80,80,118,1
Style: Label,Inter,24,&H00F5F3FF,&H000000FF,&H00000000,&HB00B0618,0,0,0,0,100,100,0.2,0,3,0,0,7,72,72,52,1
Style: Dim,Inter,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ts(seconds: float) -> str:
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = [header]
    for start, end, text in events:
        lines.append(text.replace("{START}", ts(start)).replace("{END}", ts(end)))
    path.write_text("\n".join(lines), encoding="utf-8")


def _overlay_ass(src: Path, ass: Path, dst: Path) -> None:
    # Escape path for ffmpeg fontsdir / ass filter
    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")
    fontsdir = "/usr/share/fonts/truetype/macos".replace(":", "\\:")
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"ass='{ass_esc}':fontsdir='{fontsdir}'",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )


def _xfade_concat(clips: list[Path], out: Path, fade: float = 0.28) -> None:
    if len(clips) == 1:
        shutil.copy(clips[0], out)
        return
    durations = [_probe_duration(c) for c in clips]
    inputs: list[str] = []
    for c in clips:
        inputs.extend(["-i", str(c)])
    parts: list[str] = []
    current = "[0:v]"
    timeline = 0.0
    for i in range(1, len(clips)):
        timeline += max(durations[i - 1] - fade, 0.05)
        label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        parts.append(
            f"{current}[{i}:v]xfade=transition=fade:duration={fade}:offset={timeline:.3f}{label}"
        )
        current = label
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(parts),
        "-map",
        "[vout]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-movflags",
        "+faststart",
        str(out),
    ]
    try:
        _run(cmd)
    except subprocess.CalledProcessError:
        listing = out.parent / "concat.txt"
        listing.write_text(
            "".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8"
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )


def _focus_from_markers(
    markers: list[dict[str, object]], name: str, default: tuple[float, float]
) -> tuple[float, float]:
    for mk in markers:
        if mk.get("name") == name:
            return float(mk.get("fx", default[0])), float(mk.get("fy", default[1]))
    return default


def _build_edit(
    landing: Path,
    session: Path,
    markers: list[dict[str, object]],
    work: Path,
) -> Path:
    m = _marker_map(markers)
    clips_dir = work / "clips"
    clips_dir.mkdir(exist_ok=True)

    def seg(name_a: str, name_b: str, pad_in: float = 0.08, pad_out: float = 0.04) -> tuple[float, float]:
        a = m[name_a] + pad_in
        b = m[name_b] - pad_out
        if b <= a + 0.5:
            b = a + 1.2
        return a, b

    plan: list[dict[str, object]] = []

    # Guest landing is a separate file — use full clip with mild push-in
    landing_dur = _probe_duration(landing)
    plan.append(
        {
            "id": "landing",
            "src": landing,
            "start": 0.15,
            "end": max(landing_dur - 0.1, 3.8),
            "zoom": 1.1,
            "fx": 0.42,
            "fy": 0.4,
        }
    )

    a, b = seg("overview_in", "overview_out")
    plan.append({"id": "overview", "src": session, "start": a, "end": b, "zoom": 1.08, "fx": 0.55, "fy": 0.42})

    a, b = seg("profile_in", "profile_out")
    plan.append({"id": "profile", "src": session, "start": a, "end": b, "zoom": 1.07, "fx": 0.48, "fy": 0.4})

    a, b = seg("discover_in", "discover_out")
    dx, dy = _focus_from_markers(markers, "discover_zoom", (0.72, 0.38))
    plan.append({"id": "discover", "src": session, "start": a, "end": b, "zoom": 1.14, "fx": dx, "fy": dy})

    a, b = seg("evidence_in", "evidence_out")
    ex, ey = _focus_from_markers(markers, "evidence_zoom", (0.62, 0.45))
    plan.append({"id": "evidence", "src": session, "start": a, "end": b, "zoom": 1.24, "fx": ex, "fy": ey})

    a, b = seg("prepare_in", "prepare_out")
    px, py = _focus_from_markers(markers, "prepare_zoom", (0.55, 0.5))
    plan.append({"id": "prepare", "src": session, "start": a, "end": b, "zoom": 1.1, "fx": px, "fy": py})

    a, b = seg("track_in", "track_out")
    plan.append({"id": "track", "src": session, "start": a, "end": b, "zoom": 1.06, "fx": 0.5, "fy": 0.4})

    a, b = seg("analytics_in", "analytics_out")
    plan.append({"id": "analytics", "src": session, "start": a, "end": b, "zoom": 1.08, "fx": 0.5, "fy": 0.42})

    a, b = seg("extension_in", "extension_out")
    plan.append({"id": "extension", "src": session, "start": a, "end": b, "zoom": 1.05, "fx": 0.55, "fy": 0.45})

    a, b = seg("closing_in", "end", 0.05, 0.0)
    # Hold the closing plate longer for readable kinetic type
    plan.append(
        {
            "id": "closing",
            "src": session,
            "start": a,
            "end": b,
            "zoom": 1.12,
            "fx": 0.5,
            "fy": 0.4,
            "dim": True,
            "pad": 3.2,
        }
    )

    cut_paths: list[Path] = []
    timeline = 0.0
    callout_events: list[tuple[float, float, str]] = []

    callout_events.append(
        (0.2, 2.8, "Dialogue: 0,{START},{END},Hook,,0,0,0,,{\\fad(160,240)}CareerPilot")
    )
    callout_events.append(
        (
            0.65,
            3.1,
            "Dialogue: 0,{START},{END},HookSub,,0,0,0,,{\\fad(200,240)}Grounded job search · Human-approved applications",
        )
    )

    scene_copy = {
        "landing": None,
        "overview": ("Callout", "Profile-first workspace · synthetic demo data"),
        "profile": ("Callout", "Synthetic resume to grounded profile"),
        "discover": ("Callout", "Deterministic Fit — no LLM required"),
        "evidence": ("Callout", "Matched skills cited from stored evidence"),
        "prepare": ("Callout", "Drafts until you approve — never auto-submit"),
        "track": ("Callout", "Tracker organizes · applied is human-recorded"),
        "analytics": ("Callout", "Honest funnel — no invented offers"),
        "extension": ("Label", "Illustrative Fill boundary · not a live employer ATS"),
        "closing": None,
    }

    for item in plan:
        cid = str(item["id"])
        out = clips_dir / f"{cid}.mp4"
        _cut(
            Path(str(item["src"])),
            out,
            float(item["start"]),
            float(item["end"]),
            zoom_end=float(item["zoom"]),
            focus_x=float(item["fx"]),
            focus_y=float(item["fy"]),
        )
        if item.get("dim"):
            dimmed = clips_dir / f"{cid}-dim.mp4"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(out),
                    "-vf",
                    "drawbox=x=0:y=0:w=iw:h=ih:color=0x070412@0.62:t=fill,setsar=1",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "16",
                    "-pix_fmt",
                    "yuv420p",
                    str(dimmed),
                ]
            )
            out = dimmed
        pad = float(item.get("pad") or 0)
        if pad > 0:
            padded = clips_dir / f"{cid}-pad.mp4"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(out),
                    "-vf",
                    f"tpad=stop_mode=clone:stop_duration={pad:.2f},fps={FPS},setsar=1",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "16",
                    "-pix_fmt",
                    "yuv420p",
                    str(padded),
                ]
            )
            out = padded
        dur = _probe_duration(out)
        copy = scene_copy.get(cid)
        if copy:
            style, text = copy
            start = timeline + 0.4
            end = timeline + min(2.4, max(dur - 0.35, 1.0))
            if end > start + 0.7:
                safe = text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
                callout_events.append(
                    (
                        start,
                        end,
                        f"Dialogue: 0,{{START}},{{END}},{style},,0,0,0,,{{\\fad(140,260)}}{safe}",
                    )
                )
        if cid == "closing":
            callout_events.append(
                (
                    timeline + 0.15,
                    timeline + dur - 0.05,
                    "Dialogue: 0,{START},{END},CloseTitle,,0,0,0,,{\\fad(160,0)}CareerPilot",
                )
            )
            callout_events.append(
                (
                    timeline + 0.55,
                    timeline + dur - 0.05,
                    "Dialogue: 0,{START},{END},CloseSub,,0,0,0,,{\\fad(180,0)}FastAPI · React · SQLite · Chromium extension",
                )
            )
            callout_events.append(
                (
                    timeline + 0.95,
                    timeline + dur - 0.05,
                    "Dialogue: 0,{START},{END},CloseUrl,,0,0,0,,{\\fad(200,0)}github.com/ManpreetS2/CareerPilot",
                )
            )
        timeline += dur
        cut_paths.append(out)

    concat_path = work / "concat.mp4"
    _xfade_concat(cut_paths, concat_path, fade=0.3)

    raw_sum = sum(_probe_duration(p) for p in cut_paths)
    final_dur = _probe_duration(concat_path)
    scale = final_dur / raw_sum if raw_sum else 1.0
    scaled_events = [(start * scale, end * scale, text) for start, end, text in callout_events]

    ass_path = work / "callouts.ass"
    _write_ass(ass_path, scaled_events)
    burned = work / "final.mp4"
    _overlay_ass(concat_path, ass_path, burned)

    dur = _probe_duration(burned)
    if dur > 76.0:
        speed = dur / 72.0
        trimmed = work / "final-paced.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(burned),
                "-vf",
                f"setpts={1 / speed:.5f}*PTS,fps={FPS}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(trimmed),
            ]
        )
        burned = trimmed
    elif dur < 58:
        print(f"WARNING: short demo ({dur:.1f}s); consider longer holds", flush=True)

    _ = math
    return burned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--keep-work", type=Path, default=None, help="Persist work dir for debugging")
    args = parser.parse_args()
    base = validate_loopback_base_url(args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Preserve prior deliverable once if present and archive missing
    if DEFAULT_OUT.is_file() and not ARCHIVE_OUT.is_file():
        shutil.copy(DEFAULT_OUT, ARCHIVE_OUT)
        print(f"Archived previous demo to {ARCHIVE_OUT}", flush=True)

    tmp_ctx = (
        tempfile.TemporaryDirectory(prefix="careerpilot-demo-v2-")
        if args.keep_work is None
        else None
    )
    work = Path(args.keep_work) if args.keep_work else Path(tmp_ctx.name)  # type: ignore[union-attr]
    work.mkdir(parents=True, exist_ok=True)

    try:
        print("Bootstrapping dark-theme session…", flush=True)
        state = _bootstrap_storage(base, work)
        print("Recording guest landing…", flush=True)
        landing = _record_guest_landing(base, work)
        print(f"Landing: {landing} ({_probe_duration(landing):.1f}s)", flush=True)
        print("Recording authenticated session…", flush=True)
        session, markers = _record_session(base, work, state)
        print(f"Session: {session} ({_probe_duration(session):.1f}s)", flush=True)
        print("Editing timeline…", flush=True)
        final = _build_edit(landing, session, markers, work)
        shutil.copy(final, args.out)
        shutil.copy(final, ARTIFACT_OUT)
        # Copy markers for debugging alongside artifacts
        shutil.copy(work / "markers.json", Path("/opt/cursor/artifacts/demo-markers.json"))

        meta = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size,bit_rate",
                "-show_streams",
                "-select_streams",
                "v:0",
                "-of",
                "json",
                str(args.out),
            ],
            text=True,
        )
        info = json.loads(meta)
        duration = float(info["format"]["duration"])
        size = int(info["format"]["size"])
        stream = info["streams"][0]
        br = int(info["format"].get("bit_rate") or 0)
        print(
            f"Wrote {args.out} and {ARTIFACT_OUT}\n"
            f"  {duration:.1f}s · {size/1024/1024:.1f} MB · "
            f"{stream.get('width')}x{stream.get('height')} · "
            f"{br/1000:.0f} kbps · {FPS}fps"
        )
        if duration < 58 or duration > 78:
            print(f"WARNING: duration {duration:.1f}s outside ~60–75s target", file=sys.stderr)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

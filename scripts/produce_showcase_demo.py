#!/usr/bin/env python3
"""Record and assemble the CareerPilot portfolio demo video.

Uses the isolated synthetic showcase account against a loopback frontend.
Does not click Submit, fill EEO fields, or touch data/careerpilot.db.
Extension footage uses the local illustrative ATS fixture — labeled as such.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
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
from scripts.seed_showcase_demo import (  # noqa: E402
    SHOWCASE_EMAIL,
    SHOWCASE_PASSWORD,
    SHOWCASE_PRIMARY_JOB,
)

FIXTURE = ROOT / "docs" / "showcase" / "fixtures" / "generic-ats-form.html"
DEFAULT_OUT = ROOT / "docs" / "showcase" / "video" / "careerpilot-demo.mp4"
ARTIFACT_OUT = Path("/opt/cursor/artifacts/careerpilot-demo.mp4")

# Scene timing (seconds). Target finished length ~95–110s including title cards.
SCENES: list[dict[str, object]] = [
    {
        "id": "title",
        "kind": "card",
        "duration": 4.5,
        "title": "CareerPilot",
        "subtitle": "Grounded job search · Human-approved applications",
        "caption": "Local / self-hostable portfolio project",
    },
    {
        "id": "profile",
        "kind": "browser",
        "path": "/profile",
        "duration": 10,
        "caption": "Synthetic resume to grounded candidate profile",
        "wait_for": "Jordan Avery",
    },
    {
        "id": "discover",
        "kind": "browser",
        "path": "/jobs",
        "duration": 12,
        "caption": "Discover ranks jobs with deterministic Fit — no LLM required",
        "select_harborline": True,
        "wait_for": "Harborline Analytics",
    },
    {
        "id": "evidence",
        "kind": "browser",
        "path": f"/jobs/{SHOWCASE_PRIMARY_JOB}",
        "duration": 16,
        "caption": "Explainable Fit: matched skills cited from stored evidence",
        "open_python_evidence": True,
        "wait_for": "Evidence",
    },
    {
        "id": "prepare",
        "kind": "browser",
        "path": f"/jobs/{SHOWCASE_PRIMARY_JOB}/prepare",
        "duration": 12,
        "caption": "Application materials stay drafts until human approval",
        "scroll_cover": True,
        "wait_for": "Cover letter",
    },
    {
        "id": "track",
        "kind": "browser",
        "path": "/track",
        "duration": 8,
        "caption": "Tracker organizes work — applied is human-recorded only",
        "click_list": True,
        "wait_for": "List",
    },
    {
        "id": "analytics",
        "kind": "browser",
        "path": "/analytics",
        "duration": 8,
        "caption": "Analytics stay honest: no invented interviews or offers",
        "wait_for": None,
    },
    {
        "id": "extension",
        "kind": "fixture",
        "duration": 12,
        "caption": "Illustrative Fill boundary — EEO/Submit stay manual (not live ATS)",
    },
    {
        "id": "closing",
        "kind": "card",
        "duration": 6,
        "title": "CareerPilot",
        "subtitle": "FastAPI · React · SQLite · Chromium extension",
        "caption": "github.com/ManpreetS2/CareerPilot",
    },
]


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def _make_title_card(
    path: Path,
    *,
    title: str,
    subtitle: str,
    caption: str,
    duration: float,
    width: int,
    height: int,
    fps: int,
) -> None:
    # Dark violet identity matching CareerPilot branding.
    vf = (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x1a0f33@0.55:t=fill,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"text='{title}':fontsize=72:fontcolor=0xf3e8ff:x=(w-text_w)/2:y=(h/2)-90,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        f"text='{subtitle}':fontsize=28:fontcolor=0xc4b5fd:x=(w-text_w)/2:y=(h/2)+10,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        f"text='{caption}':fontsize=22:fontcolor=0xa78bfa:x=(w-text_w)/2:y=(h/2)+70"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0b0618:s={width}x{height}:d={duration}:r={fps}",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-t",
            str(duration),
            str(path),
        ]
    )


def _burn_caption(src: Path, dst: Path, caption: str, fps: int) -> None:
    escaped = (
        caption.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("→", "-")
    )
    vf = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b0618,"
        f"fps={fps},"
        f"drawbox=x=40:y=ih-110:w=iw-80:h=70:color=0x0b0618@0.72:t=fill,"
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        f"text='{escaped}':fontsize=28:fontcolor=0xf3e8ff:"
        f"x=70:y=h-88"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "20",
            str(dst),
        ]
    )


def _record_browser_scenes(
    *,
    base: str,
    work: Path,
    width: int,
    height: int,
) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    outputs: dict[str, Path] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Identity check once (no video retention needed).
        probe_ctx = browser.new_context(viewport={"width": width, "height": height})
        probe_page = probe_ctx.new_page()
        collected: dict[str, object] = {}
        _record_identity_payloads(probe_page, collected)
        probe_page.goto(f"{base}/login", wait_until="networkidle")
        probe_page.get_by_label("Email").fill(SHOWCASE_EMAIL)
        probe_page.get_by_label("Password").fill(SHOWCASE_PASSWORD)
        probe_page.get_by_role("button", name="Log in").click()
        probe_page.wait_for_function(
            "() => !location.pathname.includes('/login')", timeout=20000
        )
        probe_page.goto(f"{base}/jobs", wait_until="networkidle")
        probe_page.wait_for_timeout(500)
        email, name, job_ids, companies = _identity_from_collected(collected)
        require_showcase_identity(email=email, name=name, job_ids=job_ids, companies=companies)
        probe_ctx.close()

        for scene in SCENES:
            if scene["kind"] not in {"browser", "fixture"}:
                continue
            context = browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=str(work / "raw"),
                record_video_size={"width": width, "height": height},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.emulate_media(reduced_motion="reduce")
            page.goto(f"{base}/login", wait_until="networkidle")
            page.get_by_label("Email").fill(SHOWCASE_EMAIL)
            page.get_by_label("Password").fill(SHOWCASE_PASSWORD)
            page.get_by_role("button", name="Log in").click()
            page.wait_for_function(
                "() => !location.pathname.includes('/login')", timeout=20000
            )

            scene_id = str(scene["id"])
            duration_ms = int(float(scene["duration"]) * 1000)

            if scene["kind"] == "fixture":
                page.goto(FIXTURE.resolve().as_uri(), wait_until="networkidle")
                page.wait_for_timeout(duration_ms)
            else:
                page.goto(f"{base}{scene['path']}", wait_until="networkidle")
                wait_for = scene.get("wait_for")
                if isinstance(wait_for, str) and wait_for:
                    page.get_by_text(wait_for, exact=False).first.wait_for(timeout=15000)
                if scene.get("select_harborline"):
                    page.get_by_role(
                        "button",
                        name="Select Software Engineer Intern at Harborline Analytics",
                    ).click()
                    page.wait_for_timeout(400)
                if scene.get("open_python_evidence"):
                    page.get_by_role("tab", name="Evidence").click()
                    page.get_by_test_id("match-evidence").wait_for()
                    python_factor = (
                        page.get_by_test_id("evidence-section-required_skills")
                        .locator('[data-testid^="factor-factor_skill_required_"]')
                        .filter(has_text="Python")
                        .first
                    )
                    python_factor.get_by_role("button", name="View evidence").click()
                    page.get_by_test_id("evidence-drawer").get_by_text(
                        "Candidate evidence", exact=True
                    ).wait_for()
                    page.wait_for_timeout(800)
                if scene.get("scroll_cover"):
                    page.get_by_role("heading", name="Cover letter").wait_for()
                    page.get_by_role("heading", name="Cover letter").evaluate(
                        "el => el.scrollIntoView({ block: 'start', inline: 'nearest' })"
                    )
                if scene.get("click_list"):
                    page.get_by_role("button", name="List").click()
                page.wait_for_timeout(duration_ms)

            video = page.video
            page.close()
            assert video is not None
            raw_path = Path(video.path())
            context.close()
            dest = work / "clips" / f"{scene_id}.webm"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(raw_path), str(dest))
            outputs[scene_id] = dest

        browser.close()
    return outputs


def _concat(clips: list[Path], out: Path, fps: int) -> None:
    listing = out.parent / "concat.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
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
            "-vf",
            f"fps={fps},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-movflags",
            "+faststart",
            "-an",
            str(out),
        ]
    )


def _crossfade_concat(clips: list[Path], out: Path, fps: int, fade: float = 0.4) -> None:
    """Soft xfade between clips when lengths allow; falls back to hard concat."""
    if len(clips) < 2:
        shutil.copy(clips[0], out)
        return
    # Probe durations
    durations: list[float] = []
    for clip in clips:
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(clip),
            ],
            text=True,
        )
        durations.append(float(json.loads(probe)["format"]["duration"]))

    inputs: list[str] = []
    for clip in clips:
        inputs.extend(["-i", str(clip)])

    # Build filter: [0][1]xfade... chain
    filter_parts: list[str] = []
    current = "[0:v]"
    offset = 0.0
    for i in range(1, len(clips)):
        offset += max(durations[i - 1] - fade, 0.05)
        out_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{current}[{i}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}{out_label}"
        )
        current = out_label if i < len(clips) - 1 else "[vout]"
        # After xfade, cumulative timeline length is offset + duration of next - fade handled by offset
        # Adjust stored duration for next offset calculation: result length ≈ offset + durations[i]
        durations[i] = durations[i]  # noqa: B018 — kept for clarity; offset uses prior clip lengths

    # Recalculate offsets more carefully for chained xfade
    filter_parts = []
    current = "[0:v]"
    timeline = 0.0
    for i in range(1, len(clips)):
        timeline += max(durations[i - 1] - fade, 0.05)
        out_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{current}[{i}:v]xfade=transition=fade:duration={fade}:offset={timeline:.3f}{out_label}"
        )
        current = out_label

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[vout]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "22",
        "-r",
        str(fps),
        "-movflags",
        "+faststart",
        "-an",
        str(out),
    ]
    try:
        _run(cmd)
    except subprocess.CalledProcessError:
        print("xfade failed; falling back to hard concat", flush=True)
        _concat(clips, out, fps)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    base = validate_loopback_base_url(args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_OUT.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="careerpilot-demo-") as tmp:
        work = Path(tmp)
        (work / "clips").mkdir()
        (work / "raw").mkdir()
        (work / "cards").mkdir()
        (work / "captioned").mkdir()

        browser_clips = _record_browser_scenes(
            base=base, work=work, width=args.width, height=args.height
        )

        ordered: list[Path] = []
        for scene in SCENES:
            scene_id = str(scene["id"])
            caption = str(scene["caption"])
            if scene["kind"] == "card":
                card = work / "cards" / f"{scene_id}.mp4"
                _make_title_card(
                    card,
                    title=str(scene["title"]),
                    subtitle=str(scene["subtitle"]),
                    caption=caption,
                    duration=float(scene["duration"]),
                    width=args.width,
                    height=args.height,
                    fps=args.fps,
                )
                ordered.append(card)
                continue

            raw = browser_clips[scene_id]
            captioned = work / "captioned" / f"{scene_id}.mp4"
            _burn_caption(raw, captioned, caption, args.fps)
            # Trim to intended duration (Playwright may record a bit longer due to login).
            trimmed = work / "captioned" / f"{scene_id}-trim.mp4"
            duration = float(scene["duration"])
            # Keep the end of the clip where the feature is visible (after login).
            probe = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(captioned),
                ],
                text=True,
            )
            total = float(json.loads(probe)["format"]["duration"])
            start = max(total - duration - 0.3, 0)
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{start:.2f}",
                    "-i",
                    str(captioned),
                    "-t",
                    f"{duration:.2f}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(trimmed),
                ]
            )
            ordered.append(trimmed)

        final = work / "final.mp4"
        _crossfade_concat(ordered, final, args.fps)
        shutil.copy(final, args.out)
        shutil.copy(final, ARTIFACT_OUT)
        probe = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-show_streams",
                "-select_streams",
                "v:0",
                "-of",
                "json",
                str(args.out),
            ],
            text=True,
        )
        meta = json.loads(probe)
        duration = float(meta["format"]["duration"])
        size = int(meta["format"]["size"])
        stream = meta["streams"][0]
        print(
            f"Wrote {args.out} and {ARTIFACT_OUT} "
            f"({duration:.1f}s, {size // 1024} KB, "
            f"{stream.get('width')}x{stream.get('height')} @ {args.fps}fps)"
        )
        if duration < 75 or duration > 120:
            print(
                f"WARNING: duration {duration:.1f}s outside 75–120s target",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

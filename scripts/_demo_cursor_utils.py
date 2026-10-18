"""Mouse tracking + ASS cursor burn helpers for showcase demo video."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def ease_points(x0: float, y0: float, x1: float, y1: float, steps: int) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)
        pts.append((x0 + (x1 - x0) * e, y0 + (y1 - y0) * e))
    return pts


class MouseTracker:
    def __init__(self, t0: float) -> None:
        self.t0 = t0
        self.x = 120.0
        self.y = 120.0
        self.log: list[dict[str, float | bool]] = []

    def _stamp(self, *, down: bool = False) -> None:
        import time

        self.log.append(
            {
                "t": round(time.monotonic() - self.t0, 4),
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "down": down,
            }
        )

    def move(self, page, x: float, y: float, *, steps: int = 28) -> None:
        for nx, ny in ease_points(self.x, self.y, x, y, steps):
            page.mouse.move(nx, ny)
            self.x, self.y = nx, ny
            page.evaluate(
                "(p) => { if (window.__cpMoveCursor) window.__cpMoveCursor(p[0], p[1]); }",
                [nx, ny],
            )
            self._stamp(down=False)
            page.wait_for_timeout(14)
        page.mouse.move(x, y)
        self.x, self.y = x, y
        page.evaluate(
            "(p) => { if (window.__cpMoveCursor) window.__cpMoveCursor(p[0], p[1]); }",
            [x, y],
        )
        self._stamp(down=False)

    def click_locator(self, page, locator, *, steps: int = 28) -> None:
        locator.wait_for(state="visible", timeout=15000)
        box = locator.bounding_box()
        if not box:
            locator.click()
            return
        x = box["x"] + box["width"] * 0.55
        y = box["y"] + box["height"] * 0.5
        self.move(page, x, y, steps=steps)
        page.wait_for_timeout(100)
        page.mouse.down()
        self._stamp(down=True)
        page.wait_for_timeout(80)
        page.mouse.up()
        self._stamp(down=False)
        page.wait_for_timeout(160)

    def scroll_by(self, page, dy: int, *, ticks: int = 8) -> None:
        for _ in range(ticks):
            page.mouse.wheel(0, dy // ticks)
            self._stamp(down=False)
            page.wait_for_timeout(70)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.log), encoding="utf-8")


def _interp(log: list[dict[str, float | bool]], t: float) -> tuple[float, float, bool]:
    if not log:
        return 120.0, 120.0, False
    if t <= float(log[0]["t"]):
        return float(log[0]["x"]), float(log[0]["y"]), bool(log[0]["down"])
    if t >= float(log[-1]["t"]):
        return float(log[-1]["x"]), float(log[-1]["y"]), bool(log[-1]["down"])
    for i in range(1, len(log)):
        a, b = log[i - 1], log[i]
        ta, tb = float(a["t"]), float(b["t"])
        if ta <= t <= tb:
            u = 0 if tb == ta else (t - ta) / (tb - ta)
            x = float(a["x"]) + (float(b["x"]) - float(a["x"])) * u
            y = float(a["y"]) + (float(b["y"]) - float(a["y"])) * u
            return x, y, bool(b["down"])
    return float(log[-1]["x"]), float(log[-1]["y"]), bool(log[-1]["down"])


def write_cursor_ass(
    path: Path,
    log: list[dict[str, float | bool]],
    *,
    duration: float,
    src_w: int,
    src_h: int,
    fps: int = 30,
) -> None:
    """Write a dense ASS track that paints a cursor glyph each frame."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {src_w}
PlayResY: {src_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cursor,DejaVu Sans,54,&H00FFFFFF,&H000000FF,&H00A78BFA,&H00000000,0,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1
Style: CursorDown,DejaVu Sans,42,&H00F5F3FF,&H000000FF,&H00C4B5FD,&H00000000,0,0,0,0,100,100,0,0,1,4,0,5,0,0,0,1

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
    n = max(int(duration * fps) + 1, 1)
    for i in range(n):
        t = i / fps
        x, y, down = _interp(log, t)
        style = "CursorDown" if down else "Cursor"
        # ASS \pos is baseline-ish; nudge so the glyph centers on tip
        lines.append(
            f"Dialogue: 0,{ts(t)},{ts(t + 1 / fps + 0.001)},{style},,0,0,0,,"
            f"{{\\pos({x:.1f},{y:.1f})}}●"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def burn_cursor(
    src: Path,
    dst: Path,
    log: list[dict[str, float | bool]],
    *,
    src_w: int,
    src_h: int,
    fps: int = 30,
) -> None:
    probe = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(src),
        ],
        text=True,
    )
    duration = float(json.loads(probe)["format"]["duration"])
    ass = dst.with_suffix(".cursor.ass")
    write_cursor_ass(ass, log, duration=duration, src_w=src_w, src_h=src_h, fps=fps)
    ass_esc = str(ass).replace("\\", "/").replace(":", "\\:")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"ass='{ass_esc}',fps={fps},format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            str(dst),
        ],
        check=True,
    )

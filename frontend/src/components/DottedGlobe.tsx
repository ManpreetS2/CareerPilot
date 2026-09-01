import { useEffect, useRef } from "react";
import {
  GLOBE_HOLD_MS,
  GLOBE_LATITUDES,
  GLOBE_MERIDIANS,
  GLOBE_REV_MS,
  GLOBE_SETTLE_MS,
  GLOBE_TRAVEL_MS,
  activeNodeIndex,
  advanceCometPhase,
  buildGlobeDots,
  cometTrailPoints,
  createHoldPhase,
  globeLayout,
  isFrontFacing,
  projectNodes,
  projectSphere,
  type CometPhase,
  type GlobeDot,
} from "../lib/globe-engine";
import { useTheme } from "../lib/theme";

type LoopHandles = {
  frame: number;
  observer: IntersectionObserver | null;
};

function cssColor(name: string, fallback: string) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function drawGlobe(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  lonOffset: number,
  phase: CometPhase,
  dots: GlobeDot[],
  compact: boolean,
  reducedMotion: boolean,
) {
  const { diameter, radius, cx, cy } = globeLayout(width, height, compact);
  const accent = cssColor("--accent", "#c084fc");
  const core = cssColor("--hole-core", "#ffffff");

  ctx.clearRect(0, 0, width, height);

  ctx.save();
  ctx.globalAlpha = compact ? 0.18 : 0.28;
  ctx.fillStyle = core;
  for (let i = 0; i < 28; i++) {
    const x = ((i * 97) % width) + 8;
    const y = ((i * 53) % Math.max(24, height * 0.45)) + 6;
    ctx.beginPath();
    ctx.arc(x, y, i % 4 === 0 ? 1.1 : 0.55, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.clip();

  const glow = ctx.createRadialGradient(cx, cy - radius * 0.42, radius * 0.08, cx, cy, radius);
  glow.addColorStop(0, "rgba(192, 132, 252, 0.22)");
  glow.addColorStop(1, "rgba(192, 132, 252, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(cx - radius, cy - radius, diameter, diameter);

  ctx.strokeStyle = core;
  ctx.globalAlpha = compact ? 0.18 : 0.28;
  ctx.lineWidth = compact ? 0.8 : 1.15;
  ctx.beginPath();
  ctx.arc(cx, cy, radius, Math.PI + 0.22, -0.22, false);
  ctx.stroke();

  ctx.strokeStyle = accent;
  ctx.lineWidth = compact ? 0.45 : 0.7;
  for (const lat of GLOBE_LATITUDES) {
    ctx.beginPath();
    let started = false;
    for (let i = 0; i <= 72; i++) {
      const lon = (i / 72) * 360 - 180;
      const point = projectSphere(lat, lon, lonOffset, radius);
      if (!isFrontFacing(point.z, radius, 0.02)) {
        started = false;
        continue;
      }
      const x = cx + point.x;
      const y = cy + point.y;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else ctx.lineTo(x, y);
    }
    ctx.globalAlpha = 0.16;
    ctx.stroke();
  }

  for (const lon of GLOBE_MERIDIANS) {
    ctx.beginPath();
    let started = false;
    for (let i = 0; i <= 40; i++) {
      const lat = 6 + (i / 40) * 80;
      const point = projectSphere(lat, lon, lonOffset, radius);
      if (!isFrontFacing(point.z, radius, 0.02)) {
        started = false;
        continue;
      }
      const x = cx + point.x;
      const y = cy + point.y;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else ctx.lineTo(x, y);
    }
    ctx.globalAlpha = 0.1;
    ctx.stroke();
  }

  ctx.fillStyle = compact ? accent : core;
  for (const dot of dots) {
    const point = projectSphere(dot.lat, dot.lon, lonOffset, radius);
    if (!isFrontFacing(point.z, radius, 0.02)) continue;
    const depth = (point.z / radius + 1) / 2;
    ctx.globalAlpha = (compact ? 0.12 : 0.2) + depth * (compact ? 0.4 : 0.72);
    const size = dot.size * (compact ? 0.62 : 1) * (0.62 + depth * 0.55);
    ctx.beginPath();
    ctx.arc(cx + point.x, cy + point.y, size, 0, Math.PI * 2);
    ctx.fill();
  }

  const nodes = projectNodes(lonOffset, radius);
  const active = activeNodeIndex(phase);
  for (const node of nodes) {
    if (!node.visible) continue;
    const isActive = node.index === active;
    const fading = phase.kind === "settle" && node.index === phase.from;
    if (compact && !isActive) continue;
    ctx.beginPath();
    ctx.arc(cx + node.x, cy + node.y, isActive ? (compact ? 3 : 4.4) : 2.2, 0, Math.PI * 2);
    ctx.fillStyle = isActive ? core : accent;
    ctx.globalAlpha = isActive ? 1 : fading ? 0.28 : 0.2;
    ctx.fill();
    if (isActive) {
      ctx.beginPath();
      ctx.arc(cx + node.x, cy + node.y, compact ? 6 : 8, 0, Math.PI * 2);
      ctx.globalAlpha = compact ? 0.14 : 0.22;
      ctx.fill();
    }
  }

  if (!reducedMotion && !compact && phase.kind === "travel") {
    const from = nodes[phase.from];
    const to = nodes[phase.to];
    if (from?.visible && to?.visible) {
      const trail = cometTrailPoints(
        { x: cx + from.x, y: cy + from.y },
        { x: cx + to.x, y: cy + to.y },
        phase.progress,
      );
      for (const spark of trail.trail) {
        ctx.beginPath();
        ctx.arc(spark.x, spark.y, spark.r, 0, Math.PI * 2);
        ctx.fillStyle = core;
        ctx.globalAlpha = spark.o;
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(trail.head.x, trail.head.y, 3.1, 0, Math.PI * 2);
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = core;
      ctx.fill();
    }
  }

  ctx.restore();
}

export function WorldPulseGlobe({
  className = "",
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { reducedMotion } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dotsRef = useRef<GlobeDot[]>(buildGlobeDots(compact));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const handles: LoopHandles = { frame: 0, observer: null };
    let visible = true;
    let pageVisible = typeof document === "undefined" ? true : document.visibilityState !== "hidden";
    let lonOffset = compact ? 28 : 18;
    let phase: CometPhase = createHoldPhase(0);
    let last = 0;
    const dots = dotsRef.current;

    const cssSize = () => {
      const parent = canvas.parentElement;
      return {
        width: parent?.clientWidth || (compact ? 280 : 1100),
        height: parent?.clientHeight || (compact ? 220 : 576),
      };
    };

    const paint = () => {
      const { width, height } = cssSize();
      drawGlobe(ctx, width, height, lonOffset, phase, dots, compact, reducedMotion);
    };

    const resize = () => {
      const { width, height } = cssSize();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      paint();
    };

    const stop = () => {
      if (handles.frame) {
        cancelAnimationFrame(handles.frame);
        handles.frame = 0;
      }
      last = 0;
    };

    const tick = (now: number) => {
      handles.frame = 0;
      if (!visible || !pageVisible || reducedMotion) {
        paint();
        return;
      }
      if (!last) last = now;
      const dt = Math.min(48, now - last);
      last = now;
      lonOffset = (lonOffset + (dt / GLOBE_REV_MS) * 360) % 360;
      if (!compact) {
        const { radius } = globeLayout(cssSize().width, cssSize().height, compact);
        const nodes = projectNodes(lonOffset, radius);
        phase = advanceCometPhase(phase, dt, nodes, {
          holdMs: GLOBE_HOLD_MS,
          travelMs: GLOBE_TRAVEL_MS,
          settleMs: GLOBE_SETTLE_MS,
        });
      }
      paint();
      handles.frame = requestAnimationFrame(tick);
    };

    const start = () => {
      if (reducedMotion || handles.frame) return;
      last = 0;
      handles.frame = requestAnimationFrame(tick);
    };

    const syncLoop = () => {
      if (visible && pageVisible && !reducedMotion) start();
      else {
        stop();
        paint();
      }
    };

    resize();
    const onResize = () => resize();
    window.addEventListener("resize", onResize);
    const onVisibility = () => {
      pageVisible = document.visibilityState !== "hidden";
      syncLoop();
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (typeof IntersectionObserver !== "undefined") {
      handles.observer = new IntersectionObserver((entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
        syncLoop();
      });
      handles.observer.observe(canvas);
    }
    syncLoop();

    return () => {
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
      handles.observer?.disconnect();
    };
  }, [compact, reducedMotion]);

  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`} aria-hidden data-testid="dotted-globe">
      <div
        className="pointer-events-none absolute inset-x-[10%] bottom-[-20%] h-[80%] opacity-70 blur-3xl"
        style={{ background: "radial-gradient(circle at 50% 40%, var(--halo), transparent 68%)" }}
      />
      <canvas ref={canvasRef} className="relative h-full w-full" />
    </div>
  );
}

export const DottedGlobe = WorldPulseGlobe;

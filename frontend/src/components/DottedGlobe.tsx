import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "../lib/theme";

type Dot = { x: number; y: number; z: number; opacity: number };

const SIZE = 360;
const CX = 180;
const CY = 180;
const RADIUS = 132;
const NODE_COUNT = 7;
const HOLD_MS = 4200;
const TRAVEL_MS = 1400;

function projectDots(): Dot[] {
  const dots: Dot[] = [];
  const lonSteps = 28;
  const latSteps = 16;
  for (let i = 0; i < lonSteps; i++) {
    for (let j = 0; j < latSteps; j++) {
      const lat = ((j / (latSteps - 1)) * 140 - 70) * (Math.PI / 180);
      const lon = ((i / lonSteps) * 360 - 180) * (Math.PI / 180);
      const x = CX + RADIUS * Math.cos(lat) * Math.sin(lon);
      const y = CY - RADIUS * Math.sin(lat);
      const z = RADIUS * Math.cos(lat) * Math.cos(lon);
      if (z < -18) continue;
      dots.push({
        x,
        y,
        z,
        opacity: 0.16 + ((z + RADIUS) / (RADIUS * 2)) * 0.55,
      });
    }
  }
  return dots;
}

function pickNodes(dots: Dot[]): number[] {
  const visible = dots
    .map((dot, index) => ({ index, score: dot.z + Math.abs(dot.x - CX) * 0.15 }))
    .sort((a, b) => b.score - a.score);
  const chosen: number[] = [];
  for (const item of visible) {
    if (chosen.length >= NODE_COUNT) break;
    const candidate = dots[item.index];
    if (!candidate) continue;
    const far = chosen.every((idx) => {
      const other = dots[idx];
      if (!other) return false;
      const dx = candidate.x - other.x;
      const dy = candidate.y - other.y;
      return dx * dx + dy * dy > 48 * 48;
    });
    if (far) chosen.push(item.index);
  }
  return chosen;
}

function quadPoint(from: Dot, to: Dot, t: number) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - 28;
  const x = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * mx + t * t * to.x;
  const y = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * my + t * t * to.y;
  return { x, y };
}

function cometPath(from: Dot, to: Dot) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - 28;
  return `M ${from.x} ${from.y} Q ${mx} ${my} ${to.x} ${to.y}`;
}

export function WorldPulseGlobe({
  className = "",
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { reducedMotion } = useTheme();
  const dots = useMemo(projectDots, []);
  const nodes = useMemo(() => pickNodes(dots), [dots]);
  const [active, setActive] = useState(0);
  const [previous, setPrevious] = useState(0);
  const [progress, setProgress] = useState(1);
  const travelRef = useRef<number | null>(null);

  useEffect(() => {
    if (reducedMotion || nodes.length < 2) return;
    const tick = window.setInterval(() => {
      setActive((current) => {
        const next = (current + 1) % nodes.length;
        setPrevious(current);
        setProgress(0);
        const started = performance.now();
        if (travelRef.current) cancelAnimationFrame(travelRef.current);
        const step = (now: number) => {
          const t = Math.min(1, (now - started) / TRAVEL_MS);
          setProgress(t);
          if (t < 1) travelRef.current = requestAnimationFrame(step);
        };
        travelRef.current = requestAnimationFrame(step);
        return next;
      });
    }, HOLD_MS);
    return () => {
      window.clearInterval(tick);
      if (travelRef.current) cancelAnimationFrame(travelRef.current);
    };
  }, [nodes.length, reducedMotion]);

  const from = dots[nodes[previous] ?? 0];
  const to = dots[nodes[active] ?? 0];
  const head = from && to ? quadPoint(from, to, progress) : null;
  const traveling = !reducedMotion && progress < 1 && from && to;

  return (
    <div className={`relative flex items-center justify-center ${className}`} aria-hidden>
      <div
        className="pointer-events-none absolute inset-0 opacity-70 blur-3xl"
        style={{
          background: "radial-gradient(circle at 50% 58%, var(--halo), transparent 62%)",
        }}
      />
      <svg
        width={compact ? 280 : SIZE}
        height={compact ? 280 : SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="relative text-primary"
      >
        <g
          style={{
            transformOrigin: `${CX}px ${CY}px`,
            animation: reducedMotion ? undefined : "rotate-slow 120s linear infinite",
          }}
        >
          <ellipse
            cx={CX}
            cy={CY}
            rx={RADIUS}
            ry={RADIUS * 0.28}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.4"
            opacity="0.22"
          />
          <circle
            cx={CX}
            cy={CY}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.45"
            opacity="0.2"
          />
          {dots.map((dot, index) => (
            <circle
              key={index}
              cx={dot.x}
              cy={dot.y}
              r={1.05}
              fill="currentColor"
              opacity={dot.opacity}
            />
          ))}
          {nodes.map((idx, i) => {
            const dot = dots[idx];
            if (!dot) return null;
            const isActive = i === active;
            const isPrev = i === previous && traveling;
            return (
              <circle
                key={`node-${idx}`}
                cx={dot.x}
                cy={dot.y}
                r={isActive ? 3.4 : 2.2}
                fill="currentColor"
                opacity={isActive ? 1 : isPrev ? 0.35 : 0.2}
                style={{
                  filter: isActive ? "drop-shadow(0 0 6px var(--halo))" : undefined,
                }}
              />
            );
          })}
          {from && to && traveling ? (
            <>
              <path
                d={cometPath(from, to)}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                opacity={0.55 * (1 - progress)}
                pathLength={1}
                strokeDasharray="0.28 0.72"
                strokeDashoffset={-progress}
              />
              {head ? (
                <circle cx={head.x} cy={head.y} r="3.1" fill="currentColor" opacity="0.95">
                  <animate attributeName="r" values="2.4;3.4;2.4" dur="0.9s" repeatCount="indefinite" />
                </circle>
              ) : null}
            </>
          ) : null}
        </g>
      </svg>
    </div>
  );
}

export const DottedGlobe = WorldPulseGlobe;

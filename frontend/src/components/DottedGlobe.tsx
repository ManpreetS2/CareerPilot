import { useEffect, useId, useMemo, useRef, useState } from "react";
import { CometArc } from "./CometArc";
import { useTheme } from "../lib/theme";

type Dot = { x: number; y: number; z: number; opacity: number };
type GeoNode = { lat: number; lon: number };

const FULL = { size: 560, radius: 208, lonSteps: 42, latSteps: 22 };
const COMPACT = { size: 300, radius: 112, lonSteps: 28, latSteps: 16 };
const HOLD_MS = 4600;
const TRAVEL_MS = 1600;
const REV_MS = 140000;

const NODES: GeoNode[] = [
  { lat: 40.7, lon: -74 },
  { lat: 51.5, lon: -0.1 },
  { lat: 35.7, lon: 139.7 },
  { lat: -33.9, lon: 151.2 },
  { lat: 1.3, lon: 103.8 },
  { lat: 19.1, lon: 72.9 },
  { lat: -23.5, lon: -46.6 },
  { lat: 52.5, lon: 13.4 },
];

function project(
  latDeg: number,
  lonDeg: number,
  lonOffset: number,
  cx: number,
  radius: number,
) {
  const lat = (latDeg * Math.PI) / 180;
  const lon = ((lonDeg + lonOffset) * Math.PI) / 180;
  const x = cx + radius * Math.cos(lat) * Math.sin(lon);
  const y = cx - radius * Math.sin(lat) * 0.94;
  const z = radius * Math.cos(lat) * Math.cos(lon);
  return { x, y, z };
}

function projectDots(lonOffset: number, size: number, radius: number, lonSteps: number, latSteps: number): Dot[] {
  const cx = size / 2;
  const dots: Dot[] = [];
  for (let i = 0; i < lonSteps; i++) {
    for (let j = 0; j < latSteps; j++) {
      const lat = (j / (latSteps - 1)) * 140 - 70;
      const lon = (i / lonSteps) * 360 - 180;
      const point = project(lat, lon, lonOffset, cx, radius);
      if (point.z < radius * 0.02) continue;
      dots.push({
        ...point,
        opacity: 0.22 + ((point.z + radius) / (radius * 2)) * 0.7,
      });
    }
  }
  return dots;
}

function latitudeRings(lonOffset: number, size: number, radius: number) {
  const cx = size / 2;
  const rings: string[] = [];
  for (const lat of [-48, -24, 0, 24, 48]) {
    let segment: string[] = [];
    for (let i = 0; i <= 48; i++) {
      const lon = (i / 48) * 360 - 180;
      const point = project(lat, lon, lonOffset, cx, radius);
      if (point.z > radius * 0.04) {
        segment.push(`${point.x.toFixed(1)},${point.y.toFixed(1)}`);
      } else if (segment.length > 1) {
        rings.push(segment.join(" "));
        segment = [];
      } else {
        segment = [];
      }
    }
    if (segment.length > 1) rings.push(segment.join(" "));
  }
  return rings;
}

export function WorldPulseGlobe({
  className = "",
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { reducedMotion } = useTheme();
  const uid = useId().replace(/:/g, "");
  const spec = compact ? COMPACT : FULL;
  const [lonOffset, setLonOffset] = useState(18);
  const [active, setActive] = useState(0);
  const [previous, setPrevious] = useState(0);
  const [progress, setProgress] = useState(1);
  const travelRef = useRef<number | null>(null);

  useEffect(() => {
    if (reducedMotion) return;
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      if (!last) last = now;
      if (now - last > 90) {
        setLonOffset((value) => (value + ((now - last) / REV_MS) * 360) % 360);
        last = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reducedMotion]);

  useEffect(() => {
    if (reducedMotion || NODES.length < 2) return;
    const interval = window.setInterval(() => {
      setActive((current) => {
        const next = (current + 1) % NODES.length;
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
      window.clearInterval(interval);
      if (travelRef.current) cancelAnimationFrame(travelRef.current);
    };
  }, [reducedMotion]);

  const dots = useMemo(
    () => projectDots(lonOffset, spec.size, spec.radius, spec.lonSteps, spec.latSteps),
    [lonOffset, spec.latSteps, spec.lonSteps, spec.radius, spec.size],
  );
  const rings = useMemo(
    () => latitudeRings(lonOffset, spec.size, spec.radius),
    [lonOffset, spec.radius, spec.size],
  );
  const cx = spec.size / 2;
  const projectedNodes = NODES.map((node) => {
    const point = project(node.lat, node.lon, lonOffset, cx, spec.radius);
    return { ...point, visible: point.z > spec.radius * 0.08 };
  });
  const from = projectedNodes[previous];
  const to = projectedNodes[active];
  const traveling =
    !reducedMotion && progress < 1 && from && to && from.z > -spec.radius * 0.18 && to.z > -spec.radius * 0.18;

  return (
    <div className={`relative flex h-full w-full items-center justify-center ${className}`} aria-hidden>
      <div
        className="pointer-events-none absolute inset-[8%] opacity-80 blur-3xl"
        style={{
          background: "radial-gradient(circle at 50% 58%, var(--halo), transparent 64%)",
        }}
      />
      <svg
        viewBox={`0 0 ${spec.size} ${spec.size}`}
        className={
          compact
            ? "relative h-[18rem] w-[18rem] text-accent"
            : "relative mx-auto aspect-square h-auto w-full max-h-full max-w-[40rem] text-accent"
        }
      >
        <defs>
          <radialGradient id={`cp-globe-limb-${uid}`} cx="38%" cy="34%" r="62%">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.08" />
            <stop offset="70%" stopColor="currentColor" stopOpacity="0.02" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`cp-comet-stroke-${uid}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#c084fc" stopOpacity="0" />
            <stop offset="50%" stopColor="#f5e9ff" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.2" />
          </linearGradient>
          <radialGradient id={`cp-comet-head-${uid}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="55%" stopColor="#e9d5ff" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#a855f7" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle cx={cx} cy={cx} r={spec.radius} fill={`url(#cp-globe-limb-${uid})`} />
        <ellipse
          cx={cx}
          cy={cx}
          rx={spec.radius}
          ry={spec.radius * 0.26}
          fill="none"
          stroke="currentColor"
          strokeWidth="0.45"
          opacity="0.22"
        />
        <circle cx={cx} cy={cx} r={spec.radius} fill="none" stroke="currentColor" strokeWidth="0.4" opacity="0.18" />
        {rings.map((points, index) => (
          <polyline
            key={`ring-${index}`}
            points={points}
            fill="none"
            stroke="currentColor"
            strokeWidth="0.35"
            strokeDasharray="1.6 3.4"
            opacity="0.28"
          />
        ))}
        {dots.map((dot, index) => (
          <circle key={index} cx={dot.x} cy={dot.y} r={compact ? 1.05 : 1.4} fill="currentColor" opacity={dot.opacity} />
        ))}
        {projectedNodes.map((node, index) => {
          if (!node.visible) return null;
          const isActive = index === active;
          const isPrev = index === previous && traveling;
          return (
            <circle
              key={`node-${index}`}
              cx={node.x}
              cy={node.y}
              r={isActive ? 4.1 : 2.3}
              fill={isActive ? "#ffffff" : "currentColor"}
              opacity={isActive ? 1 : isPrev ? 0.28 : 0.22}
              style={{
                filter: isActive ? "drop-shadow(0 0 8px var(--halo))" : undefined,
              }}
            />
          );
        })}
        {traveling && from && to ? (
          <CometArc
            from={from}
            to={to}
            progress={progress}
            strokeId={`cp-comet-stroke-${uid}`}
            headId={`cp-comet-head-${uid}`}
          />
        ) : null}
      </svg>
    </div>
  );
}

export const DottedGlobe = WorldPulseGlobe;

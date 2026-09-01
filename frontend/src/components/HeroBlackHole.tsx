import { useId } from "react";
import { useTheme } from "../lib/theme";

const RINGS = [
  { rx: 96, ry: 22, opacity: 0.95, width: 1.9 },
  { rx: 158, ry: 36, opacity: 0.74, width: 1.5 },
  { rx: 232, ry: 52, opacity: 0.52, width: 1.25 },
  { rx: 318, ry: 70, opacity: 0.36, width: 1.05 },
  { rx: 418, ry: 90, opacity: 0.24, width: 0.9 },
  { rx: 536, ry: 112, opacity: 0.14, width: 0.75 },
  { rx: 670, ry: 136, opacity: 0.08, width: 0.6 },
  { rx: 820, ry: 162, opacity: 0.05, width: 0.5 },
];

export function HeroBlackHole() {
  const { reducedMotion } = useTheme();
  const uid = useId().replace(/:/g, "");

  return (
    <div className="hero-blackhole" aria-hidden>
      <div className="hero-blackhole-bloom" />
      <div className="hero-blackhole-shimmer" />
      <div className="hero-blackhole-haze" />
      <svg className="hero-blackhole-svg" viewBox="0 0 1400 560" preserveAspectRatio="xMidYMax meet">
        <defs>
          <radialGradient id={`cp-hole-core-${uid}`} cx="50%" cy="48%" r="58%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="16%" stopColor="#fff7ff" stopOpacity="0.92" />
            <stop offset="38%" stopColor="#e9d5ff" stopOpacity="0.7" />
            <stop offset="58%" stopColor="#c084fc" stopOpacity="0.42" />
            <stop offset="82%" stopColor="#6d28d9" stopOpacity="0.14" />
            <stop offset="100%" stopColor="#4c1d95" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`cp-hole-ring-${uid}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#c084fc" stopOpacity="0" />
            <stop offset="35%" stopColor="#f5e9ff" stopOpacity="0.85" />
            <stop offset="50%" stopColor="#ffffff" stopOpacity="0.95" />
            <stop offset="65%" stopColor="#e9d5ff" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#7c3aed" stopOpacity="0" />
          </linearGradient>
          <filter id={`cp-hole-soft-${uid}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
        </defs>
        <ellipse
          className={reducedMotion ? undefined : "hero-blackhole-core"}
          cx="700"
          cy="470"
          rx="240"
          ry="62"
          fill={`url(#cp-hole-core-${uid})`}
          filter={`url(#cp-hole-soft-${uid})`}
        />
        <ellipse cx="700" cy="470" rx="48" ry="14" fill="#0a0614" opacity="0.92" />
        <ellipse cx="700" cy="470" rx="28" ry="8" fill="#ffffff" opacity="0.98" />
        {RINGS.map((ring, index) => (
          <ellipse
            key={ring.rx}
            className={reducedMotion ? undefined : "hero-blackhole-ring"}
            cx="700"
            cy="470"
            rx={ring.rx}
            ry={ring.ry}
            fill="none"
            stroke={`url(#cp-hole-ring-${uid})`}
            strokeWidth={ring.width}
            opacity={ring.opacity}
            style={{ animationDelay: `${index * 0.28}s` }}
          />
        ))}
      </svg>
    </div>
  );
}

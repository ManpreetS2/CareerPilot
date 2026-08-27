import { useMemo } from "react";
import { useTheme } from "../../lib/theme";

const NODES = [
  [8, 22],
  [18, 64],
  [29, 18],
  [41, 72],
  [52, 30],
  [63, 58],
  [74, 16],
  [82, 46],
  [91, 28],
  [14, 40],
  [36, 44],
  [58, 12],
  [70, 78],
  [86, 68],
];

const LINKS: Array<[number, number]> = [
  [0, 2],
  [2, 4],
  [4, 6],
  [6, 8],
  [1, 3],
  [3, 5],
  [5, 7],
  [10, 4],
  [10, 11],
  [7, 13],
  [9, 10],
  [11, 6],
];

export function IntelligenceField() {
  const { reducedMotion } = useTheme();
  const links = useMemo(() => LINKS, []);
  if (reducedMotion) return null;

  return (
    <div className="intelligence-field pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice" className="h-full w-full opacity-[0.28]">
        <defs>
          <linearGradient id="field-line" x1="0" x2="1">
            <stop offset="0%" stopColor="var(--primary)" />
            <stop offset="100%" stopColor="var(--accent)" />
          </linearGradient>
        </defs>
        <g className="origin-center" style={{ animation: "field-drift 18s var(--ease-standard) infinite alternate" }}>
          {links.map(([a, b]) => {
            const start = NODES[a];
            const end = NODES[b];
            if (!start || !end) return null;
            return (
            <line
              key={`${a}-${b}`}
              x1={start[0]}
              y1={start[1]}
              x2={end[0]}
              y2={end[1]}
              stroke="url(#field-line)"
              strokeWidth="0.18"
              opacity="0.55"
            />
            );
          })}
          {NODES.map(([x, y], index) => (
            <circle
              key={`${x}-${y}`}
              cx={x}
              cy={y}
              r={index % 4 === 0 ? 0.55 : 0.38}
              fill="var(--primary)"
              style={{ animation: `node-pulse ${7 + (index % 5)}s ease-in-out infinite` }}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}

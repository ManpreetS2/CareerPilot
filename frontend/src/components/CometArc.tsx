export type GlobePoint = { x: number; y: number };

function easeInOutCubic(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function quadPoint(from: GlobePoint, to: GlobePoint, t: number, lift: number) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - lift;
  return {
    x: (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * mx + t * t * to.x,
    y: (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * my + t * t * to.y,
  };
}

export function CometArc({
  from,
  to,
  progress,
  strokeId = "cp-comet-stroke",
  headId = "cp-comet-head",
}: {
  from: GlobePoint;
  to: GlobePoint;
  progress: number;
  strokeId?: string;
  headId?: string;
}) {
  const span = Math.hypot(to.x - from.x, to.y - from.y);
  const lift = 22 + span * 0.14;
  const t = easeInOutCubic(Math.min(1, Math.max(0, progress)));
  const head = quadPoint(from, to, t, lift);
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2 - lift;
  const fade = 1 - t;
  const trail = Array.from({ length: 9 }, (_, index) => {
    const behind = Math.max(0, t - index * 0.038);
    const point = quadPoint(from, to, behind, lift);
    return {
      ...point,
      r: Math.max(0.7, 2.6 - index * 0.2),
      o: (1 - index / 9) * fade * 0.7,
    };
  });

  return (
    <g>
      <path
        d={`M ${from.x} ${from.y} Q ${mx} ${my} ${to.x} ${to.y}`}
        fill="none"
        stroke={`url(#${strokeId})`}
        strokeWidth="1.2"
        strokeLinecap="round"
        opacity={0.32 * fade}
        pathLength={1}
        strokeDasharray="0.18 0.82"
        strokeDashoffset={-t}
      />
      {trail.map((point, index) => (
        <circle
          key={index}
          cx={point.x}
          cy={point.y}
          r={point.r}
          fill={`url(#${headId})`}
          opacity={point.o}
        />
      ))}
      <circle cx={head.x} cy={head.y} r="7" fill={`url(#${headId})`} opacity={0.22 * fade + 0.18} />
      <circle cx={head.x} cy={head.y} r="2.6" fill="#ffffff" opacity={0.95} />
    </g>
  );
}

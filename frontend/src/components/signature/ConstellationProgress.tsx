import { cn } from "../../lib/cn";

const NODES = ["Welcome", "Roles", "Resume", "Profile", "Type", "Place", "Finish"] as const;

export function ConstellationProgress({
  step,
  completed = false,
}: {
  step: number;
  completed?: boolean;
}) {
  const active = completed ? NODES.length : Math.min(Math.max(step, 1), NODES.length - 1);
  return (
    <div className="space-y-3" data-testid="onboarding-constellation">
      <svg viewBox="0 0 560 56" className="h-14 w-full" role="img" aria-label={`Setup step ${active} of ${NODES.length}`}>
        <defs>
          <linearGradient id="constellation-grad" x1="0" x2="1">
            <stop offset="0%" stopColor="var(--primary)" />
            <stop offset="100%" stopColor="var(--accent)" />
          </linearGradient>
        </defs>
        {NODES.slice(0, -1).map((_, index) => {
          const x1 = 28 + index * 84;
          const lit = index + 1 < active;
          return (
            <line
              key={`seg-${index}`}
              x1={x1}
              y1="18"
              x2={x1 + 84}
              y2="18"
              stroke={lit ? "url(#constellation-grad)" : "var(--border)"}
              strokeWidth="1.4"
              className={lit ? "path-stroke" : undefined}
              pathLength={1}
            />
          );
        })}
        {NODES.map((label, index) => {
          const x = 28 + index * 84;
          const state = index + 1 < active ? "complete" : index + 1 === active ? "current" : "upcoming";
          return (
            <g key={label}>
              <circle
                cx={x}
                cy="18"
                r={state === "current" ? 6 : 4.5}
                fill={state === "upcoming" ? "var(--surface)" : "url(#constellation-grad)"}
                stroke={state === "upcoming" ? "var(--border-strong)" : "transparent"}
              />
              <text
                x={x}
                y="46"
                textAnchor="middle"
                className="fill-current text-[11px] font-medium"
                fill="currentColor"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="sr-only">
        {NODES.map((label, index) => `${label}: ${index + 1 < active ? "complete" : index + 1 === active ? "current" : "upcoming"}`).join(". ")}
      </p>
      <ol className="flex justify-between gap-1 text-[11px] text-muted-foreground sm:hidden">
        {NODES.map((label, index) => (
          <li
            key={label}
            className={cn(
              "min-w-0 truncate",
              index + 1 === active && "font-semibold text-foreground",
            )}
          >
            {label}
          </li>
        ))}
      </ol>
    </div>
  );
}

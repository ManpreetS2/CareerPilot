import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { Compass } from "lucide-react";
import { Glass } from "./ui/glass";
import { cn } from "../lib/cn";

export const JOB_DISCOVERY_STAGES = [
  "Understanding your target roles",
  "Searching job sources",
  "Reviewing new opportunities",
  "Matching jobs to your profile",
  "Ranking your strongest matches",
  "Almost ready",
] as const;

export const JOB_DISCOVERY_STAGE_THRESHOLDS_MS = [0, 500, 1400, 3200, 5500, 8000] as const;

function visualStageIndex(elapsedMs: number): number {
  let index = 0;
  for (let i = 0; i < JOB_DISCOVERY_STAGE_THRESHOLDS_MS.length; i += 1) {
    const threshold = JOB_DISCOVERY_STAGE_THRESHOLDS_MS[i] ?? 0;
    if (elapsedMs >= threshold) index = i;
  }
  return index;
}

export function JobDiscoveryProgress({
  active,
  reduceMotion,
}: {
  active: boolean;
  reduceMotion?: boolean;
}) {
  const prefersReduced = useReducedMotion();
  const reduce = reduceMotion ?? Boolean(prefersReduced);
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsedMs(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - started);
    }, reduce ? 250 : 120);
    return () => window.clearInterval(id);
  }, [active, reduce]);

  if (!active) return null;

  const current = visualStageIndex(elapsedMs);
  const lastIndex = JOB_DISCOVERY_STAGES.length - 1;

  return (
    <Glass
      variant="working"
      refract={!reduce}
      className="rounded-[var(--radius-lg)] p-5"
      data-testid="job-discovery-progress"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="flex gap-4">
        <div
          className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/10 text-primary sm:flex"
          aria-hidden
        >
          <Compass className={cn("h-5 w-5", !reduce && "job-discovery-spin")} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg font-semibold tracking-tight">Finding opportunities</p>
          <p className="mt-1 text-sm text-muted-foreground">
            CareerPilot is searching live job sources and ranking opportunities against your
            profile.
          </p>
          <ol className="mt-5 space-y-2.5 border-l border-border/80 pl-4">
            {JOB_DISCOVERY_STAGES.map((label, index) => {
              const complete = index < current;
              const isActive = index === current;
              const pending = index > current;
              const state = complete ? "complete" : isActive ? "active" : "pending";
              return (
                <li
                  key={label}
                  className="flex items-center gap-3 text-sm"
                  data-testid={`job-discovery-stage-${index}`}
                  data-state={state}
                >
                  <span
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
                      complete && "bg-primary/15 text-primary",
                      isActive && "border border-primary/50 text-primary",
                      pending && "border border-border text-muted-foreground/50",
                      isActive && !reduce && "job-discovery-pulse",
                    )}
                    aria-hidden
                  >
                    {complete ? "✓" : isActive ? "●" : "○"}
                  </span>
                  <span className={complete || isActive ? "text-foreground" : "text-muted-foreground"}>
                    {label}
                  </span>
                  {isActive && index === lastIndex ? (
                    <span className="sr-only">Still working</span>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </Glass>
  );
}

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { Glass } from "./ui/glass";
import { cn } from "../lib/cn";

export const RESUME_PARSE_STAGES = [
  "Reading your resume",
  "Extracting your experience",
  "Identifying skills & strengths",
  "Building your CareerPilot profile",
  "Almost ready",
] as const;

export const RESUME_PARSE_STAGE_THRESHOLDS_MS = [0, 800, 1800, 3000, 4500] as const;

function visualStageIndex(elapsedMs: number): number {
  let index = 0;
  for (let i = 0; i < RESUME_PARSE_STAGE_THRESHOLDS_MS.length; i += 1) {
    const threshold = RESUME_PARSE_STAGE_THRESHOLDS_MS[i] ?? 0;
    if (elapsedMs >= threshold) index = i;
  }
  return index;
}

export function ResumeParsingProgress({
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
  const lastIndex = RESUME_PARSE_STAGES.length - 1;

  return (
    <Glass
      variant="working"
      refract={!reduce}
      className="rounded-[var(--radius-lg)] p-5"
      data-testid="resume-parsing-progress"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <p className="font-display text-lg font-semibold tracking-tight">Building your profile</p>
      <p className="mt-1 text-sm text-muted-foreground">
        CareerPilot is grounding your profile in the information on your resume.
      </p>
      <ol className="mt-5 space-y-3">
        {RESUME_PARSE_STAGES.map((label, index) => {
          const complete = index < current;
          const isActive = index === current;
          const pending = index > current;
          const state = complete ? "complete" : isActive ? "active" : "pending";
          return (
            <li
              key={label}
              className="flex items-center gap-3 text-sm"
              data-testid={`resume-parse-stage-${index}`}
              data-state={state}
            >
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
                  complete && "bg-primary/15 text-primary",
                  isActive && "border border-primary/50 text-primary",
                  pending && "border border-border text-muted-foreground/50",
                  isActive && !reduce && "resume-parse-pulse",
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
    </Glass>
  );
}

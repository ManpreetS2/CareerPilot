import { useId } from "react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "../../lib/cn";
import { motionDuration, motionEase } from "../../lib/motion";

export type PathNode = {
  id: string;
  label: string;
  state: "complete" | "current" | "upcoming";
};

export function WorkflowPath({
  nodes,
  className,
}: {
  nodes: PathNode[];
  className?: string;
}) {
  const reduce = useReducedMotion();
  const gradId = useId();
  return (
    <ol className={cn("flex flex-wrap items-center gap-2", className)} data-testid="workflow-path">
      {nodes.map((node, index) => (
        <li key={node.id} className="flex items-center gap-2">
          {index > 0 ? (
            <svg width="28" height="8" viewBox="0 0 28 8" aria-hidden className="text-primary">
              <defs>
                <linearGradient id={`${gradId}-${index}`} x1="0" x2="1">
                  <stop offset="0%" stopColor="currentColor" />
                  <stop offset="100%" stopColor="var(--accent)" />
                </linearGradient>
              </defs>
              <line
                x1="0"
                y1="4"
                x2="28"
                y2="4"
                stroke={`url(#${gradId}-${index})`}
                strokeWidth="1.2"
                className={reduce || node.state === "upcoming" ? undefined : "path-stroke"}
                pathLength={1}
                opacity={node.state === "upcoming" ? 0.25 : 0.9}
              />
            </svg>
          ) : null}
          <motion.span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide",
              node.state === "current" && "border-primary/50 bg-primary/10 text-foreground",
              node.state === "complete" && "border-accent/30 bg-accent/10 text-foreground",
              node.state === "upcoming" && "border-border text-muted-foreground",
            )}
            initial={reduce ? false : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionDuration.fast, ease: motionEase.standard, delay: index * 0.04 }}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                node.state === "current" && "bg-accent",
                node.state === "complete" && "bg-primary",
                node.state === "upcoming" && "bg-muted-foreground/40",
              )}
              aria-hidden
            />
            {node.label}
          </motion.span>
        </li>
      ))}
    </ol>
  );
}

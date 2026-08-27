import { motion, useReducedMotion } from "motion/react";
import { motionDuration, motionEase } from "../../lib/motion";

export function LockIn({
  message,
  active,
}: {
  message: string;
  active: boolean;
}) {
  const reduce = useReducedMotion();
  if (!active) return null;

  return (
    <div
      className="flex items-center gap-3 rounded-[var(--radius-md)] border border-primary/25 bg-primary/5 px-3 py-2.5 text-sm"
      role="status"
      data-testid="lock-in"
    >
      <svg width="36" height="20" viewBox="0 0 36 20" aria-hidden className="text-primary">
        <path
          d="M2 10 H22"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className={reduce ? undefined : "path-stroke"}
          pathLength={1}
        />
        <motion.circle
          cx="28"
          cy="10"
          r="5"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.5"
          initial={reduce ? false : { scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: motionDuration.fast, ease: motionEase.expressive, delay: 0.12 }}
        />
        <path
          d="M25.5 10.2 L27.2 12 L30.6 8.2"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
      <span>{message}</span>
    </div>
  );
}

import { cn } from "../../lib/cn";

export function ScoreOrb({
  score,
  className,
}: {
  score?: number | null;
  className?: string;
}) {
  if (score == null) {
    return (
      <div className={cn("score-orb score-orb-empty", className)} aria-label="Not scored">
        <span className="score-orb-inner text-sm">—</span>
      </div>
    );
  }

  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div
      className={cn("score-orb", className)}
      style={{ ["--score-deg" as string]: `${Math.round((clamped / 100) * 360)}deg` }}
      aria-label={`${Math.round(clamped)} percent match`}
    >
      <span className="score-orb-inner tabular">{Math.round(clamped)}</span>
    </div>
  );
}

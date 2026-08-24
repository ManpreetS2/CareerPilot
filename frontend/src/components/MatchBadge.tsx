export function MatchBadge({
  score,
  recommendation,
}: {
  score?: number | null;
  recommendation?: string | null;
}) {
  if (score == null) {
    return (
      <span className="status-pill bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-200">
        Not scored
      </span>
    );
  }

  const tone =
    score >= 80
      ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
      : score >= 65
        ? "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200"
        : "bg-rose-100 text-danger-600 dark:bg-rose-950/40 dark:text-rose-200";

  return (
    <span className={`status-pill ${tone}`}>
      {Math.round(score)}% MATCH
      {recommendation ? ` · ${recommendation}` : ""}
    </span>
  );
}

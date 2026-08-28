const TIER_LABEL: Record<string, string> = {
  strong_match: "Strong Match",
  good_match: "Good Match",
  possible_match: "Possible Match",
  weak_match: "Weak Match",
};

const APPLY_LABEL: Record<string, string> = {
  strong_apply: "Strong Apply",
  apply: "Apply",
  consider: "Consider",
  probably_skip: "Probably Skip",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function MatchBadge({
  score,
  recommendation,
  matchTier,
  applyRecommendation,
  confidenceLevel,
  compact = false,
}: {
  score?: number | null;
  recommendation?: string | null;
  matchTier?: string | null;
  applyRecommendation?: string | null;
  confidenceLevel?: string | null;
  compact?: boolean;
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

  const tier = matchTier ? TIER_LABEL[matchTier] : null;
  const apply = applyRecommendation ? APPLY_LABEL[applyRecommendation] : recommendation;
  const confidence = confidenceLevel ? CONFIDENCE_LABEL[confidenceLevel] : null;

  return (
    <span className={`status-pill ${tone}`}>
      {Math.round(score)}%{tier ? ` ${tier}` : " MATCH"}
      {!compact && apply ? ` · ${apply}` : ""}
      {!compact && confidence ? ` · ${confidence} confidence` : ""}
    </span>
  );
}

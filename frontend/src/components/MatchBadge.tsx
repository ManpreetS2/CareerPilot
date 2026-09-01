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
  scoreKind,
  compact = false,
}: {
  score?: number | null;
  recommendation?: string | null;
  matchTier?: string | null;
  applyRecommendation?: string | null;
  confidenceLevel?: string | null;
  scoreKind?: string | null;
  compact?: boolean;
}) {
  if (score == null) {
    return (
      <span className="status-pill border border-border/70 bg-muted/80 text-muted-foreground">
        Not scored
      </span>
    );
  }

  const apply = applyRecommendation ? APPLY_LABEL[applyRecommendation] : recommendation;
  const verified = scoreKind === "verified";
  if (!verified) {
    return (
      <span className="status-pill border border-border/70 bg-muted/80 text-muted-foreground">
        Potential Match
        {!compact && apply ? ` · ${apply}` : ""}
      </span>
    );
  }

  const tone =
    score >= 80
      ? "border-primary/30 bg-primary/10 text-primary"
      : score >= 65
        ? "border-warning/30 bg-warning/10 text-warning"
        : "border-danger/30 bg-danger/10 text-danger";

  const tier = matchTier ? TIER_LABEL[matchTier] : null;
  const confidence = confidenceLevel ? CONFIDENCE_LABEL[confidenceLevel] : null;

  return (
    <span className={`status-pill ${tone}`}>
      {Math.round(score)}%{tier ? ` ${tier}` : " Verified Fit"}
      {!compact && apply ? ` · ${apply}` : ""}
      {!compact && confidence ? ` · ${confidence} confidence` : ""}
    </span>
  );
}

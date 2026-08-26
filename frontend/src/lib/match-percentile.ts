const MIN_STORED_SCORES = 5;

/**
 * Honest in-user ranking only. Requires enough stored scores for this user.
 * Never invents a global or cross-user percentile.
 */
export function topMatchPercentileLabel(score: number, storedScores: number[]): string | null {
  if (!Number.isFinite(score) || storedScores.length < MIN_STORED_SCORES) return null;
  const betterCount = storedScores.filter((value) => value > score).length;
  const percentileFromTop = ((betterCount + 1) / storedScores.length) * 100;
  if (percentileFromTop <= 10) return "Top 10% of your matches";
  if (percentileFromTop <= 25) return "Top 25% of your matches";
  return null;
}

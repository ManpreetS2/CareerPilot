import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchBadge } from "./MatchBadge";

describe("MatchBadge", () => {
  it("shows compact overall match and tier without apply copy", () => {
    render(
      <MatchBadge
        score={88}
        recommendation="apply"
        matchTier="strong_match"
        applyRecommendation="strong_apply"
        confidenceLevel="high"
        compact
      />,
    );
    expect(screen.getByText(/88% Strong Match/)).toBeInTheDocument();
    expect(screen.queryByText(/Strong Apply/)).not.toBeInTheDocument();
    expect(screen.queryByText(/High confidence/)).not.toBeInTheDocument();
  });

  it("shows apply recommendation and confidence in the detailed badge", () => {
    render(
      <MatchBadge
        score={88}
        recommendation="apply"
        matchTier="strong_match"
        applyRecommendation="strong_apply"
        confidenceLevel="high"
      />,
    );
    expect(screen.getByText(/88% Strong Match · Strong Apply · High confidence/)).toBeInTheDocument();
  });
});

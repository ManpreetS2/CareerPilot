import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MatchBadge } from "./MatchBadge";

describe("MatchBadge", () => {
  it("hides preliminary percentages behind Potential Match", () => {
    render(
      <MatchBadge
        score={88}
        recommendation="apply"
        matchTier="strong_match"
        applyRecommendation="strong_apply"
        confidenceLevel="high"
        scoreKind="preliminary"
        compact
      />,
    );
    expect(screen.getByText("Potential Match")).toBeInTheDocument();
    expect(screen.queryByText(/88%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Strong Match/)).not.toBeInTheDocument();
  });

  it("shows compact verified overall match and tier without apply copy", () => {
    render(
      <MatchBadge
        score={88}
        recommendation="apply"
        matchTier="strong_match"
        applyRecommendation="strong_apply"
        confidenceLevel="high"
        scoreKind="verified"
        compact
      />,
    );
    expect(screen.getByText(/88% Strong Match/)).toBeInTheDocument();
    expect(screen.queryByText(/Strong Apply/)).not.toBeInTheDocument();
    expect(screen.queryByText(/High confidence/)).not.toBeInTheDocument();
  });

  it("shows apply recommendation and confidence in the detailed verified badge", () => {
    render(
      <MatchBadge
        score={88}
        recommendation="apply"
        matchTier="strong_match"
        applyRecommendation="strong_apply"
        confidenceLevel="high"
        scoreKind="verified"
      />,
    );
    expect(screen.getByText(/88% Strong Match · Strong Apply · High confidence/)).toBeInTheDocument();
  });
});

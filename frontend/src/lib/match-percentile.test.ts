import { describe, expect, it } from "vitest";
import { topMatchPercentileLabel } from "./match-percentile";

describe("topMatchPercentileLabel", () => {
  it("stays silent until this user has enough stored scores", () => {
    expect(topMatchPercentileLabel(99, [99, 80, 70, 60])).toBeNull();
  });

  it("labels only the top slice of this user's stored scores", () => {
    const scores = [92, 88, 80, 70, 60, 55, 40, 30, 20, 10];
    expect(topMatchPercentileLabel(92, scores)).toBe("Top 10% of your matches");
    expect(topMatchPercentileLabel(88, scores)).toBe("Top 25% of your matches");
    expect(topMatchPercentileLabel(40, scores)).toBeNull();
  });
});

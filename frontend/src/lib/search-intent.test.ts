import { describe, expect, it } from "vitest";
import { parseSearchIntent } from "./search-intent";

describe("search intent skeleton", () => {
  it("does not invent filters from natural language", () => {
    const intent = parseSearchIntent(
      "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite",
    );
    expect(intent.parserReady).toBe(false);
    expect(intent.roles).toEqual([]);
    expect(intent.rawQuery).toContain("Software engineering internships");
  });
});

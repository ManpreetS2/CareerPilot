import { describe, expect, it } from "vitest";
import { parseSearchIntent } from "./search-intent";

describe("search intent parser", () => {
  it("parses the Bay Area internship example into allowlisted filters", () => {
    const intent = parseSearchIntent(
      "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite",
    );
    expect(intent.parser_ready).toBe(true);
    expect(intent.roles).toEqual(["Software Engineering"]);
    expect(intent.opportunity_types).toEqual(["internship"]);
    expect(intent.locations).toEqual(["San Francisco Bay Area"]);
    expect(intent.work_modes).toEqual(["hybrid", "onsite"]);
    expect(intent.industries).toEqual(["fintech"]);
    expect(intent.raw_query).not.toMatch(/SELECT|DROP TABLE/i);
  });

  it("falls back to an empty ready intent when the query is blank", () => {
    const intent = parseSearchIntent("   ");
    expect(intent.parser_source).toBe("empty");
    expect(intent.roles).toEqual([]);
    expect(intent.parser_ready).toBe(true);
  });
});

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { formatApiDate, formatApiTimestamp, parseApiTimestamp } from "./datetime";

// CI runs in UTC, where both bugs below are invisible. Pin a zone west of UTC.
const originalTz = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "America/Chicago";
});
afterAll(() => {
  process.env.TZ = originalTz;
});

describe("parseApiTimestamp", () => {
  it("reads a naive API date-time as UTC, not local time", () => {
    expect(parseApiTimestamp("2026-09-23T22:51:44.481746").getTime()).toBe(
      Date.UTC(2026, 8, 23, 22, 51, 44, 481),
    );
  });

  it("keeps an explicit offset as given", () => {
    expect(parseApiTimestamp("2026-09-23T22:51:44Z").getTime()).toBe(Date.UTC(2026, 8, 23, 22, 51, 44));
    expect(parseApiTimestamp("2026-09-23T17:51:44-05:00").getTime()).toBe(Date.UTC(2026, 8, 23, 22, 51, 44));
  });

  it("reads a calendar date as that local day, not the previous one", () => {
    const parsed = parseApiTimestamp("2026-08-21");
    expect([parsed.getFullYear(), parsed.getMonth(), parsed.getDate()]).toEqual([2026, 7, 21]);
  });

  it("parses non-ISO strings exactly as before", () => {
    expect(parseApiTimestamp("Aug 21, 2026").getTime()).toBe(new Date("Aug 21, 2026").getTime());
  });
});

describe("formatApiTimestamp / formatApiDate", () => {
  it("formats the true UTC instant in the viewer's zone", () => {
    expect(formatApiTimestamp("2026-09-23T22:51:44")).toBe(
      new Date(Date.UTC(2026, 8, 23, 22, 51, 44)).toLocaleString(),
    );
  });

  it("does not move an evening UTC signup to the next local day", () => {
    // 01:30 UTC on Sep 24 is still Sep 23 in Chicago.
    expect(formatApiDate("2026-09-24T01:30:00")).toBe(new Date(2026, 8, 23).toLocaleDateString());
  });

  it("falls back for missing or unreadable values", () => {
    expect(formatApiTimestamp(null)).toBe("—");
    expect(formatApiTimestamp("", "Not yet")).toBe("Not yet");
    expect(formatApiDate("not a date", "n/a")).toBe("n/a");
  });
});

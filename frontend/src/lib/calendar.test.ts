import { describe, expect, it } from "vitest";
import { googleCalendarUrl } from "./calendar";

describe("googleCalendarUrl", () => {
  it("builds a well-formed create-event template URL", () => {
    const url = googleCalendarUrl("Backend Intern", "Acme", "2026-09-20");
    const parsed = new URL(url);
    expect(parsed.origin + parsed.pathname).toBe("https://calendar.google.com/calendar/render");
    expect(parsed.searchParams.get("action")).toBe("TEMPLATE");
    expect(parsed.searchParams.get("text")).toBe("Follow up: Backend Intern @ Acme");
  });

  it("uses an exclusive end date one day after the reminder, matching the .ics convention", () => {
    const url = googleCalendarUrl("Backend Intern", "Acme", "2026-09-20");
    const parsed = new URL(url);
    expect(parsed.searchParams.get("dates")).toBe("20260920/20260921");
  });

  it("rolls over month and year boundaries correctly", () => {
    const monthEnd = new URL(googleCalendarUrl("A", "B", "2026-09-30"));
    expect(monthEnd.searchParams.get("dates")).toBe("20260930/20261001");
    const yearEnd = new URL(googleCalendarUrl("A", "B", "2026-12-31"));
    expect(yearEnd.searchParams.get("dates")).toBe("20261231/20270101");
  });

  it("relies on URLSearchParams to encode special characters safely", () => {
    const url = googleCalendarUrl("Engineer, Backend & Infra", "A/B Corp", "2026-01-01");
    const parsed = new URL(url);
    expect(parsed.searchParams.get("text")).toBe("Follow up: Engineer, Backend & Infra @ A/B Corp");
    expect(url).not.toContain("&Infra"); // raw ampersand must be percent-encoded, not a literal query separator
  });
});

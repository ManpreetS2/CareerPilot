import { describe, expect, it } from "vitest";

import { isJobPageUrl, originPattern } from "../src/api";
import {
  escapeHtml,
  materialsBadge,
  matchBadge,
  parseUtcTimestamp,
  scoutedTimeAgo,
  sourceBadge,
  statusBadge,
} from "../src/render";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

describe("parseUtcTimestamp", () => {
  it("reads a naive backend timestamp as UTC, not as local time", () => {
    // The regression this exists for: SQLite strips tzinfo, so date_scraped
    // arrives with no offset, and bare Date parsing would treat it as local.
    expect(parseUtcTimestamp("2026-08-26T06:34:33.735519")).toBe(Date.parse("2026-08-26T06:34:33.735Z"));
  });

  it("leaves an explicit offset alone rather than double-applying one", () => {
    expect(parseUtcTimestamp("2026-08-26T06:34:33Z")).toBe(Date.parse("2026-08-26T06:34:33Z"));
    expect(parseUtcTimestamp("2026-08-26T12:04:33+05:30")).toBe(Date.parse("2026-08-26T06:34:33Z"));
    expect(parseUtcTimestamp("2026-08-26T12:04:33+0530")).toBe(Date.parse("2026-08-26T06:34:33Z"));
  });

  it("returns NaN for unparseable input instead of throwing", () => {
    expect(Number.isNaN(parseUtcTimestamp("not a date"))).toBe(true);
  });
});

describe("scoutedTimeAgo", () => {
  const scraped = "2026-08-26T06:00:00";
  const scrapedUtc = Date.parse("2026-08-26T06:00:00Z");

  it("counts whole days from the true UTC instant", () => {
    expect(scoutedTimeAgo(scraped, scrapedUtc + 2 * HOUR)).toBe("Seen today");
    expect(scoutedTimeAgo(scraped, scrapedUtc + 25 * HOUR)).toBe("Seen 1 day ago");
    expect(scoutedTimeAgo(scraped, scrapedUtc + 3 * DAY)).toBe("Seen 3 days ago");
  });

  it("does not roll over a day early for a viewer ahead of UTC", () => {
    // 20 hours after scraping is still "today". Parsing the naive string as
    // IST local time would have added 5h30m of phantom age and reported
    // "Seen 1 day ago" — the exact off-by-one this guards.
    expect(scoutedTimeAgo(scraped, scrapedUtc + 20 * HOUR)).toBe("Seen today");
  });

  it("clamps a future timestamp to today rather than reporting negative days", () => {
    expect(scoutedTimeAgo(scraped, scrapedUtc - 3 * HOUR)).toBe("Seen today");
  });

  it("returns null when there is nothing to show", () => {
    expect(scoutedTimeAgo(null)).toBeNull();
    expect(scoutedTimeAgo(undefined)).toBeNull();
    expect(scoutedTimeAgo("")).toBeNull();
    expect(scoutedTimeAgo("garbage")).toBeNull();
  });
});

describe("escapeHtml", () => {
  it("neutralizes markup coming from page or job content", () => {
    expect(escapeHtml("<img src=x onerror=alert(1)>")).not.toContain("<img");
    expect(escapeHtml("Tom & Jerry")).toBe("Tom &amp; Jerry");
  });
});

describe("badges", () => {
  it("labels every job status and never emits raw input", () => {
    for (const status of ["discovered", "verified", "flagged", "stale"]) {
      expect(statusBadge(status)).toContain(status);
    }
    expect(statusBadge("<b>x</b>")).not.toContain("<b>");
  });

  it("renders underscored statuses as words", () => {
    expect(statusBadge("needs_review")).toContain("needs review");
  });

  it("maps known sources to display names and passes unknown ones through safely", () => {
    expect(sourceBadge("greenhouse")).toContain("Greenhouse");
    expect(sourceBadge("remoteok")).toContain("RemoteOK");
    expect(sourceBadge("REMOTIVE")).toContain("Remotive");
    expect(sourceBadge("<script>")).not.toContain("<script>");
  });

  it("shows an unscored pill only when there is genuinely no score", () => {
    expect(matchBadge(null)).toContain("Not scored");
    expect(matchBadge(undefined)).toContain("Not scored");
    expect(matchBadge(0)).toContain("Potential Match");
  });

  it("hides preliminary percentages and shows verified scores", () => {
    expect(matchBadge(87.4, "apply")).toContain("Potential Match");
    expect(matchBadge(87.4, "apply", "verified")).toContain("Verified Match 87%");
    expect(matchBadge(87.4, "apply", "verified")).toContain("apply");
    expect(matchBadge(87.4, undefined, "verified")).not.toContain("·");
  });

  it("gives every materials state a distinct label", () => {
    const labels = (["missing", "current", "stale_pending", "stale_reviewed"] as const).map((s) => materialsBadge(s));
    expect(new Set(labels).size).toBe(4);
    expect(materialsBadge(null)).toContain("No materials yet");
  });
});

describe("isJobPageUrl", () => {
  it("accepts http and https pages", () => {
    expect(isJobPageUrl("https://boards.greenhouse.io/acme/jobs/1")).toBe(true);
    expect(isJobPageUrl("http://localhost:5173/jobs")).toBe(true);
  });

  it("rejects everything a job posting can never live at", () => {
    // These must never be sent to the backend — the panel would be
    // reporting the user's browsing of internal pages to the server.
    for (const url of [
      "chrome://extensions/",
      "chrome-extension://abcdef/sidepanel.html",
      "about:blank",
      "file:///Users/someone/private.pdf",
      "data:text/html,hi",
      "",
      null,
      undefined,
      "not a url",
    ]) {
      expect(isJobPageUrl(url)).toBe(false);
    }
  });
});

describe("originPattern", () => {
  it("scopes a request to the posting's own origin and nothing wider", () => {
    expect(originPattern("https://boards.greenhouse.io/acme/jobs/1?x=2")).toBe("https://boards.greenhouse.io/*");
    expect(originPattern("https://jobs.lever.co/acme/uuid/apply")).toBe("https://jobs.lever.co/*");
  });

  it("returns null rather than a broken pattern for unparseable input", () => {
    expect(originPattern("not a url")).toBeNull();
  });
});

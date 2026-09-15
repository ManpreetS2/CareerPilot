import { describe, expect, it } from "vitest";
import { formatJobCardMeta } from "./job-meta";

describe("formatJobCardMeta", () => {
  it("deduplicates adjacent equivalent values such as Remote + Remote", () => {
    expect(formatJobCardMeta(["Remote", "Remote", "Internship"])).toBe("Remote · Internship");
    expect(formatJobCardMeta([" remote ", "Remote", "Internship"])).toBe("remote · Internship");
  });

  it("keeps location and a different work mode", () => {
    expect(formatJobCardMeta(["San Francisco, CA", "Hybrid"])).toBe("San Francisco, CA · Hybrid");
    expect(formatJobCardMeta(["New York, NY", "On-site"])).toBe("New York, NY · On-site");
  });

  it("skips unknown and missing values without inventing labels", () => {
    expect(formatJobCardMeta([null, undefined, "", "Internship"])).toBe("Internship");
  });

  it("keeps a repeated value when a distinct salary sits between the duplicates", () => {
    expect(formatJobCardMeta(["Remote", "$120k–$150k", "Remote", "Internship"])).toBe(
      "Remote · $120k–$150k · Remote · Internship",
    );
  });

  it("keeps salary at the end of location, work mode, and employment type", () => {
    expect(formatJobCardMeta(["Remote", "Remote", "Internship", "$120k–$150k"])).toBe(
      "Remote · Internship · $120k–$150k",
    );
  });
});

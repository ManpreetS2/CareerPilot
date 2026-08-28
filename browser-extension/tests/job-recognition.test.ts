import { describe, expect, it } from "vitest";
import { detectAtsPlatform, recognizeJobPage } from "../src/job-recognition";

describe("job recognition", () => {
  it("recognizes Greenhouse posting URLs and extracts the source job id", () => {
    const canonical = recognizeJobPage("https://boards.greenhouse.io/acme/jobs/12345");
    expect(canonical.platform).toBe("greenhouse");
    expect(canonical.supported).toBe(true);
    expect(canonical.sourceJobId).toBe("12345");
    expect(canonical.companyHint).toBe("acme");

    const embed = recognizeJobPage(
      "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=7761472003&utm_source=jobright",
    );
    expect(embed.platform).toBe("greenhouse");
    expect(embed.sourceJobId).toBe("7761472003");
    expect(embed.companyHint).toBe("acme");
  });

  it("recognizes Lever posting URLs including /apply", () => {
    const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const posting = recognizeJobPage(`https://jobs.lever.co/acme/${id}`);
    expect(posting.platform).toBe("lever");
    expect(posting.supported).toBe(true);
    expect(posting.sourceJobId).toBe(id);
    expect(recognizeJobPage(`https://jobs.lever.co/acme/${id}/apply`).sourceJobId).toBe(id);
  });

  it("marks other hosts as unsupported without scraping page text", () => {
    expect(detectAtsPlatform("https://remotive.com/remote-jobs/software-dev/x")).toBe("unsupported");
    expect(recognizeJobPage("https://example.com/jobs/1").supported).toBe(false);
    expect(recognizeJobPage("https://example.com/jobs/1").sourceJobId).toBeNull();
  });
});

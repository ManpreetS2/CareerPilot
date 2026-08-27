import { describe, expect, it } from "vitest";
import { ApiClientError } from "./api";
import { jobDiscoveryErrorHeading } from "./job-discovery-error";

describe("jobDiscoveryErrorHeading", () => {
  it("maps timeouts without exposing internals", () => {
    expect(jobDiscoveryErrorHeading(new ApiClientError(504, "timed out"))).toBe(
      "Job discovery timed out",
    );
  });

  it("maps source outages without exposing URLs", () => {
    expect(jobDiscoveryErrorHeading(new ApiClientError(502, "bad gateway"))).toBe(
      "We couldn't reach enough job sources",
    );
    expect(jobDiscoveryErrorHeading(new ApiClientError(0, "network"))).toBe(
      "Job search temporarily unavailable",
    );
  });
});

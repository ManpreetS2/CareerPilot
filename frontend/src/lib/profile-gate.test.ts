import { describe, expect, it } from "vitest";
import { canScoutJobs, isGroundedCandidate, resolveProfileGate } from "./profile-gate";
import type { CandidateProfile } from "./types";

const grounded: CandidateProfile = {
  name: "Ada Lovelace",
  skills: ["Python"],
  projects: [],
  experience: [],
  education: [],
  certifications: [],
  strengths: [],
  evidence_links: [],
};

const empty: CandidateProfile = {
  name: "",
  skills: [],
  projects: [],
  experience: [],
  education: [],
  certifications: [],
  strengths: [],
  evidence_links: [],
};

describe("profile gate", () => {
  it("treats a named or skilled candidate as grounded", () => {
    expect(isGroundedCandidate(grounded)).toBe(true);
    expect(isGroundedCandidate({ ...empty, skills: ["Go"] })).toBe(true);
    expect(isGroundedCandidate(empty)).toBe(false);
    expect(isGroundedCandidate(null)).toBe(false);
  });

  it("blocks scouting while profile status is unknown and nothing is cached", () => {
    const gate = resolveProfileGate({ cached: null, status: "pending", remote: undefined });
    expect(gate.kind).toBe("pending");
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("blocks scouting when profile loading failed and nothing is cached", () => {
    const gate = resolveProfileGate({ cached: null, status: "error", remote: undefined });
    expect(gate.kind).toBe("error");
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("blocks scouting for a successful empty profile", () => {
    const gate = resolveProfileGate({ cached: null, status: "success", remote: null });
    expect(gate.kind).toBe("incomplete");
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("allows scouting from a cached complete profile while the query is pending", () => {
    const gate = resolveProfileGate({ cached: grounded, status: "pending", remote: undefined });
    expect(gate.kind).toBe("ready");
    expect(canScoutJobs(gate)).toBe(true);
  });

  it("allows scouting from a cached complete profile if the live query failed", () => {
    const gate = resolveProfileGate({ cached: grounded, status: "error", remote: undefined });
    expect(gate.kind).toBe("ready");
    expect(canScoutJobs(gate)).toBe(true);
  });
});

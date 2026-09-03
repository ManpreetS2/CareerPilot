import { describe, expect, it } from "vitest";
import {
  INCOMPLETE_READINESS,
  canScoutJobs,
  evidenceSourcesFromCandidate,
  requiredReadinessFromServer,
  resolveProfileGate,
} from "./profile-gate";
import type { CandidateProfile } from "./types";

const ready = {
  ready: true,
  missing: [] as string[],
  code: null,
  next_route: null,
};

describe("resolveProfileGate", () => {
  it("blocks scout while the profile query is pending", () => {
    const gate = resolveProfileGate({ status: "pending", readiness: ready });
    expect(gate.kind).toBe("pending");
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("treats a profile GET failure as an error, not ready or missing", () => {
    const gate = resolveProfileGate({ status: "error", readiness: ready });
    expect(gate.kind).toBe("error");
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("unlocks scout only from server readiness", () => {
    const gate = resolveProfileGate({ status: "success", readiness: ready });
    expect(gate.kind).toBe("ready");
    expect(canScoutJobs(gate)).toBe(true);
  });

  it("shows the incomplete gate from server missing requirements", () => {
    const gate = resolveProfileGate({
      status: "success",
      readiness: {
        ready: false,
        code: "profile_required",
        missing: ["target_roles"],
        next_route: "/profile",
      },
    });
    expect(gate).toEqual({
      kind: "incomplete",
      readiness: {
        ready: false,
        code: "profile_required",
        missing: ["target_roles"],
        next_route: "/profile",
      },
    });
    expect(canScoutJobs(gate)).toBe(false);
  });

  it("does not invent ready=true when the server omitted readiness", () => {
    const gate = resolveProfileGate({ status: "success", readiness: undefined });
    expect(gate.kind).toBe("incomplete");
    if (gate.kind === "incomplete") {
      expect(gate.readiness).toEqual(INCOMPLETE_READINESS);
    }
  });
});

describe("requiredReadinessFromServer", () => {
  it("marks all three required gates Open when the profile is empty", () => {
    const items = requiredReadinessFromServer(INCOMPLETE_READINESS);
    expect(items.map((item) => [item.label, item.ready])).toEqual([
      ["Identity", false],
      ["Grounded evidence", false],
      ["Target role", false],
    ]);
  });

  it("marks all three Ready for name + one skill + target role", () => {
    const items = requiredReadinessFromServer(ready);
    expect(items.every((item) => item.ready)).toBe(true);
  });

  it("marks only Target role Ready when the server is still missing candidate evidence", () => {
    const items = requiredReadinessFromServer({
      ready: false,
      code: "profile_required",
      missing: ["candidate_profile", "candidate_evidence"],
      next_route: "/profile",
    });
    expect(items.find((item) => item.id === "identity")?.ready).toBe(false);
    expect(items.find((item) => item.id === "grounded_evidence")?.ready).toBe(false);
    expect(items.find((item) => item.id === "target_role")?.ready).toBe(true);
  });
});

describe("evidenceSourcesFromCandidate", () => {
  it("does not treat empty experience or projects as required gates", () => {
    const candidate: CandidateProfile = {
      name: "QA Test User",
      skills: ["Python"],
      education: [],
      experience: [],
      projects: [],
      certifications: [],
      strengths: [],
      evidence_links: [],
    };
    expect(evidenceSourcesFromCandidate(candidate)).toEqual([
      { id: "skills", label: "Skills", present: true },
      { id: "education", label: "Education", present: false },
      { id: "experience", label: "Experience", present: false },
      { id: "projects", label: "Projects", present: false },
    ]);
  });
});

import { describe, expect, it } from "vitest";
import {
  INCOMPLETE_READINESS,
  canScoutJobs,
  resolveProfileGate,
} from "./profile-gate";

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

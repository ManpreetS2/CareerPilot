import type { CandidateProfile } from "./types";

export type ProfileQueryStatus = "pending" | "success" | "error";

export type ProfileReadiness = {
  ready: boolean;
  code?: string | null;
  missing: string[];
  next_route?: string | null;
};

export type ProfileGate =
  | { kind: "ready"; readiness: ProfileReadiness }
  | { kind: "incomplete"; readiness: ProfileReadiness }
  | { kind: "pending" }
  | { kind: "error" };

export const PROFILE_REQUIREMENT_LABELS: Record<string, string> = {
  candidate_profile: "A name on your profile",
  candidate_evidence: "Education, experience, projects, or skills",
  target_roles: "At least one target role",
};

export function missingRequirementLabel(code: string): string {
  return PROFILE_REQUIREMENT_LABELS[code] ?? code.replaceAll("_", " ");
}

/** Fallback only when the server omitted readiness. Never treat failure as ready. */
export const INCOMPLETE_READINESS: ProfileReadiness = {
  ready: false,
  code: "profile_required",
  missing: ["candidate_profile", "candidate_evidence", "target_roles"],
  next_route: "/profile",
};

export function resolveProfileGate({
  status,
  readiness,
}: {
  cached?: CandidateProfile | null;
  status: ProfileQueryStatus;
  remote?: CandidateProfile | null | undefined;
  readiness: ProfileReadiness | null | undefined;
}): ProfileGate {
  if (status === "pending") return { kind: "pending" };
  if (status === "error") return { kind: "error" };
  if (readiness?.ready) return { kind: "ready", readiness };
  return {
    kind: "incomplete",
    readiness: readiness ?? INCOMPLETE_READINESS,
  };
}

export function canScoutJobs(gate: ProfileGate): boolean {
  return gate.kind === "ready";
}

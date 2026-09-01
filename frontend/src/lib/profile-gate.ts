import type { CandidateProfile } from "./types";

export type ProfileQueryStatus = "pending" | "success" | "error";

export type ProfileGate =
  | { kind: "ready"; candidate: CandidateProfile }
  | { kind: "pending" }
  | { kind: "error" }
  | { kind: "incomplete" };

export function isGroundedCandidate(candidate: CandidateProfile | null | undefined): boolean {
  if (!candidate) return false;
  return Boolean(candidate.name?.trim()) || Boolean(candidate.skills?.length);
}

export function resolveProfileGate({
  cached,
  status,
  remote,
}: {
  cached: CandidateProfile | null | undefined;
  status: ProfileQueryStatus;
  remote: CandidateProfile | null | undefined;
}): ProfileGate {
  if (status === "success") {
    const known = remote ?? cached ?? null;
    return isGroundedCandidate(known) && known
      ? { kind: "ready", candidate: known }
      : { kind: "incomplete" };
  }
  if (isGroundedCandidate(cached) && cached) {
    return { kind: "ready", candidate: cached };
  }
  if (status === "pending") return { kind: "pending" };
  return { kind: "error" };
}

export function canScoutJobs(gate: ProfileGate): boolean {
  return gate.kind === "ready";
}

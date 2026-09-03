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

export const REQUIRED_READINESS_ITEMS = [
  { missingCode: "candidate_profile", id: "identity", label: "Identity" },
  {
    missingCode: "candidate_evidence",
    id: "grounded_evidence",
    label: "Grounded evidence",
    helper: "Add at least one skill, education item, experience item, or project.",
  },
  { missingCode: "target_roles", id: "target_role", label: "Target role" },
] as const;

export type RequiredReadinessItem = {
  id: (typeof REQUIRED_READINESS_ITEMS)[number]["id"];
  label: string;
  helper?: string;
  ready: boolean;
};

export type EvidenceSourceDetail = {
  id: "skills" | "education" | "experience" | "projects";
  label: string;
  present: boolean;
};

/** Required Discover gates from the server `missing` list. Never invent extra gates. */
export function requiredReadinessFromServer(
  readiness: ProfileReadiness | null | undefined,
): RequiredReadinessItem[] {
  const missing = new Set(
    readiness?.missing ?? (readiness?.ready ? [] : INCOMPLETE_READINESS.missing),
  );
  return REQUIRED_READINESS_ITEMS.map((item) => ({
    id: item.id,
    label: item.label,
    helper: "helper" in item ? item.helper : undefined,
    ready: readiness != null && !missing.has(item.missingCode),
  }));
}

export function evidenceSourcesFromCandidate(candidate: CandidateProfile | null | undefined): EvidenceSourceDetail[] {
  return [
    { id: "skills", label: "Skills", present: Boolean(candidate?.skills.length) },
    { id: "education", label: "Education", present: Boolean(candidate?.education.length) },
    { id: "experience", label: "Experience", present: Boolean(candidate?.experience.length) },
    { id: "projects", label: "Projects", present: Boolean(candidate?.projects.length) },
  ];
}

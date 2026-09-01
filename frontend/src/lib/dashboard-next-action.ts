import type { Job, MatchScore, ProfileReadiness, ResumeVersionSummary } from "./types";

export type NextAction = {
  id: "profile" | "jobs" | "matches" | "resume";
  title: string;
  description: string;
  to: string;
  cta: string;
};

export function resolveNextAction(input: {
  readiness?: ProfileReadiness | null;
  jobs: Job[];
  scores: MatchScore[];
  resumeVersions: ResumeVersionSummary[];
}): NextAction {
  if (!input.readiness?.ready) {
    return {
      id: "profile",
      title: "Complete your profile",
      description:
        "CareerPilot needs a grounded profile and at least one target role before it can search for matches.",
      to: input.readiness?.next_route || "/profile",
      cta: "Complete your profile",
    };
  }
  if (input.jobs.length === 0) {
    return {
      id: "jobs",
      title: "Find jobs",
      description: "Scout Greenhouse, Lever, Remotive, Adzuna, RemoteOK, Jobicy, and Himalayas roles — or paste a posting URL.",
      to: "/jobs",
      cta: "Open jobs",
    };
  }
  const verified = input.scores.filter((score) => score.score_kind === "verified");
  if (verified.length > 0 || input.scores.length > 0) {
    return {
      id: "matches",
      title: verified.length > 0 ? "Review verified matches" : "Review your matches",
      description:
        verified.length > 0
          ? "Open Matches to see Verified Fit first. Potential Matches stay clearly labeled until requirements are verified."
          : "CareerPilot has preliminary rankings. Open Matches — percentages become authoritative only after verification.",
      to: "/jobs?tab=matches",
      cta: "Open Matches",
    };
  }
  if (input.resumeVersions.length > 0) {
    const latest = input.resumeVersions[0];
    return {
      id: "resume",
      title: "Review latest resume",
      description: "An approved resume version is ready. Historical snapshots stay frozen even if your profile changes.",
      to: latest ? `/resume/${latest.id}` : "/resume",
      cta: "Open resume library",
    };
  }
  return {
    id: "jobs",
    title: "Find jobs",
    description: "Scout roles and calculate fit on the ones that look promising.",
    to: "/jobs",
    cta: "Open jobs",
  };
}

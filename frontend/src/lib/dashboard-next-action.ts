import type { CandidateProfile, Job, MatchScore, ResumeVersionSummary, TargetPreferences } from "./types";

export type NextAction = {
  id: "profile" | "preferences" | "jobs" | "matches" | "resume";
  title: string;
  description: string;
  to: string;
  cta: string;
};

export function resolveNextAction(input: {
  candidate: CandidateProfile | null;
  preferences: TargetPreferences | null;
  jobs: Job[];
  scores: MatchScore[];
  resumeVersions: ResumeVersionSummary[];
}): NextAction {
  if (!input.candidate) {
    return {
      id: "profile",
      title: "Build your profile",
      description: "Upload a resume so CareerPilot can ground every later recommendation in your real experience.",
      to: "/profile",
      cta: "Open profile",
    };
  }
  if (!input.preferences?.target_roles?.length) {
    return {
      id: "preferences",
      title: "Finish setup",
      description: "Add target roles and locations so job search and fit scoring know what you want.",
      to: "/onboarding",
      cta: "Continue setup",
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

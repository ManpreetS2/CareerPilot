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
      description: "Scout Greenhouse, Lever, Remotive, Adzuna, and RemoteOK roles — or paste a posting URL.",
      to: "/jobs",
      cta: "Open jobs",
    };
  }
  const strong = input.scores.filter((score) => score.overall_score >= 70 || score.recommendation === "apply");
  if (strong.length > 0) {
    const first = strong[0];
    return {
      id: "matches",
      title: "Review strongest matches",
      description: "You have roles with a strong stored fit. Prepare materials only when you choose to.",
      to: first?.job_id ? `/jobs/${first.job_id}` : "/jobs",
      cta: "Review matches",
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

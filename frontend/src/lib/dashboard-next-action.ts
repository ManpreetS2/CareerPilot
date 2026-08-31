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
      title: "Finish your profile",
      description: "Upload a resume so CareerPilot can ground every later recommendation in your real experience.",
      to: "/profile",
      cta: "Finish your profile",
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
      cta: "Find jobs",
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
    cta: "Find jobs",
  };
}

export function pickTopMatches(
  jobs: Job[],
  scores: MatchScore[],
  limit = 3,
): Array<{ job: Job; score: MatchScore }> {
  const byId = new Map(scores.map((score) => [score.job_id, score]));
  return jobs
    .filter((job): job is Job & { id: string } => Boolean(job.id) && byId.has(job.id as string))
    .map((job) => ({ job, score: byId.get(job.id as string)! }))
    .sort((a, b) => {
      const verifiedA = a.score.score_kind === "verified" ? 1 : 0;
      const verifiedB = b.score.score_kind === "verified" ? 1 : 0;
      if (verifiedB !== verifiedA) return verifiedB - verifiedA;
      const rankA = a.score.ranking_score ?? a.score.overall_score ?? 0;
      const rankB = b.score.ranking_score ?? b.score.overall_score ?? 0;
      return rankB - rankA;
    })
    .slice(0, limit);
}

export function profileReadinessItems(input: {
  candidate: CandidateProfile | null;
  preferences: TargetPreferences | null;
  resumeVersions: ResumeVersionSummary[];
}): Array<{ label: string; done: boolean }> {
  const candidate = input.candidate;
  return [
    { label: "Add your name", done: Boolean(candidate?.name) },
    { label: "Add skills", done: Boolean(candidate?.skills.length) },
    { label: "Set target roles", done: Boolean(input.preferences?.target_roles?.length) },
    {
      label: "Upload a resume",
      done: Boolean(candidate?.experience.length || input.resumeVersions.length),
    },
  ];
}

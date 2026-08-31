import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ErrorBanner } from "../components/ErrorBanner";
import { MatchBadge } from "../components/MatchBadge";
import { Glass } from "../components/ui/glass";
import { Progress } from "../components/ui/progress";
import { Skeleton } from "../components/ui/skeleton";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  pickTopMatches,
  profileReadinessItems,
  resolveNextAction,
} from "../lib/dashboard-next-action";
import { queryKeys } from "../lib/query-keys";
import { useCandidateSession } from "../lib/session";

function greetingForHour(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function workModeLabel(mode: string | null | undefined): string | null {
  if (mode === "remote") return "Remote";
  if (mode === "hybrid") return "Hybrid";
  if (mode === "onsite") return "On-site";
  return null;
}

export function DashboardPage() {
  const { user } = useAuth();
  const { candidate, preferences } = useCandidateSession();

  const jobsQuery = useQuery({
    queryKey: queryKeys.jobs,
    queryFn: ({ signal }) => api.getJobs({ signal }),
  });
  const scoresQuery = useQuery({
    queryKey: queryKeys.scores,
    queryFn: async ({ signal }) => {
      try {
        return await api.getStoredScores({ signal });
      } catch {
        return [];
      }
    },
  });
  const versionsQuery = useQuery({
    queryKey: queryKeys.resumeVersions,
    queryFn: async ({ signal }) => {
      try {
        return await api.listAllResumeVersions({ signal });
      } catch {
        return [];
      }
    },
  });
  const profileQuery = useQuery({
    queryKey: queryKeys.profile,
    queryFn: ({ signal }) => api.getProfile({ signal }),
  });

  const loading =
    jobsQuery.isPending || scoresQuery.isPending || versionsQuery.isPending || profileQuery.isPending;
  const error = jobsQuery.error ?? profileQuery.error;
  const jobs = jobsQuery.data ?? [];
  const scores = scoresQuery.data ?? [];
  const versions = versionsQuery.data ?? [];
  const liveCandidate = profileQuery.data?.candidate ?? candidate;
  const livePreferences = profileQuery.data?.preferences ?? preferences;
  const next = resolveNextAction({
    candidate: liveCandidate,
    preferences: livePreferences,
    jobs,
    scores,
    resumeVersions: versions,
  });
  const matches = pickTopMatches(jobs, scores, 3);
  const readiness = profileReadinessItems({
    candidate: liveCandidate,
    preferences: livePreferences,
    resumeVersions: versions,
  });
  const readinessDone = readiness.filter((item) => item.done).length;
  const greetingName =
    liveCandidate?.name?.split(" ")[0] || user?.email?.split("@")[0] || "there";
  const hour = new Date().getHours();

  return (
    <div className="dashboard-stack space-y-6">
      <div className="dashboard-wash" aria-hidden="true" />
      <header className="relative z-[1] max-w-2xl">
        <h1 className="title-fluid font-display font-semibold text-foreground">
          {greetingForHour(hour)}, {greetingName}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground sm:text-[15px]">
          Your next opportunities are ready.
        </p>
      </header>
      <ErrorBanner error={error} />
      {loading ? (
        <div className="relative z-[1] space-y-4" aria-busy>
          <Skeleton className="h-36 w-full" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        </div>
      ) : (
        <>
          <Glass variant="panel" className="rounded-[var(--radius-lg)] p-6">
            <h2 className="section-title font-display">{next.title}</h2>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{next.description}</p>
            <Link to={next.to} className="btn-primary mt-5 inline-flex" data-testid="dashboard-next-action">
              {next.cta}
            </Link>
          </Glass>

          <Glass variant="panel" className="rounded-[var(--radius-lg)] p-5">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="section-title font-display">Top matches</h2>
              <Link to="/jobs?tab=matches" className="text-sm font-medium text-foreground underline-offset-2 hover:underline">
                View all matches
              </Link>
            </div>
            {matches.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
                No ranked matches yet. Find jobs, then open Matches for your personal ranking.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-border">
                {matches.map(({ job, score }) => {
                  const mode = workModeLabel(job.work_mode);
                  const place = [job.location, mode].filter(Boolean).join(" · ");
                  const reason =
                    score.score_kind === "verified"
                      ? score.rationale?.split(".")[0]
                      : null;
                  return (
                    <li key={score.job_id}>
                      <Link
                        to={`/jobs/${score.job_id}`}
                        className="flex flex-wrap items-start justify-between gap-3 py-3 text-sm"
                      >
                        <span className="min-w-0">
                          <span className="block font-semibold text-foreground">{job.title}</span>
                          <span className="mt-0.5 block text-muted-foreground">
                            {job.company}
                            {place ? ` · ${place}` : ""}
                          </span>
                          {reason ? (
                            <span className="mt-1 block text-[13px] text-muted-foreground">{reason}.</span>
                          ) : null}
                        </span>
                        <MatchBadge
                          score={score.overall_score}
                          scoreKind={score.score_kind}
                          matchTier={score.match_tier}
                          compact
                        />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Glass>

          <div className="grid gap-4 lg:grid-cols-2">
            <Glass variant="panel" className="rounded-[var(--radius-lg)] p-5">
              <h2 className="section-title font-display">Profile readiness</h2>
              <div className="mt-4">
                <Progress value={(readinessDone / readiness.length) * 100} label={`${readinessDone} of ${readiness.length} complete`} />
              </div>
              <ul className="mt-4 space-y-2 text-sm">
                {readiness.map((item) => (
                  <li key={item.label} className="flex items-center justify-between gap-3">
                    <span className={item.done ? "text-muted-foreground" : "text-foreground"}>{item.label}</span>
                    <span className="text-xs font-medium text-muted-foreground">{item.done ? "Done" : "Missing"}</span>
                  </li>
                ))}
              </ul>
            </Glass>
            <Glass variant="panel" className="rounded-[var(--radius-lg)] p-5">
              <h2 className="section-title font-display">Recent activity</h2>
              {versions.length === 0 ? (
                <p className="mt-3 text-sm text-muted-foreground">No resume versions or applications yet.</p>
              ) : (
                <ul className="mt-3 space-y-2.5 text-sm">
                  {versions.slice(0, 4).map((version) => (
                    <li key={version.id}>
                      <Link to={`/resume/${version.id}`} className="flex justify-between gap-3">
                        <span className="min-w-0 wrap-anywhere">
                          Resume v{version.version_number} · {version.company}
                        </span>
                        <span className="shrink-0 tabular text-muted-foreground">
                          {new Date(version.created_at).toLocaleDateString()}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Glass>
          </div>
        </>
      )}
    </div>
  );
}

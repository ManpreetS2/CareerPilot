import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ErrorBanner } from "../components/ErrorBanner";
import { ReadinessPath } from "../components/signature/ReadinessPath";
import { ScoreOrb } from "../components/signature/ScoreOrb";
import { WorkflowPath } from "../components/signature/WorkflowPath";
import { Glass } from "../components/ui/glass";
import { DashboardAtmosphere } from "../components/DashboardAtmosphere";
import { Skeleton } from "../components/ui/skeleton";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { resolveNextAction } from "../lib/dashboard-next-action";
import { shouldPromptFinishSetup } from "../lib/onboarding";
import { queryKeys } from "../lib/query-keys";
import { useCandidateSession } from "../lib/session";

export function DashboardPage() {
  const { user } = useAuth();
  const { candidate, preferences, sessionUserId } = useCandidateSession();

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
    queryKey: queryKeys.profile(sessionUserId),
    queryFn: ({ signal }) => api.getProfile({ signal }),
  });

  const summaryQuery = useQuery({
    queryKey: queryKeys.dashboardSummary,
    queryFn: async ({ signal }) => {
      try {
        return await api.getDashboardSummary({ signal });
      } catch {
        return null;
      }
    },
  });

  const loading =
    jobsQuery.isPending ||
    scoresQuery.isPending ||
    versionsQuery.isPending ||
    profileQuery.isPending ||
    summaryQuery.isPending;
  const jobs = jobsQuery.data ?? [];
  const scores = scoresQuery.data ?? [];
  const versions = versionsQuery.data ?? [];
  const summary = summaryQuery.data;
  const liveCandidate = profileQuery.data?.candidate ?? candidate;
  const livePreferences = profileQuery.data?.preferences ?? preferences;
  const readiness = profileQuery.data?.readiness;
  const profileReady = Boolean(readiness?.ready);
  const next = resolveNextAction({
    readiness,
    jobs,
    scores,
    resumeVersions: versions,
  });
  const strong = scores.filter((score) => score.score_kind === "verified");
  const readinessFlags = [
    Boolean(liveCandidate?.name),
    Boolean(liveCandidate?.skills.length),
    Boolean(liveCandidate?.experience.length),
    Boolean(liveCandidate?.projects.length),
    Boolean(livePreferences?.target_roles?.length),
  ];

  const greetingName =
    liveCandidate?.name?.split(" ")[0] || user?.email?.split("@")[0] || "there";
  const searchFocus = livePreferences?.target_roles?.[0];
  const pipelineBits = [
    { label: "Ready to apply", value: summary?.ready_to_apply ?? 0 },
    { label: "Applied", value: summary?.applications_applied ?? 0 },
    { label: "Interviews", value: summary?.interviews ?? 0 },
  ].filter((item) => item.value > 0);

  return (
    <div className="relative space-y-8">
      <DashboardAtmosphere />
      <div className="relative z-[1]">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Dashboard</h1>
        <p className="mt-2 text-lg text-foreground">Welcome back, {greetingName}</p>
        <p className="mt-2 text-muted-foreground">
          {searchFocus
            ? `Current search focus: ${searchFocus}`
            : "Your next opportunities are ready"}
        </p>
      </div>

      <ErrorBanner error={jobsQuery.error} />
      {profileQuery.isError ? (
        <Glass variant="atmosphere" className="relative z-[1] rounded-[var(--radius-lg)] p-4" data-testid="dashboard-profile-error">
          <p className="font-display text-base font-semibold tracking-tight">Couldn't load your profile</p>
          <p className="mt-1 text-sm text-muted-foreground">
            CareerPilot paused discovery until it can read your profile.
          </p>
          <button type="button" className="btn-primary mt-3 inline-flex" onClick={() => void profileQuery.refetch()}>
            Retry
          </button>
        </Glass>
      ) : null}

      {loading ? (
        <div className="relative z-[1] space-y-4" aria-busy>
          <Skeleton className="h-36 w-full" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        </div>
      ) : profileQuery.isError ? null : (
        <>
          <Glass variant="floating" className="relative z-[1] rounded-2xl p-8">
            <p className="text-sm font-medium text-primary">Next Action</p>
            <h2 className="mt-3 text-2xl font-bold tracking-tight text-foreground">{next.title}</h2>
            <p className="mt-3 max-w-2xl leading-relaxed text-muted-foreground">{next.description}</p>
            <Link
              to={next.to}
              className="btn-primary mt-6 inline-flex"
              data-testid="dashboard-next-action"
            >
              {next.cta}
            </Link>
            {user && shouldPromptFinishSetup(user.id) ? (
              <p className="mt-4 text-sm text-muted-foreground">
                You can also{" "}
                <Link to="/onboarding" className="font-semibold text-primary hover:text-primary-hover">
                  finish setup
                </Link>{" "}
                when you have a minute.
              </p>
            ) : null}
          </Glass>

          <div className="relative z-[1]">
            <WorkflowPath
              nodes={[
                { id: "profile", label: "Profile", state: liveCandidate?.name ? "complete" : "current" },
                { id: "discover", label: "Discover", state: jobs.length ? "complete" : "upcoming" },
                { id: "analyze", label: "Analyze", state: scores.length ? "complete" : jobs.length ? "current" : "upcoming" },
                { id: "prepare", label: "Prepare", state: versions.length ? "complete" : "upcoming" },
                { id: "track", label: "Track", state: pipelineBits.length ? "current" : "upcoming" },
              ]}
            />
          </div>

          <div className="relative z-[1] grid gap-4 lg:grid-cols-2">
            <Glass variant="panel" className="rounded-2xl p-6">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-foreground">Top Matches</h2>
                <Link to="/jobs?tab=matches" className="text-sm font-medium text-primary hover:text-primary-hover">
                  View All
                </Link>
              </div>
              { !profileReady ? (
                <p className="mt-4 text-sm text-muted-foreground" data-testid="dashboard-matches-gate">
                  Complete your profile to see matches.
                </p>
              ) : strong.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground">
                  No verified matches yet. Open Matches to review rankings.
                </p>
              ) : (
                <ul className="mt-4 space-y-4">
                  {strong.slice(0, 3).map((score) => {
                    const job = jobs.find((item) => item.id === score.job_id);
                    return (
                      <li key={score.job_id}>
                        <Link to={`/jobs/${score.job_id}`} className="group flex items-start gap-4 rounded-xl border border-border/70 bg-foreground/[0.03] p-3 transition-colors hover:border-primary/30 hover:bg-foreground/[0.05]">
                          <ScoreOrb score={score.overall_score} compact />
                          <div className="min-w-0">
                            <p className="font-semibold text-foreground group-hover:text-primary">{job?.title ?? "Role"}</p>
                            <p className="mt-1 text-sm text-muted-foreground">{job?.company ?? "Company"}</p>
                          </div>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Glass>

            <Glass variant="panel" className="rounded-2xl p-6">
              <h2 className="text-lg font-semibold text-foreground">Profile Readiness</h2>
              <div className="mt-4">
                <ReadinessPath flags={readinessFlags} />
              </div>
              <dl className="mt-6 grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-sm text-muted-foreground">Skills</dt>
                  <dd className="mt-1 text-2xl font-bold tabular text-foreground">{liveCandidate?.skills.length ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Jobs discovered</dt>
                  <dd className="mt-1 text-2xl font-bold tabular text-foreground">{jobs.length}</dd>
                </div>
              </dl>
            </Glass>

            <Glass variant="panel" className="rounded-2xl p-6">
              <h2 className="text-lg font-semibold text-foreground">Recent Versions</h2>
              {versions.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground">No resume versions yet.</p>
              ) : (
                <ul className="mt-4 space-y-3">
                  {versions.slice(0, 3).map((version) => (
                    <li key={version.id}>
                      <Link to={`/resume/${version.id}`} className="group flex items-center justify-between gap-3 rounded-lg border border-border/70 bg-foreground/[0.03] p-3 transition-colors hover:border-primary/30 hover:bg-foreground/[0.05]">
                        <span className="min-w-0 text-sm">
                          <span className="font-medium text-foreground group-hover:text-primary">
                            Version {version.version_number}
                          </span>
                          <span className="text-muted-foreground"> · {version.company}</span>
                        </span>
                        <span className="shrink-0 text-xs tabular text-muted-foreground">
                          {new Date(version.created_at).toLocaleDateString()}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Glass>

            <Glass variant="panel" className="rounded-2xl p-6">
              <h2 className="text-lg font-semibold text-foreground">Application Pipeline</h2>
              {pipelineBits.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground">
                  Nothing in your tracker yet.
                </p>
              ) : (
                <dl className="mt-4 space-y-3">
                  {pipelineBits.map((item) => (
                    <div key={item.label} className="flex items-center justify-between rounded-lg border border-border/70 bg-foreground/[0.03] p-3">
                      <dt className="text-sm text-muted-foreground">{item.label}</dt>
                      <dd className="text-xl font-bold tabular text-foreground">{item.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <Link
                to="/track"
                className="mt-4 inline-block text-sm font-semibold text-primary hover:text-primary-hover"
              >
                Open Tracker →
              </Link>
            </Glass>
          </div>
        </>
      )}
    </div>
  );
}

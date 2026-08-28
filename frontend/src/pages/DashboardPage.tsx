import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ErrorBanner } from "../components/ErrorBanner";
import { ReadinessPath } from "../components/signature/ReadinessPath";
import { ScoreOrb } from "../components/signature/ScoreOrb";
import { WorkflowPath } from "../components/signature/WorkflowPath";
import { Glass } from "../components/ui/glass";
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { resolveNextAction } from "../lib/dashboard-next-action";
import { shouldPromptFinishSetup } from "../lib/onboarding";
import { queryKeys } from "../lib/query-keys";
import { useCandidateSession } from "../lib/session";

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
  const error = jobsQuery.error ?? profileQuery.error;
  const jobs = jobsQuery.data ?? [];
  const scores = scoresQuery.data ?? [];
  const versions = versionsQuery.data ?? [];
  const summary = summaryQuery.data;
  const liveCandidate = profileQuery.data?.candidate ?? candidate;
  const livePreferences = profileQuery.data?.preferences ?? preferences;
  const next = resolveNextAction({
    candidate: liveCandidate,
    preferences: livePreferences,
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
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description={
          searchFocus
            ? `Welcome back, ${greetingName}. Current search focus: ${searchFocus}.`
            : `Welcome back, ${greetingName}. One next step, then the real signals CareerPilot already has.`
        }
      />
      <ErrorBanner error={error} />
      {loading ? (
        <div className="space-y-4" aria-busy>
          <Skeleton className="h-36 w-full" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        </div>
      ) : (
        <>
          <Glass variant="atmosphere" refract className="rounded-[var(--radius-lg)] p-6">
            <p className="cp-kicker">Next action</p>
            <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight">{next.title}</h2>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{next.description}</p>
            <Link to={next.to} className="btn-primary mt-4 inline-flex" data-testid="dashboard-next-action">
              {next.cta}
            </Link>
            {user && shouldPromptFinishSetup(user.id) ? (
              <p className="mt-3 text-sm text-muted-foreground">
                You can also{" "}
                <Link to="/onboarding" className="font-semibold text-primary">
                  finish setup
                </Link>{" "}
                when you have a minute.
              </p>
            ) : null}
          </Glass>

          <WorkflowPath
            nodes={[
              { id: "profile", label: "Profile", state: liveCandidate?.name ? "complete" : "current" },
              { id: "discover", label: "Discover", state: jobs.length ? "complete" : "upcoming" },
              { id: "analyze", label: "Analyze", state: scores.length ? "complete" : jobs.length ? "current" : "upcoming" },
              { id: "prepare", label: "Prepare", state: versions.length ? "complete" : "upcoming" },
              { id: "track", label: "Track", state: pipelineBits.length ? "current" : "upcoming" },
            ]}
          />

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
            <Glass variant="working" className="rounded-[var(--radius-lg)] p-5">
              <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-lg font-semibold">Strongest matches</h2>
              <Link to="/jobs?tab=matches" className="text-sm font-medium text-primary">
                Open Matches
              </Link>
              </div>
              {strong.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">
                  No verified matches yet. Open Matches to review Potential Match rankings.
                </p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {strong.slice(0, 4).map((score) => {
                    const job = jobs.find((item) => item.id === score.job_id);
                    return (
                      <li key={score.job_id}>
                        <Link to={`/jobs/${score.job_id}`} className="flex items-start gap-3 text-sm">
                          <ScoreOrb score={score.overall_score} compact />
                          <span className="min-w-0 wrap-anywhere">
                            <span className="font-semibold">{job?.title ?? "Role"}</span>
                            <span className="mt-0.5 block text-muted-foreground">{job?.company ?? "Company"}</span>
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Glass>
            <Glass variant="working" className="rounded-[var(--radius-lg)] p-5">
              <h2 className="font-display text-lg font-semibold">Profile readiness</h2>
              <div className="mt-3">
                <ReadinessPath flags={readinessFlags} />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Skills</dt>
                  <dd className="tabular font-semibold">{liveCandidate?.skills.length ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Jobs discovered</dt>
                  <dd className="tabular font-semibold">{jobs.length}</dd>
                </div>
              </dl>
            </Glass>
            <div className="rounded-[var(--radius-lg)] border border-border/70 p-5">
              <h2 className="font-display text-lg font-semibold">Recent resume versions</h2>
              {versions.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">No approved resume versions yet.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {versions.slice(0, 4).map((version) => (
                    <li key={version.id}>
                      <Link to={`/resume/${version.id}`} className="flex justify-between gap-3">
                        <span className="min-w-0 wrap-anywhere">
                          Version {version.version_number} · {version.company}
                        </span>
                        <span className="shrink-0 tabular text-muted-foreground">
                          {new Date(version.created_at).toLocaleDateString()}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-[var(--radius-lg)] border border-border/70 p-5">
              <h2 className="font-display text-lg font-semibold">Application pipeline</h2>
              {pipelineBits.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">
                  Nothing is in your tracker yet. Save or prepare a role when you are ready — zeros
                  are not a scoreboard.
                </p>
              ) : (
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  {pipelineBits.map((item) => (
                    <div key={item.label}>
                      <dt className="text-muted-foreground">{item.label}</dt>
                      <dd className="tabular font-semibold">{item.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <p className="mt-3 text-sm">
                <Link to="/track" className="font-semibold text-primary">
                  Open Track
                </Link>
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

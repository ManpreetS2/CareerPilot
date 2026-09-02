import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/ui/page-header";
import { Surface } from "../components/ui/surface";
import { api, ApiClientError } from "../lib/api";
import { queryKeys } from "../lib/query-keys";
import type { EvidenceState, PriorityLabel, SkillGrowthItem } from "../lib/types";

type FilterId = "all" | "high" | "partial" | "unknown" | "saved";

const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "high", label: "High priority" },
  { id: "partial", label: "Partial evidence" },
  { id: "unknown", label: "No verified evidence" },
  { id: "saved", label: "Saved jobs only" },
];

const PRIORITY_COPY: Record<PriorityLabel, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const EVIDENCE_COPY: Record<EvidenceState, string> = {
  satisfied: "Verified across profile evidence",
  partial: "Partial — strengthen evidence",
  unknown: "No verified profile evidence",
  not_satisfied: "Not supported by current evaluation",
};

function isProfileRequired(error: unknown): boolean {
  if (!(error instanceof ApiClientError) || error.status !== 409) return false;
  const detail = error.detail;
  if (detail && typeof detail === "object" && detail !== null && "code" in detail) {
    return (detail as { code?: string }).code === "profile_required";
  }
  return true;
}

function matchesFilter(item: SkillGrowthItem, filter: FilterId): boolean {
  if (filter === "all") return true;
  if (filter === "high") return item.priority === "high";
  if (filter === "partial") return item.candidate_evidence_state === "partial";
  if (filter === "unknown") return item.candidate_evidence_state === "unknown";
  return item.related_jobs.some((job) => job.saved);
}

export function GrowthPage() {
  const [filter, setFilter] = useState<FilterId>("all");
  const growthQuery = useQuery({
    queryKey: queryKeys.careerGrowth,
    queryFn: ({ signal }) => api.getCareerGrowth({ signal }),
    retry: false,
  });

  const summary = growthQuery.data;
  const gaps = useMemo(
    () => (summary?.skill_gaps ?? []).filter((item) => matchesFilter(item, filter)),
    [summary, filter],
  );
  const strengths = summary?.strengths ?? [];
  const highCount = summary?.skill_gaps.filter((item) => item.priority === "high").length ?? 0;
  const refreshCount = (summary?.stale_jobs_excluded ?? 0) + (summary?.unavailable_jobs_excluded ?? 0);

  if (growthQuery.isPending) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
        <PageHeader title="Career Growth" description="Grounded skills gap from jobs you saved and currently match." />
        <LoadingState label="Loading career growth…" />
      </div>
    );
  }

  if (isProfileRequired(growthQuery.error)) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
        <PageHeader title="Career Growth" description="Grounded skills gap from jobs you saved and currently match." />
        <EmptyState
          title="Complete your profile first"
          description="Career Growth needs a usable candidate profile before it can read stored job evidence. CareerPilot will not search or call a provider from this page."
          action={
            <Link to="/profile" className="btn-primary">
              Go to Profile
            </Link>
          }
        />
      </div>
    );
  }

  if (growthQuery.isError) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
        <PageHeader title="Career Growth" description="Grounded skills gap from jobs you saved and currently match." />
        <ErrorBanner error={growthQuery.error} heading="Could not load career growth" />
        <button type="button" className="btn-secondary" onClick={() => void growthQuery.refetch()}>
          Retry
        </button>
      </div>
    );
  }

  if (!summary || summary.jobs_considered === 0) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
        <PageHeader title="Career Growth" description="Grounded skills gap from jobs you saved and currently match." />
        <EmptyState
          title="Discover or save some jobs first"
          description={summary?.notice ?? "Career Growth looks at saved jobs and your strongest current matches. It does not scout on this page."}
          action={
            <Link to="/jobs" className="btn-primary">
              Open Discover
            </Link>
          }
        />
      </div>
    );
  }

  if (summary.jobs_with_current_evidence === 0) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
        <PageHeader
          title="Career Growth"
          description={`Based on ${summary.jobs_considered} relevant jobs: ${summary.saved_jobs_considered} Saved + ${summary.matched_jobs_considered} Top Matches.`}
        />
        <EmptyState
          title="Analyze jobs to build grounded growth insights"
          description={
            summary.stale_jobs_excluded
              ? `${summary.stale_jobs_excluded} job${summary.stale_jobs_excluded === 1 ? "" : "s"} need refreshed analysis before CareerPilot can use them here.`
              : "CareerPilot has jobs in this set, but no current Match Evidence to aggregate."
          }
          action={
            <Link to="/analyze" className="btn-primary">
              Open Analyze
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="min-w-0 max-w-full space-y-6" data-testid="growth-page">
      <PageHeader
        title="Career Growth"
        description={`Based on ${summary.jobs_considered} relevant jobs: ${summary.saved_jobs_considered} Saved + ${summary.matched_jobs_considered} Top Matches. Counts use ${summary.jobs_with_current_evidence} analyzed jobs with current evidence.`}
      />

      <Surface className="grid gap-3 p-5 sm:grid-cols-3" data-testid="growth-summary">
        <SummaryStat label="Key focus areas" value={highCount || summary.skill_gaps.length} />
        <SummaryStat label="Existing strengths" value={strengths.length} />
        <SummaryStat label="Jobs needing refresh" value={refreshCount} />
      </Surface>

      {refreshCount > 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="growth-stale-note">
          {summary.stale_jobs_excluded} stale and {summary.unavailable_jobs_excluded} unavailable jobs were excluded from these counts.
        </p>
      ) : null}

      <div>
        <h2 className="font-display text-xl font-semibold">Growth opportunities</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Advisory only. Absence of stored evidence is not proof you lack a skill.
        </p>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter growth items">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`btn-secondary min-h-11 px-3 text-sm ${filter === item.id ? "ring-2 ring-[var(--ring)]" : ""}`}
              aria-pressed={filter === item.id}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {summary.skill_gaps.length === 0 ? (
        <EmptyState
          title="No repeated skill gaps in this set"
          description="CareerPilot isn't seeing repeated skill gaps in the current job set."
        />
      ) : gaps.length === 0 ? (
        <p className="text-sm text-muted-foreground">No growth items match this filter.</p>
      ) : (
        <ul className="space-y-4">
          {gaps.map((item) => (
            <li key={item.canonical_key}>
              <GrowthCard item={item} />
            </li>
          ))}
        </ul>
      )}

      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold">Strengths already working for you</h2>
        {strengths.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            CareerPilot does not currently have repeated verified skill evidence in this job set.
          </p>
        ) : (
          <ul className="space-y-3">
            {strengths.map((item) => (
              <li key={item.canonical_key}>
                <GrowthCard item={item} strength />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular text-foreground">{value}</p>
    </div>
  );
}

function GrowthCard({ item, strength = false }: { item: SkillGrowthItem; strength?: boolean }) {
  const [open, setOpen] = useState(false);
  const pct = item.denominator ? Math.round((item.jobs_count / item.denominator) * 100) : 0;
  return (
    <Surface className="min-w-0 max-w-full space-y-3 p-5">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="wrap-anywhere font-display text-lg font-semibold">{item.label}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {strength ? "Verified strength" : `${PRIORITY_COPY[item.priority]} priority`}
          </p>
        </div>
        <p className="text-sm font-medium text-foreground">{PRIORITY_COPY[item.priority]}</p>
      </div>

      <p className="text-sm text-foreground">
        Appears in {item.jobs_count} / {item.denominator} analyzed jobs
      </p>
      <div className="h-1.5 overflow-hidden rounded-full bg-foreground/10" aria-hidden>
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-muted-foreground">
        Required in {item.required_count} · Preferred in {item.preferred_count}
      </p>
      <p className="text-sm text-foreground">
        Your evidence: {EVIDENCE_COPY[item.candidate_evidence_state]}
      </p>
      <p className="text-sm text-muted-foreground">{item.reason}</p>
      {strength ? null : (
        <p className="text-sm text-foreground">
          <span className="font-semibold">Next step: </span>
          {item.suggested_action}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide jobs" : "View jobs"}
        </button>
        <Link to="/profile" className="btn-primary">
          Update profile
        </Link>
      </div>
      {open ? (
        <ul className="space-y-2" data-testid={`growth-jobs-${item.canonical_key}`}>
          {item.related_jobs.map((job) => (
            <li key={job.job_id} className="min-w-0">
              <Link
                to={`/jobs/${job.job_id}`}
                className="block min-w-0 rounded-lg border border-border/70 p-3 hover:border-primary/30"
              >
                <p className="wrap-anywhere font-medium text-foreground">{job.title}</p>
                <p className="wrap-anywhere text-sm text-muted-foreground">
                  {job.company} · {job.importance} · {EVIDENCE_COPY[job.evidence_state]}
                  {job.saved ? " · Saved" : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Surface>
  );
}

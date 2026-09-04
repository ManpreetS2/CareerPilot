import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/ui/page-header";
import { Surface } from "../components/ui/surface";
import { api } from "../lib/api";
import { isProfileRequired } from "../lib/profile-gate";
import { queryKeys } from "../lib/query-keys";
import type { ApplicationAnalyticsSummary, BreakdownBucket, FunnelStep } from "../lib/types";

const PAGE_DESCRIPTION =
  "Conversion funnel from saved jobs through offers. Accrues from your own activity going forward — earlier applications aren't backfilled.";

function formatDays(value: number | null): string {
  if (value === null) return "—";
  return value === 1 ? "1 day" : `${value} days`;
}

function formatRate(value: number | null): string {
  if (value === null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function AnalyticsPage() {
  const analyticsQuery = useQuery({
    queryKey: queryKeys.analytics,
    queryFn: ({ signal }) => api.getAnalyticsSummary({ signal }),
    retry: false,
  });

  if (analyticsQuery.isPending) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="analytics-page">
        <PageHeader title="Analytics" description={PAGE_DESCRIPTION} />
        <LoadingState label="Loading analytics…" />
      </div>
    );
  }

  if (isProfileRequired(analyticsQuery.error)) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="analytics-page">
        <PageHeader title="Analytics" description={PAGE_DESCRIPTION} />
        <EmptyState
          title="Complete your profile first"
          description="Analytics reads your own saved jobs and tracked applications, which need a usable candidate profile first. CareerPilot will not search or call a provider from this page."
          action={
            <Link to="/profile" className="btn-primary">
              Go to Profile
            </Link>
          }
        />
      </div>
    );
  }

  if (analyticsQuery.isError) {
    return (
      <div className="min-w-0 max-w-full space-y-6" data-testid="analytics-page">
        <PageHeader title="Analytics" description={PAGE_DESCRIPTION} />
        <ErrorBanner error={analyticsQuery.error} heading="Could not load analytics" />
        <button type="button" className="btn-secondary" onClick={() => void analyticsQuery.refetch()}>
          Retry
        </button>
      </div>
    );
  }

  const summary = analyticsQuery.data as ApplicationAnalyticsSummary;
  const topCount = summary.funnel[0]?.jobs_count ?? 0;

  return (
    <div className="min-w-0 max-w-full space-y-6" data-testid="analytics-page">
      <PageHeader title="Analytics" description={PAGE_DESCRIPTION} />

      {summary.notice ? (
        <p className="text-sm text-muted-foreground" data-testid="analytics-notice">
          {summary.notice}
        </p>
      ) : null}

      {topCount === 0 ? (
        <EmptyState
          title="No conversion activity yet"
          description="Save a job and move it through Prepare and Track to start building your funnel."
          action={
            <Link to="/jobs" className="btn-primary">
              Open Discover
            </Link>
          }
        />
      ) : null}

      <Surface className="space-y-4 p-5" data-testid="analytics-funnel">
        <h2 className="font-display text-xl font-semibold">Funnel</h2>
        <ul className="space-y-3">
          {summary.funnel.map((step) => (
            <FunnelRow key={step.stage} step={step} maxCount={topCount} />
          ))}
        </ul>
      </Surface>

      <Surface className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4" data-testid="analytics-summary">
        <SummaryStat label="Rejected" value={String(summary.rejected_count)} />
        <SummaryStat label="Withdrawn" value={String(summary.withdrawn_count)} />
        <SummaryStat label="Median days, saved → applied" value={formatDays(summary.median_days_saved_to_applied)} />
        <SummaryStat
          label="Median days, applied → interviewing"
          value={formatDays(summary.median_days_applied_to_interviewing)}
        />
      </Surface>

      <BreakdownSection title="By job source" buckets={summary.by_source} testId="analytics-by-source" />
      <BreakdownSection
        title="By match-score band"
        buckets={summary.by_match_score_band}
        testId="analytics-by-score-band"
      />
    </div>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular text-foreground">{value}</p>
    </div>
  );
}

function FunnelRow({ step, maxCount }: { step: FunnelStep; maxCount: number }) {
  const pct = maxCount ? Math.round((step.jobs_count / maxCount) * 100) : 0;
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-foreground">{step.label}</p>
        <p className="text-sm text-muted-foreground">
          {step.jobs_count}
          {step.conversion_from_previous !== null ? ` · ${formatRate(step.conversion_from_previous)} of previous` : null}
        </p>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-foreground/10" aria-hidden>
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}

function BreakdownSection({
  title,
  buckets,
  testId,
}: {
  title: string;
  buckets: BreakdownBucket[];
  testId: string;
}) {
  if (buckets.length === 0) return null;
  return (
    <Surface className="space-y-3 p-5" data-testid={testId}>
      <h2 className="font-display text-xl font-semibold">{title}</h2>
      <ul className="space-y-2">
        {buckets.map((bucket) => (
          <li key={bucket.label} className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-foreground">{bucket.label}</span>
            <span className="text-muted-foreground">
              {bucket.applied_count} / {bucket.total_count} applied ({formatRate(bucket.applied_rate)})
              {bucket.small_sample ? " · too few to trust" : ""}
            </span>
          </li>
        ))}
      </ul>
    </Surface>
  );
}

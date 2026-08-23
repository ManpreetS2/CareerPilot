import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { StatusBadge } from "../components/StatusBadge";
import { api, ApiClientError } from "../lib/api";
import type { ApplicationListItem, TrackerStatus } from "../lib/types";

const TRACKER_STATUSES: TrackerStatus[] = [
  "saved",
  "pending_review",
  "approved",
  "ready_to_apply",
  "applied",
  "interviewing",
  "rejected",
  "offer",
  "withdrawn",
];

function formatUpdated(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

export function ApplicationsPage() {
  const [items, setItems] = useState<ApplicationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  async function loadList() {
    setLoading(true);
    setError(null);
    try {
      const next = await api.listApplications();
      setItems(next);
    } catch (err) {
      setError(err);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadList();
  }, []);

  async function handleStatusChange(jobId: string, nextStatus: TrackerStatus) {
    setUpdatingId(jobId);
    setError(null);
    try {
      const updated = await api.updateTracking(jobId, nextStatus);
      setItems((current) =>
        current.map((item) =>
          item.job_id === jobId
            ? {
                ...item,
                tracker_status: updated.status ?? nextStatus,
                updated_at: updated.updated_at ?? item.updated_at,
              }
            : item,
        ),
      );
    } catch (err) {
      setError(err instanceof ApiClientError ? err : err);
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-4xl font-semibold">Applications</h1>
        <p className="mt-2 max-w-2xl text-ink-600 dark:text-ink-300">
          Track saved roles without changing approval decisions or assisted-apply results. Status
          updates run only when you choose a new value.
        </p>
      </div>

      <ErrorBanner error={error} />

      {loading ? (
        <LoadingState label="Loading applications…" />
      ) : items.length === 0 ? (
        <EmptyState
          title="No applications yet"
          description="Discovered jobs will appear here. Open a job to review materials, then set a tracking status when you are ready."
          action={
            <Link to="/jobs" className="btn-primary">
              Browse jobs
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4">
          {items.map((item) => (
            <article key={item.job_id} className="card p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="font-display text-xl font-semibold">{item.title}</h2>
                  <p className="text-sm text-ink-600 dark:text-ink-300">{item.company}</p>
                  <p className="mt-1 text-xs text-ink-500">
                    Last updated {formatUpdated(item.updated_at)}
                  </p>
                </div>
                <MatchBadge
                  score={item.match_score}
                  recommendation={item.recommendation}
                />
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                {item.approval_status ? (
                  <StatusBadge status={item.approval_status} />
                ) : (
                  <span className="text-xs text-ink-500">No approval yet</span>
                )}
                {item.tracker_status ? (
                  <StatusBadge status={item.tracker_status} />
                ) : (
                  <span className="text-xs text-ink-500">Not tracked</span>
                )}
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <label className="flex min-w-[12rem] flex-col gap-1 text-sm">
                  <span className="text-ink-500">Tracking status</span>
                  <select
                    className="input"
                    aria-label={`Tracking status for ${item.title} at ${item.company}`}
                    value={item.tracker_status ?? ""}
                    disabled={updatingId === item.job_id}
                    onChange={(event) => {
                      const value = event.target.value as TrackerStatus;
                      if (!value || value === item.tracker_status) return;
                      void handleStatusChange(item.job_id, value);
                    }}
                  >
                    <option value="" disabled>
                      Set status…
                    </option>
                    {TRACKER_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <Link
                  to={`/applications/${item.job_id}`}
                  className="btn-ghost px-2 py-1.5 text-accent-700 dark:text-accent-300"
                >
                  Open application
                  <ArrowUpRight className="h-4 w-4" aria-hidden />
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

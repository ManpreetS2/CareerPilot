import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, LayoutGrid, List } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { StatusBadge } from "../components/StatusBadge";
import { PageHeader } from "../components/ui/page-header";
import { Glass } from "../components/ui/glass";
import { api, ApiClientError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/cn";
import { readTrackerView, saveTrackerView, type TrackerView } from "../lib/tracker-view";
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

const KANBAN_COLUMNS: { id: TrackerStatus | "untracked"; label: string }[] = [
  { id: "untracked", label: "Not tracked" },
  ...TRACKER_STATUSES.map((status) => ({
    id: status,
    label: status.replaceAll("_", " "),
  })),
];

function statusOptions(item: ApplicationListItem): TrackerStatus[] {
  if (item.allowed_statuses && item.allowed_statuses.length > 0) {
    return item.allowed_statuses;
  }
  return TRACKER_STATUSES;
}

function formatUpdated(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function columnItems(items: ApplicationListItem[], column: TrackerStatus | "untracked") {
  if (column === "untracked") return items.filter((item) => !item.tracker_status);
  return items.filter((item) => item.tracker_status === column);
}

function TrackerCard({
  item,
  updating,
  onStatusChange,
  onReminderChange,
}: {
  item: ApplicationListItem;
  updating: boolean;
  onStatusChange: (jobId: string, status: TrackerStatus) => void;
  onReminderChange: (jobId: string, date: string | null) => void;
}) {
  return (
    <article className="card space-y-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-base font-semibold leading-snug">{item.title}</h2>
          <p className="text-sm text-muted-foreground">{item.company}</p>
          <p className="mt-1 text-xs text-muted-foreground">Updated {formatUpdated(item.updated_at)}</p>
        </div>
        <MatchBadge score={item.match_score} recommendation={item.recommendation} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {item.approval_status ? (
          <StatusBadge status={item.approval_status} />
        ) : (
          <span className="text-xs text-muted-foreground">No approval yet</span>
        )}
        {item.tracker_status ? <StatusBadge status={item.tracker_status} /> : null}
      </div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-[10rem] flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Tracking status</span>
            <select
              className="input"
              aria-label={`Tracking status for ${item.title} at ${item.company}`}
              value={item.tracker_status ?? ""}
              disabled={updating}
              onChange={(event) => {
                const value = event.target.value as TrackerStatus;
                if (!value || value === item.tracker_status) return;
                onStatusChange(item.job_id, value);
              }}
            >
              <option value="" disabled>
                Set status…
              </option>
              {statusOptions(item).map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[9rem] flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Follow-up</span>
            <input
              type="date"
              className="input"
              aria-label={`Follow-up reminder date for ${item.title} at ${item.company}`}
              value={item.reminder_date ?? ""}
              disabled={updating || !item.tracker_status}
              title={item.tracker_status ? undefined : "Set a tracking status first"}
              onChange={(event) => onReminderChange(item.job_id, event.target.value || null)}
            />
          </label>
        </div>
        <Link to={`/jobs/${item.job_id}/prepare`} className="btn-ghost px-2 py-1.5 text-primary">
          Open application
          <ArrowUpRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </article>
  );
}

export function ApplicationsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<ApplicationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [view, setView] = useState<TrackerView>(() => (user ? readTrackerView(user.id) : "list"));

  useEffect(() => {
    if (user) setView(readTrackerView(user.id));
  }, [user]);

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

  function setPersistedView(next: TrackerView) {
    setView(next);
    if (user) saveTrackerView(user.id, next);
  }

  async function handleStatusChange(jobId: string, nextStatus: TrackerStatus) {
    const current = items.find((item) => item.job_id === jobId);
    setUpdatingId(jobId);
    setError(null);
    try {
      const updated = await api.updateTracking(jobId, nextStatus, undefined, current?.reminder_date);
      setItems((prev) =>
        prev.map((item) =>
          item.job_id === jobId
            ? {
                ...item,
                tracker_status: updated.status ?? nextStatus,
                reminder_date: updated.reminder_date ?? item.reminder_date,
                updated_at: updated.updated_at ?? item.updated_at,
                allowed_statuses: updated.allowed_statuses ?? item.allowed_statuses,
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

  async function handleReminderDateChange(jobId: string, nextDate: string | null) {
    const current = items.find((item) => item.job_id === jobId);
    if (!current?.tracker_status) return;
    setUpdatingId(jobId);
    setError(null);
    try {
      const updated = await api.updateTracking(jobId, current.tracker_status, undefined, nextDate);
      setItems((prev) =>
        prev.map((item) =>
          item.job_id === jobId
            ? {
                ...item,
                reminder_date: updated.reminder_date ?? nextDate,
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

  const timeline = useMemo(() => {
    return [...items].sort((a, b) => {
      const at = a.updated_at ? Date.parse(a.updated_at) : 0;
      const bt = b.updated_at ? Date.parse(b.updated_at) : 0;
      return bt - at;
    });
  }, [items]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Track"
        description="Kanban on desktop, list/timeline when you want chronology. Status changes use the same tracker API and never rely on drag-and-drop."
        actions={
          <div className="flex rounded-[var(--radius-sm)] border border-border p-1" role="group" aria-label="Tracker view">
            <button
              type="button"
              className={cn("btn-ghost h-9 px-3", view === "kanban" && "bg-primary/10 text-foreground")}
              aria-pressed={view === "kanban"}
              onClick={() => setPersistedView("kanban")}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
              Kanban
            </button>
            <button
              type="button"
              className={cn("btn-ghost h-9 px-3", view === "list" && "bg-primary/10 text-foreground")}
              aria-pressed={view === "list"}
              onClick={() => setPersistedView("list")}
            >
              <List className="h-4 w-4" aria-hidden />
              List
            </button>
          </div>
        }
      />

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
      ) : view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto pb-2" data-testid="tracker-kanban">
          {KANBAN_COLUMNS.map((column) => {
            const columnJobs = columnItems(items, column.id);
            return (
              <section
                key={column.id}
                className="w-[18.5rem] shrink-0"
                aria-label={`${column.label} column`}
              >
                <Glass variant="subtle" className="mb-3 rounded-[var(--radius-md)] px-3 py-2">
                  <h2 className="text-sm font-semibold capitalize">{column.label}</h2>
                  <p className="text-xs text-muted-foreground">{columnJobs.length}</p>
                </Glass>
                <div className="space-y-3">
                  {columnJobs.length === 0 ? (
                    <p className="px-1 text-xs text-muted-foreground">Empty</p>
                  ) : (
                    columnJobs.map((item) => (
                      <TrackerCard
                        key={item.job_id}
                        item={item}
                        updating={updatingId === item.job_id}
                        onStatusChange={(jobId, status) => void handleStatusChange(jobId, status)}
                        onReminderChange={(jobId, date) => void handleReminderDateChange(jobId, date)}
                      />
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <ol className="space-y-4" data-testid="tracker-list">
          {timeline.map((item) => (
            <li key={item.job_id}>
              <TrackerCard
                item={item}
                updating={updatingId === item.job_id}
                onStatusChange={(jobId, status) => void handleStatusChange(jobId, status)}
                onReminderChange={(jobId, date) => void handleReminderDateChange(jobId, date)}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

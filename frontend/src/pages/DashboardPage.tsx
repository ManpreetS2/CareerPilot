import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  Search,
  Upload,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { api } from "../lib/api";
import type { DashboardSummary } from "../lib/types";

const EMPTY_SUMMARY: DashboardSummary = {
  profile_completion: 0,
  skills_count: 0,
  target_roles: [],
  preferred_location: null,
  jobs_discovered: 0,
  jobs_verified: 0,
  high_matches: 0,
  ready_to_apply: 0,
  applications_saved: 0,
  applications_ready: 0,
  applications_applied: 0,
  interviews: 0,
};

export function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const next = await api.getDashboardSummary();
        if (!cancelled) setSummary(next);
      } catch (err) {
        if (!cancelled) {
          setError(err);
          setSummary(EMPTY_SUMMARY);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const metrics = summary ?? EMPTY_SUMMARY;

  return (
    <div className="space-y-8">
      <section className="card overflow-hidden p-6 sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-wide text-accent-700 dark:text-accent-300">
              CareerPilot
            </p>
            <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight sm:text-5xl">
              Find the right jobs. Understand your fit. Apply smarter.
            </h1>
            <p className="mt-3 text-ink-600 dark:text-ink-300">
              Build a grounded candidate profile, discover roles, and move toward human-approved
              applications — without inventing experience you do not have.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/profile" className="btn-primary">
              <Upload className="h-4 w-4" aria-hidden />
              Upload Resume / Build Profile
            </Link>
            <Link to="/jobs" className="btn-secondary">
              <Search className="h-4 w-4" aria-hidden />
              Find Jobs
            </Link>
          </div>
        </div>
      </section>

      <ErrorBanner error={error} />
      {loading ? (
        <LoadingState label="Loading dashboard…" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <DashboardCard
            icon={UserRound}
            title="Candidate Profile"
            rows={[
              ["Completion", `${metrics.profile_completion}%`],
              ["Skills", String(metrics.skills_count)],
              [
                "Target roles",
                metrics.target_roles.length
                  ? metrics.target_roles.slice(0, 2).join(", ")
                  : "Not set",
              ],
              ["Preferred location", metrics.preferred_location ?? "Not set"],
            ]}
            action={<Link to="/profile" className="btn-ghost px-0">Open profile</Link>}
          />
          <DashboardCard
            icon={BriefcaseBusiness}
            title="Job Pipeline"
            rows={[
              ["Discovered", String(metrics.jobs_discovered)],
              ["Verified", String(metrics.jobs_verified)],
              ["High matches", String(metrics.high_matches)],
              ["Ready to apply", String(metrics.ready_to_apply)],
            ]}
            action={<Link to="/jobs" className="btn-ghost px-0">Browse jobs</Link>}
          />
          <DashboardCard
            icon={FileText}
            title="Applications"
            rows={[
              ["Saved", String(metrics.applications_saved)],
              ["Ready", String(metrics.applications_ready)],
              ["Applied", String(metrics.applications_applied)],
              ["Interviews", String(metrics.interviews)],
            ]}
            action={<Link to="/applications" className="btn-ghost px-0">Review materials</Link>}
          />
        </div>
      )}
    </div>
  );
}

function DashboardCard({
  icon: Icon,
  title,
  rows,
  action,
}: {
  icon: typeof UserRound;
  title: string;
  rows: [string, string][];
  action: ReactNode;
}) {
  return (
    <section className="card flex flex-col p-5">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-accent-600/10 text-accent-700 dark:text-accent-300">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <h2 className="font-display text-xl font-semibold">{title}</h2>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-ink-500">{label}</dt>
            <dd className="mt-0.5 font-semibold text-ink-900 dark:text-ink-50">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-auto pt-4">{action}</div>
    </section>
  );
}

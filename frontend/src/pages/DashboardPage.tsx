import { Link } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  Search,
  Upload,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import { DEMO_DASHBOARD_METRICS, useCandidateSession } from "../lib/session";

export function DashboardPage() {
  const { candidate, preferences } = useCandidateSession();
  const metrics = DEMO_DASHBOARD_METRICS;

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

      <div className="grid gap-4 lg:grid-cols-3">
        <DashboardCard
          icon={UserRound}
          title="Candidate Profile"
          rows={[
            ["Completion", `${candidate ? metrics.profileCompletion : 0}%`],
            ["Skills", String(candidate?.skills.length ?? 0)],
            [
              "Target roles",
              preferences?.target_roles?.length
                ? preferences.target_roles.slice(0, 2).join(", ")
                : "Not set",
            ],
            [
              "Preferred location",
              preferences?.preferred_locations?.[0] ?? "Not set",
            ],
          ]}
          action={<Link to="/profile" className="btn-ghost px-0">Open profile</Link>}
        />
        <DashboardCard
          icon={BriefcaseBusiness}
          title="Job Pipeline"
          rows={[
            ["Discovered", String(metrics.jobsDiscovered)],
            ["Verified", String(metrics.jobsVerified)],
            ["High matches", String(metrics.highMatches)],
            ["Ready to apply", String(metrics.readyToApply)],
          ]}
          action={<Link to="/jobs" className="btn-ghost px-0">Browse jobs</Link>}
          footnote="Pipeline counts currently use isolated demo metrics until Job Scout persists live data."
        />
        <DashboardCard
          icon={FileText}
          title="Applications"
          rows={[
            ["Saved", String(metrics.applicationsSaved)],
            ["Ready", String(metrics.applicationsReady)],
            ["Applied", String(metrics.applicationsApplied)],
            ["Interviews", String(metrics.interviews)],
          ]}
          action={<Link to="/applications" className="btn-ghost px-0">Review materials</Link>}
          footnote="Application tracker metrics are placeholders until Day 4+ packaging lands."
        />
      </div>
    </div>
  );
}

function DashboardCard({
  icon: Icon,
  title,
  rows,
  action,
  footnote,
}: {
  icon: typeof UserRound;
  title: string;
  rows: [string, string][];
  action: ReactNode;
  footnote?: string;
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
      {footnote ? <p className="mt-2 text-xs text-ink-500">{footnote}</p> : null}
    </section>
  );
}

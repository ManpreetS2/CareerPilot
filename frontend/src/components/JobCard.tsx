import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { Job, MatchScore } from "../lib/types";
import { MatchBadge } from "./MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "./SourceBadge";
import { StatusBadge } from "./StatusBadge";

function companyInitial(company: string) {
  return company.trim().charAt(0).toUpperCase() || "?";
}

export function JobCard({
  job,
  match,
}: {
  job: Job;
  match?: MatchScore | null;
}) {
  const jobId = job.id ?? "";
  const skillChips = match?.matched_skills?.slice(0, 4) ?? [];
  const seenAgo = scoutedTimeAgo(job.date_scraped);

  return (
    <article className="card p-5 transition hover:-translate-y-0.5 hover:border-accent-400/50">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-600/10 text-sm font-semibold text-accent-700 dark:text-accent-300"
            aria-hidden
          >
            {companyInitial(job.company)}
          </div>
          <div className="min-w-0">
            <h3 className="font-display text-xl font-semibold">{job.title}</h3>
            <p className="text-sm text-ink-600 dark:text-ink-300">{job.company}</p>
            <p className="mt-1 text-sm text-ink-500">
              {job.location || "Location n/a"}
              {job.salary ? ` · ${job.salary}` : ""}
            </p>
          </div>
        </div>
        <MatchBadge
          score={match?.overall_score}
          recommendation={match?.recommendation}
          matchTier={match?.match_tier}
          confidenceLevel={match?.confidence_level}
          compact
        />
      </div>

      {skillChips.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {skillChips.map((skill) => (
            <span
              key={skill}
              className="rounded-lg bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-700 dark:bg-ink-800 dark:text-ink-100"
            >
              {skill}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={job.status} />
          <SourceBadge source={job.source} />
          {seenAgo ? <span className="text-xs text-ink-500">{seenAgo}</span> : null}
        </div>
        {jobId ? (
          <Link to={`/jobs/${jobId}`} className="btn-ghost px-2 py-1.5 text-accent-700 dark:text-accent-300">
            View Analysis
            <ArrowUpRight className="h-4 w-4" aria-hidden />
          </Link>
        ) : null}
      </div>
    </article>
  );
}

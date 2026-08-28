import { Bookmark } from "lucide-react";
import { MatchBadge } from "./MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "./SourceBadge";
import { cn } from "../lib/cn";
import { chipLabel } from "../lib/search-intent";
import type { Job, MatchScore } from "../lib/types";

function companyInitial(company: string) {
  return company.trim().charAt(0).toUpperCase() || "?";
}

function workLabel(job: Job): string | null {
  if (!job.work_mode || job.work_mode === "unknown") return null;
  return chipLabel(job.work_mode);
}

export function JobCard({
  job,
  match,
  selected = false,
  onSelect,
  onToggleSave,
  savePending = false,
}: {
  job: Job;
  match?: MatchScore | null;
  selected?: boolean;
  onSelect?: () => void;
  onToggleSave?: () => void;
  savePending?: boolean;
}) {
  const seenAgo = scoutedTimeAgo(job.date_scraped);
  const employment =
    job.employment_type && job.employment_type !== "unknown" ? chipLabel(job.employment_type) : null;

  return (
    <article
      className={cn(
        "card w-full p-3 text-left transition",
        selected
          ? "job-card-selected glass-refract border-primary/50 bg-primary/[0.07]"
          : "hover:border-accent-400/50",
      )}
    >
      <div className="flex items-start gap-3">
        <button type="button" className="flex min-w-0 flex-1 items-start gap-3 text-left" onClick={onSelect} aria-pressed={selected}>
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-600/10 text-sm font-semibold text-accent-700 dark:text-accent-300"
            aria-hidden
          >
            {companyInitial(job.company)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="wrap-anywhere font-semibold">{job.title}</p>
            <p className="wrap-anywhere text-sm text-muted-foreground">{job.company}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {[job.location || null, workLabel(job), employment, job.salary || null].filter(Boolean).join(" · ")}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SourceBadge source={job.source} />
              {seenAgo ? <span className="text-xs text-muted-foreground">{seenAgo}</span> : null}
              <MatchBadge
                score={match?.overall_score}
                recommendation={match?.recommendation}
                matchTier={match?.match_tier}
                confidenceLevel={match?.confidence_level}
                scoreKind={match?.score_kind}
                compact
              />
              {match?.eligibility_status === "likely_ineligible" ? (
                <span className="text-xs text-danger-600 dark:text-rose-200">Likely ineligible</span>
              ) : null}
            </div>
          </div>
        </button>
        {onToggleSave && job.id ? (
          <button
            type="button"
            className="btn-ghost h-11 w-11 min-h-11 px-0"
            aria-pressed={Boolean(job.saved)}
            aria-label={job.saved ? "Unsave job" : "Save job"}
            disabled={savePending}
            onClick={onToggleSave}
            data-testid={`save-job-${job.id}`}
          >
            <Bookmark
              className={cn("h-4 w-4 transition-colors", job.saved && "fill-current text-primary bookmark-saved")}
              aria-hidden
            />
          </button>
        ) : null}
      </div>
    </article>
  );
}

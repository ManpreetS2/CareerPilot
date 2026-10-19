import { Bookmark } from "lucide-react";
import { MatchBadge } from "./MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "./SourceBadge";
import { cn } from "../lib/cn";
import { formatJobCardMeta } from "../lib/job-meta";
import { chipLabel } from "../lib/search-intent";
import { isSyntheticShowcasePosting } from "../lib/showcase";
import type { Job, MatchScore } from "../lib/types";

export { formatJobCardMeta } from "../lib/job-meta";

function companyInitial(company: string) {
  return company.trim().charAt(0).toUpperCase() || "?";
}

function workLabel(job: Job): string | null {
  if (!job.work_mode || job.work_mode === "unknown") return null;
  return chipLabel(job.work_mode);
}

export function selectJobCardLabel(title: string, company: string): string {
  return `Select ${title} at ${company}`;
}

function clickIsOnOtherControl(event: { target: EventTarget | null }): boolean {
  const target = event.target;
  if (!(target instanceof Element)) return false;
  if (target.closest("a[href]")) return true;
  const button = target.closest("button");
  return Boolean(button && !button.classList.contains("job-card-select"));
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
        "card w-full p-3 text-left transition-colors duration-[var(--motion-fast)]",
        selected
          ? "job-card-selected border-primary/50 bg-primary/[0.08] shadow-[inset_3px_0_0_0_var(--primary)]"
          : "hover:border-primary/35 hover:bg-foreground/[0.02]",
      )}
      onClick={(event) => {
        if (clickIsOnOtherControl(event)) return;
        onSelect?.();
      }}
    >
      <div className="flex items-start gap-2.5">
        <div className="min-w-0 flex-1">
          <button
            type="button"
            className="job-card-select flex w-full items-start gap-2.5 rounded-md text-left"
            onClick={(event) => {
              event.stopPropagation();
              onSelect?.();
            }}
            aria-pressed={selected}
            aria-label={selectJobCardLabel(job.title, job.company)}
          >
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-sm font-semibold text-primary"
              aria-hidden
            >
              {companyInitial(job.company)}
            </div>
            <div className="min-w-0 flex-1 space-y-0.5">
              <p className="wrap-anywhere text-[15px] font-semibold leading-snug tracking-tight text-foreground">
                {job.title}
              </p>
              <p className="wrap-anywhere text-sm font-medium text-foreground/80">{job.company}</p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {formatJobCardMeta([job.location || null, workLabel(job), employment, job.salary || null])}
              </p>
            </div>
          </button>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-11">
            <SourceBadge source={job.source} url={job.url} sourceUrl={job.source_url} />
            {isSyntheticShowcasePosting(job.id, job.company) ? (
              <span className="status-pill border border-warning/40 bg-warning/10 text-warning">
                Synthetic demo · not a real posting
              </span>
            ) : null}
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
              <span className="text-xs font-medium text-danger">Likely ineligible</span>
            ) : null}
          </div>
        </div>
        {onToggleSave && job.id ? (
          <button
            type="button"
            className="btn-ghost h-10 w-10 min-h-10 shrink-0 px-0 disabled:opacity-50"
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

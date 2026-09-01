import { Link } from "react-router-dom";
import { Bookmark } from "lucide-react";
import { MatchBadge } from "./MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "./SourceBadge";
import { StatusBadge } from "./StatusBadge";
import { Glass } from "./ui/glass";
import { ScoreOrb } from "./signature/ScoreOrb";
import { chipLabel } from "../lib/search-intent";
import { cn } from "../lib/cn";
import type { Job, MatchScore } from "../lib/types";

function eligibilityLabel(status?: string | null): string {
  if (status === "likely_eligible") return "Eligible based on stated requirements";
  if (status === "likely_ineligible") return "Likely ineligible";
  if (status === "eligibility_uncertain") return "Uncertain";
  return "Not evaluated";
}

export function JobPreviewPanel({
  job,
  match,
  onToggleSave,
  savePending = false,
}: {
  job: Job;
  match?: MatchScore | null;
  onToggleSave?: () => void;
  savePending?: boolean;
}) {
  const verified = match?.score_kind === "verified";
  const reasons = (match?.match_reasons ?? []).slice(0, 4);
  const watchout = (match?.watchouts ?? match?.gap_reasons ?? [])[0];
  const work = job.work_mode && job.work_mode !== "unknown" ? chipLabel(job.work_mode) : "Work setup not stated";
  const employment =
    job.employment_type && job.employment_type !== "unknown" ? chipLabel(job.employment_type) : null;

  return (
    <Glass variant="floating" className="sticky top-6 min-w-0 space-y-4 rounded-[var(--radius-lg)] p-6">
      <div className="flex min-w-0 items-start gap-4">
        <ScoreOrb score={verified ? match?.overall_score : null} />
        <div className="min-w-0">
          <p className="wrap-anywhere text-sm text-muted-foreground">{job.company}</p>
          <h2 className="wrap-anywhere font-display text-2xl font-semibold">{job.title}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {[job.location || "Location not stated", work, employment].filter(Boolean).join(" · ")}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={job.status} />
            <SourceBadge source={job.source} />
            {scoutedTimeAgo(job.date_scraped) ? (
              <span className="text-xs text-muted-foreground">{scoutedTimeAgo(job.date_scraped)}</span>
            ) : null}
            <MatchBadge
              score={match?.overall_score}
              recommendation={match?.recommendation}
              matchTier={match?.match_tier}
              applyRecommendation={match?.apply_recommendation}
              confidenceLevel={match?.confidence_level}
              scoreKind={match?.score_kind}
            />
          </div>
        </div>
      </div>

      <section className="rounded-[var(--radius-md)] border border-border/70 bg-surface/80 p-4">
        <p className="cp-kicker">CareerPilot verdict</p>
        {verified && match ? (
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Verified Match</dt>
              <dd className="font-semibold">{Math.round(match.overall_score)}%</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Qualification</dt>
              <dd className="font-semibold">
                {match.qualification_score == null ? "—" : `${Math.round(match.qualification_score)}%`}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Preference</dt>
              <dd className="font-semibold">
                {match.preference_score == null ? "—" : `${Math.round(match.preference_score)}%`}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Eligibility</dt>
              <dd className="font-semibold">{eligibilityLabel(match.eligibility_status)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Confidence</dt>
              <dd className="font-semibold capitalize">{match.confidence_level ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            Potential Match. CareerPilot has not verified all employer requirements yet.
          </p>
        )}
      </section>

      {reasons.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold">Top reasons</h3>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {watchout ? (
        <section>
          <h3 className="text-sm font-semibold">Top watchout</h3>
          <p className="mt-2 text-sm text-muted-foreground">{watchout}</p>
        </section>
      ) : null}

      {job.id ? (
        <div className="flex flex-wrap gap-2">
          <Link to={`/jobs/${job.id}`} className="btn-secondary">
            View Full Analysis
          </Link>
          {onToggleSave ? (
            <button
              type="button"
              className={cn("btn-secondary", job.saved && "text-primary")}
              onClick={onToggleSave}
              disabled={savePending}
            >
              <Bookmark className={cn("h-4 w-4", job.saved && "fill-current")} aria-hidden />
              {job.saved ? "Saved" : "Save"}
            </button>
          ) : null}
          <Link to={`/jobs/${job.id}/prepare`} className="btn-primary">
            {verified ? "Prepare Application" : "Review before preparing"}
          </Link>
        </div>
      ) : null}
    </Glass>
  );
}

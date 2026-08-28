import type { JobRequirementProfile, MatchScore, Requirement, RequirementGroup } from "../lib/types";
import { MatchBadge } from "./MatchBadge";

export function PotentialMatchBadge() {
  return <span className="status-pill bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-200">Potential Match</span>;
}

export function JobFreshnessBadge({ dateScraped }: { dateScraped?: string | null }) {
  if (!dateScraped) return null;
  return <span className="text-xs text-muted-foreground">{dateScraped}</span>;
}

export function RequirementGroupView({ group }: { group: RequirementGroup }) {
  return (
    <div className="rounded-lg border border-border/70 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {group.operator === "any_of" ? "Any of" : "All of"}
      </p>
      <p className="mt-1 text-sm">{group.text}</p>
    </div>
  );
}

export function JobRequirementSection({
  title,
  items,
}: {
  title: string;
  items: Requirement[] | string[];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-200">
        {items.map((item) => (
          <li key={typeof item === "string" ? item : item.id}>{typeof item === "string" ? item : item.text}</li>
        ))}
      </ul>
    </div>
  );
}

export function EligibilityPanel({ match }: { match: MatchScore | null }) {
  if (!match?.eligibility_status) return null;
  const label =
    match.eligibility_status === "likely_eligible"
      ? "Likely eligible"
      : match.eligibility_status === "likely_ineligible"
        ? "Likely ineligible"
        : "Eligibility uncertain";
  return (
    <section className="card space-y-2 p-6">
      <h2 className="font-display text-2xl font-semibold">Eligibility</h2>
      <p className="text-sm font-semibold">{label}</p>
      {(match.gap_reasons ?? []).slice(0, 4).map((reason) => (
        <p key={reason} className="text-sm text-muted-foreground">
          {reason}
        </p>
      ))}
    </section>
  );
}

export function WorkLocationPanel({ profile }: { profile: JobRequirementProfile | null }) {
  if (!profile) return null;
  return (
    <section className="card space-y-3 p-6">
      <h2 className="font-display text-2xl font-semibold">Work & location</h2>
      <p className="text-sm capitalize">{profile.work_mode || "unknown"}</p>
      {profile.remote_scope ? <p className="text-sm">Remote geography: {profile.remote_scope}</p> : null}
      {profile.hybrid_onsite_frequency ? (
        <p className="text-sm">{profile.hybrid_onsite_frequency} onsite days per week</p>
      ) : null}
      {profile.locations.length > 0 ? (
        <p className="text-sm">{profile.locations.map((item) => item.label).join(" · ")}</p>
      ) : null}
      {profile.timezone_requirements ? <p className="text-sm">{profile.timezone_requirements}</p> : null}
      {profile.travel_requirements.map((item) => (
        <p key={item.id} className="text-sm">
          {item.text}
        </p>
      ))}
      {profile.relocation_requirements.map((item) => (
        <p key={item.id} className="text-sm">
          {item.text}
        </p>
      ))}
    </section>
  );
}

export function VerifiedFitPanel({ match }: { match: MatchScore | null }) {
  if (!match) return null;
  return (
    <section className="card space-y-3 p-6">
      <h2 className="font-display text-2xl font-semibold">CareerPilot verdict</h2>
      <MatchBadge
        score={match.overall_score}
        recommendation={match.recommendation}
        matchTier={match.match_tier}
        applyRecommendation={match.apply_recommendation}
        confidenceLevel={match.confidence_level}
        scoreKind={match.score_kind}
      />
      {match.score_kind === "verified" ? (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Qualification Fit</dt>
            <dd className="font-semibold">{match.qualification_score == null ? "—" : `${Math.round(match.qualification_score)}%`}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Preference Fit</dt>
            <dd className="font-semibold">{match.preference_score == null ? "—" : `${Math.round(match.preference_score)}%`}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Eligibility</dt>
            <dd className="font-semibold">{match.eligibility_status?.replaceAll("_", " ") ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Confidence</dt>
            <dd className="font-semibold">{match.confidence_level ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">
          This is a Potential Match until CareerPilot finishes reading the complete posting.
        </p>
      )}
      <p className="text-sm text-muted-foreground">{match.rationale}</p>
    </section>
  );
}

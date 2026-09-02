import type { JobRequirementProfile, MatchScore, Requirement, RequirementGroup } from "../lib/types";
import { MatchBadge } from "./MatchBadge";
import { chipLabel } from "../lib/search-intent";

type RequirementResult = "satisfied" | "partially_satisfied" | "not_satisfied" | "unknown" | "not_applicable";

export function PotentialMatchBadge() {
  return (
    <span className="status-pill bg-muted text-foreground">Potential Match</span>
  );
}

export function formatPostedDate(value?: string | null): string {
  if (!value || !value.trim() || /^0+$/.test(value.trim())) return "Not stated";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "Not stated";
  const date = new Date(parsed);
  if (date.getFullYear() < 1990) return "Not stated";
  return date.toLocaleDateString();
}

export function JobFreshnessBadge({
  dateScraped,
  datePosted,
  verifiedAt,
  status,
}: {
  dateScraped?: string | null;
  datePosted?: string | null;
  verifiedAt?: string | null;
  status?: string | null;
}) {
  return (
    <dl className="grid gap-2 text-sm sm:grid-cols-2">
      <div>
        <dt className="text-muted-foreground">Posted</dt>
        <dd>{formatPostedDate(datePosted)}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Last fetched</dt>
        <dd>{dateScraped ? new Date(dateScraped).toLocaleString() : "Not stated"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Last verified</dt>
        <dd>{verifiedAt ? new Date(verifiedAt).toLocaleString() : "Not yet"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Status</dt>
        <dd className="capitalize">{status || "unknown"}</dd>
      </div>
    </dl>
  );
}

export function RequirementGroupView({
  group,
  requirements,
  statuses,
  groupStatus,
}: {
  group: RequirementGroup;
  requirements: Requirement[];
  statuses?: Record<string, RequirementResult>;
  groupStatus?: RequirementResult;
}) {
  const members = group.requirement_ids
    .map((id) => requirements.find((item) => item.id === id))
    .filter((item): item is Requirement => Boolean(item));
  const satisfyOne = group.operator === "any_of";
  const mark = (id: string) => {
    const status = statuses?.[id];
    if (status === "satisfied") return "✓";
    if (status === "not_satisfied") return "✕";
    if (status === "partially_satisfied") return "~";
    if (status === "unknown") return "?";
    return "○";
  };
  const resultLabel =
    groupStatus === "satisfied"
      ? "Satisfied"
      : groupStatus === "not_satisfied"
        ? "Neither condition satisfied"
        : groupStatus === "partially_satisfied"
          ? "Partially satisfied"
          : groupStatus === "not_applicable"
            ? "Not applicable"
            : "Not enough evidence";
  return (
    <div className="rounded-lg border border-border/70 bg-surface/80 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {satisfyOne ? "You must satisfy one" : "You must satisfy all"}
      </p>
      <ul className="mt-2 space-y-2 text-sm">
        {members.map((item, index) => (
          <li key={item.id}>
            {index > 0 && satisfyOne ? <p className="mb-1 text-xs uppercase text-muted-foreground">or</p> : null}
            <p>
              <span className="mr-2 font-semibold" aria-hidden>
                {mark(item.id)}
              </span>
              {item.text}
            </p>
          </li>
        ))}
        {members.length === 0 ? <li>{group.text}</li> : null}
      </ul>
      <p className="mt-2 text-xs font-semibold text-muted-foreground">Group result: {resultLabel}</p>
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
      <ul className="mt-2 space-y-1 text-sm text-foreground">
        {items.map((item) => (
          <li key={typeof item === "string" ? item : item.id}>
            {typeof item === "string" ? item : item.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EligibilityPanel({ match }: { match: MatchScore | null }) {
  if (!match?.eligibility_status) return null;
  const label =
    match.eligibility_status === "likely_eligible"
      ? "Eligible based on stated requirements"
      : match.eligibility_status === "likely_ineligible"
        ? "Likely ineligible"
        : "Eligibility uncertain";
  return (
    <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
      <h2 className="font-display text-2xl font-semibold">Eligibility</h2>
      <p className="mt-2 text-sm font-semibold">{label}</p>
      {(match.gap_reasons ?? []).slice(0, 4).map((reason) => (
        <p key={reason} className="mt-1 text-sm text-muted-foreground">
          {reason}
        </p>
      ))}
    </section>
  );
}

export function WorkLocationPanel({ profile }: { profile: JobRequirementProfile | null }) {
  if (!profile) return null;
  const mode = profile.work_mode && profile.work_mode !== "unknown" ? chipLabel(profile.work_mode) : "Not stated";
  const remoteScope = profile.remote_scope?.trim();
  const locations = profile.locations.map((item) => item.label).filter(Boolean);
  return (
    <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
      <h2 className="font-display text-2xl font-semibold">Work setup</h2>
      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Work setup</dt>
          <dd className="font-semibold">{mode}</dd>
        </div>
        {remoteScope ? (
          <div>
            <dt className="text-muted-foreground">Remote geography</dt>
            <dd>{remoteScope}</dd>
          </div>
        ) : null}
        {locations.length > 0 ? (
          <div>
            <dt className="text-muted-foreground">Location</dt>
            <dd>{locations.join(" · ")}</dd>
          </div>
        ) : null}
        {profile.hybrid_onsite_frequency ? (
          <div>
            <dt className="text-muted-foreground">On-site rhythm</dt>
            <dd>{profile.hybrid_onsite_frequency} days/week onsite</dd>
          </div>
        ) : null}
        {profile.timezone_requirements ? (
          <div>
            <dt className="text-muted-foreground">Timezone</dt>
            <dd>{profile.timezone_requirements}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-muted-foreground">Relocation</dt>
          <dd>
            {profile.relocation_requirements.length
              ? profile.relocation_requirements.map((item) => item.text).join(" · ")
              : "Not stated"}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Travel</dt>
          <dd>
            {profile.travel_requirements.length
              ? profile.travel_requirements.map((item) => item.text).join(" · ")
              : "Not stated"}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function VerifiedFitPanel({ match }: { match: MatchScore | null }) {
  if (!match) return null;
  return (
    <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
      <h2 className="font-display text-2xl font-semibold">CareerPilot verdict</h2>
      <div className="mt-3">
        <MatchBadge
          score={match.overall_score}
          recommendation={match.recommendation}
          matchTier={match.match_tier}
          applyRecommendation={match.apply_recommendation}
          confidenceLevel={match.confidence_level}
          scoreKind={match.score_kind}
        />
      </div>
      {match.score_kind === "verified" ? (
        <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Qualification Fit</dt>
            <dd className="font-semibold">
              {match.qualification_score == null ? "—" : `${Math.round(match.qualification_score)}%`}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Preference Fit</dt>
            <dd className="font-semibold">
              {match.preference_score == null ? "—" : `${Math.round(match.preference_score)}%`}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Eligibility</dt>
            <dd className="font-semibold">
              {match.eligibility_status === "likely_eligible"
                ? "Eligible based on stated requirements"
                : match.eligibility_status?.replaceAll("_", " ") ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Confidence</dt>
            <dd className="font-semibold capitalize">{match.confidence_level ?? "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          Potential Match. CareerPilot has not verified all employer requirements yet.
        </p>
      )}
    </section>
  );
}

export const VERIFICATION_STAGES = [
  "Reading the full posting",
  "Structuring requirements",
  "Checking eligibility",
  "Calculating verified match",
  "Almost ready",
] as const;

export function VerificationProgress({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <div
      className="rounded-[var(--radius-md)] border border-primary/25 bg-primary/5 p-4"
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="verification-progress"
    >
      <p className="font-semibold">Verifying this posting</p>
      <ol className="mt-3 space-y-1 text-sm text-muted-foreground">
        {VERIFICATION_STAGES.map((label) => (
          <li key={label}>{label}</li>
        ))}
      </ol>
    </div>
  );
}

export function EvidencePanel() {
  return (
    <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
      <h2 className="font-display text-2xl font-semibold">Evidence</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Open the Evidence tab after Calculate Fit to see stored job and candidate evidence.
      </p>
    </section>
  );
}

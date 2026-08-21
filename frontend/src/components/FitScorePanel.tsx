import { Calculator } from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import { MatchBadge } from "./MatchBadge";
import { ApiClientError } from "../lib/api";
import type { MatchScore } from "../lib/types";

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return <p className="mt-2 text-sm text-ink-500">None.</p>;
  }
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-lg bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-700 dark:bg-ink-800 dark:text-ink-100"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function ComponentRow({ label, value }: { label: string; value?: number | null }) {
  if (value == null) {
    return (
      <p className="text-sm text-ink-500">
        {label}: unavailable (omitted from overall, not counted as zero)
      </p>
    );
  }
  return (
    <p className="text-sm">
      {label}: <strong>{Math.round(value)}</strong>
    </p>
  );
}

export function FitScorePanel({
  match,
  loading,
  error,
  onCalculate,
}: {
  match: MatchScore | null;
  loading: boolean;
  error: unknown;
  onCalculate: () => void;
}) {
  const provisional = Boolean(match?.rationale?.toLowerCase().includes("provisional"));
  const missingProfile =
    error instanceof ApiClientError &&
    error.status === 409 &&
    error.message.toLowerCase().includes("candidate profile");

  return (
    <section className="card space-y-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-semibold">Fit score</h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
            Scoring runs only when you ask. It uses the stored candidate profile and grounded job
            requirements.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={onCalculate} disabled={loading}>
          <Calculator className="h-4 w-4" aria-hidden />
          {loading ? "Calculating…" : "Calculate fit"}
        </button>
      </div>

      {missingProfile ? (
        <div
          role="alert"
          className="card mb-4 border-amber-300/70 bg-amber-50/80 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100"
        >
          <p className="font-semibold">Build a candidate profile before calculating fit.</p>
          <Link className="mt-2 inline-flex font-semibold underline" to="/profile">
            Build Profile
          </Link>
        </div>
      ) : (
        <ErrorBanner error={error} />
      )}
      {loading ? <LoadingState label="Calculating fit…" /> : null}

      {!loading && !match ? (
        <p className="text-sm text-ink-500">No fit score yet. Calculate fit to generate one.</p>
      ) : null}

      {match ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm">
              Overall: <strong>{Math.round(match.overall_score)}%</strong> · Recommendation:{" "}
              <strong className="capitalize">{match.recommendation}</strong>
            </p>
            <MatchBadge score={match.overall_score} recommendation={match.recommendation} />
          </div>
          <div className="space-y-1">
            <ComponentRow label="Skills" value={match.skill_score} />
            <ComponentRow label="Experience" value={match.experience_score} />
            <ComponentRow label="Education" value={match.education_score} />
            <ComponentRow label="Location" value={match.location_score} />
            <ComponentRow label="Preferences" value={match.preference_score} />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Matched skills</h3>
            <ChipList items={match.matched_skills} />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Partial matches</h3>
            <ChipList items={match.partial_matches} />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Missing skills</h3>
            <ChipList items={match.missing_skills} />
          </div>
          <div>
            <h3 className="text-sm font-semibold">Rationale</h3>
            <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">{match.rationale}</p>
            {provisional ? (
              <p className="mt-2 text-xs text-ink-500">
                This is a provisional score from explicit posting text. Full Job Intelligence could
                change the result.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

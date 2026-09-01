import { useEffect, useState } from "react";
import { Calculator } from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import { ScoreAssembly } from "./signature/ScoreAssembly";
import { ApiClientError } from "../lib/api";
import type { MatchScore } from "../lib/types";

export function FitScorePanel({
  match,
  loading,
  disabled = false,
  error,
  onCalculate,
}: {
  match: MatchScore | null;
  loading: boolean;
  disabled?: boolean;
  error: unknown;
  onCalculate: () => void;
}) {
  const [assembling, setAssembling] = useState(false);
  const missingProfile =
    error instanceof ApiClientError &&
    error.status === 409 &&
    error.message.toLowerCase().includes("candidate profile");

  useEffect(() => {
    if (loading) setAssembling(true);
  }, [loading]);

  useEffect(() => {
    if (!assembling || loading || !match) return;
    const timer = window.setTimeout(() => setAssembling(false), 860);
    return () => window.clearTimeout(timer);
  }, [assembling, loading, match]);

  return (
    <section
      className="card space-y-4 p-6"
      aria-labelledby="fit-score-heading"
      aria-busy={loading}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="fit-score-heading" className="font-display text-2xl font-semibold">
            Fit score
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
        description="Scoring uses the stored candidate profile and a complete JobRequirementProfile when one exists. Find Jobs ranks with a fast preliminary score. Calculate Fit produces Verified Fit after the full posting is read."
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={onCalculate}
          disabled={loading || disabled}
          aria-busy={loading}
        >
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
      {loading ? (
        <div role="status" aria-live="polite">
          <LoadingState label="Calculating fit…" />
        </div>
      ) : null}

      {!loading && !match ? (
        <p className="text-sm text-muted-foreground">No fit score yet. Calculate fit to generate one.</p>
      ) : null}

      {match && !loading ? <ScoreAssembly match={match} assembling={assembling} /> : null}
    </section>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, PencilLine, X } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import { getSelectedJobId, saveSelectedJobId } from "../lib/session";
import type { ApplicationPackage, ApprovalDecision, Job, MatchScore } from "../lib/types";

export function ApplicationPage() {
  const params = useParams();
  const jobId = params.jobId || getSelectedJobId();

  const [job, setJob] = useState<Job | null>(null);
  const [materials, setMaterials] = useState<ApplicationPackage | null>(null);
  const [match, setMatch] = useState<MatchScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [eligibilityConfirmed, setEligibilityConfirmed] = useState(false);
  const [eligibilityNotes, setEligibilityNotes] = useState("");

  useEffect(() => {
    if (!jobId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [nextJob, nextMaterials] = await Promise.all([
          api.getJob(jobId as string),
          api.generateMaterials(jobId as string),
        ]);
        if (cancelled) return;
        setJob(nextJob);
        setMaterials(nextMaterials);
        setEligibilityConfirmed(nextMaterials.eligibility_confirmed);
        setEligibilityNotes(nextMaterials.eligibility_notes || "");
        saveSelectedJobId(jobId as string);
        try {
          const nextMatch = await api.scoreJob(jobId as string);
          if (!cancelled) setMatch(nextMatch);
        } catch {
          if (!cancelled) setMatch(null);
        }
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function decide(decision: ApprovalDecision) {
    if (!jobId) return;
    setActing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.approveApplication(jobId, decision, {
        eligibilityConfirmed,
        eligibilityNotes: eligibilityNotes || undefined,
      });
      setMessage(result.message);
      setMaterials((prev) =>
        prev
          ? {
              ...prev,
              approval_status: result.approval_status as ApplicationPackage["approval_status"],
              eligibility_confirmed: eligibilityConfirmed,
              eligibility_notes: eligibilityNotes || null,
            }
          : prev,
      );
    } catch (err) {
      setError(err);
    } finally {
      setActing(false);
    }
  }

  if (!jobId) {
    return (
      <EmptyState
        title="No application selected"
        description="Pick a role from Jobs to review tailored materials."
        action={
          <Link to="/jobs" className="btn-primary">
            Browse jobs
          </Link>
        }
      />
    );
  }

  if (loading) return <LoadingState label="Loading application package…" />;
  if (error && !job) return <ErrorBanner error={error} />;
  if (!job || !materials) {
    return (
      <EmptyState
        title="No application selected"
        description="Pick a role from Jobs to review tailored materials."
        action={
          <Link to="/jobs" className="btn-primary">
            Browse jobs
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-4xl font-semibold">Application</h1>
        <p className="mt-2 text-ink-600 dark:text-ink-300">
          Human approval for tailored materials. Material generation is still a placeholder
          until the Application Material Agent lands — approval, editing, and eligibility
          confirmation below are real.
        </p>
      </div>

      <ErrorBanner error={error} />
      {message ? (
        <div className="card border-accent-300/60 bg-accent-50/70 p-4 text-sm text-accent-900 dark:border-accent-800 dark:bg-accent-950/30 dark:text-accent-100">
          {message}
        </div>
      ) : null}

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Job</h2>
        <p className="mt-2 text-lg font-semibold">{job.title}</p>
        <p className="text-sm text-ink-600 dark:text-ink-300">
          {job.company} · {job.location || "Location n/a"}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <StatusBadge status={materials.approval_status} />
          <Link to={`/jobs/${job.id}`} className="btn-ghost px-2 py-1.5">
            View job detail
          </Link>
        </div>
      </section>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Match summary</h2>
        {match ? (
          <div className="mt-3 space-y-2">
            <MatchBadge score={match.overall_score} recommendation={match.recommendation} />
            <p className="text-sm text-ink-600 dark:text-ink-300">{match.rationale}</p>
          </div>
        ) : (
          <p className="mt-3 text-sm text-ink-500">Analysis available after processing</p>
        )}
      </section>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Tailored materials</h2>
        <h3 className="mt-4 text-sm font-semibold uppercase tracking-wide text-ink-500">
          Resume bullets
        </h3>
        <ul className="mt-2 list-disc space-y-2 pl-5 text-sm">
          {materials.tailored_bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[var(--line)] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Cover letter
            </h3>
            <p className="mt-2 whitespace-pre-wrap text-sm text-ink-700 dark:text-ink-200">
              {materials.cover_letter_draft || "None"}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--line)] p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Recruiter message
            </h3>
            <p className="mt-2 whitespace-pre-wrap text-sm text-ink-700 dark:text-ink-200">
              {materials.recruiter_message || "None"}
            </p>
          </div>
        </div>
        {materials.source_traceability_notes.length > 0 ? (
          <div className="mt-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
              Source traceability
            </h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-600 dark:text-ink-300">
              {materials.source_traceability_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Approval</h2>
        <p className="mt-2 text-sm text-ink-600 dark:text-ink-300">
          Current state: <strong className="capitalize">{materials.approval_status.replaceAll("_", " ")}</strong>
        </p>

        <div className="mt-4 rounded-xl border border-[var(--line)] p-4">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={eligibilityConfirmed}
              onChange={(event) => setEligibilityConfirmed(event.target.checked)}
            />
            <span>
              I confirm my work authorization, salary expectations, and eligibility for this role
              are accurate for this application.
            </span>
          </label>
          <textarea
            className="input mt-3 min-h-[72px]"
            placeholder="Optional notes (e.g. sponsorship needed, salary flexibility)…"
            value={eligibilityNotes}
            onChange={(event) => setEligibilityNotes(event.target.value)}
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary"
            disabled={acting || !eligibilityConfirmed}
            title={!eligibilityConfirmed ? "Confirm eligibility above before approving" : undefined}
            onClick={() => void decide("approved")}
          >
            <Check className="h-4 w-4" aria-hidden />
            Approve
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={acting}
            onClick={() => void decide("edit_requested")}
          >
            <PencilLine className="h-4 w-4" aria-hidden />
            Edit
          </button>
          <button
            type="button"
            className="btn-danger"
            disabled={acting}
            onClick={() => void decide("rejected")}
          >
            <X className="h-4 w-4" aria-hidden />
            Reject
          </button>
        </div>
      </section>
    </div>
  );
}

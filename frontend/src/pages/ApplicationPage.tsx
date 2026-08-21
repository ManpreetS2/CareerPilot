import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, ExternalLink, PencilLine, Wand2, X } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import { getSelectedJobId, saveSelectedJobId } from "../lib/session";
import type { ApplicationPackage, ApprovalDecision, FormFillResult, Job, MatchScore } from "../lib/types";

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
  const [decisionNotes, setDecisionNotes] = useState("");
  const [filling, setFilling] = useState(false);
  const [fillResult, setFillResult] = useState<FormFillResult | null>(null);
  const [fillError, setFillError] = useState<unknown>(null);

  useEffect(() => {
    if (!jobId) {
      setLoading(false);
      return;
    }
    const id = jobId;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      // Independent requests run concurrently — a fit score failure (no
      // candidate profile yet, scoring error) shouldn't block showing the
      // job and materials, so it's handled separately from the other two.
      const [jobResult, materialsResult, scoreResult] = await Promise.allSettled([
        api.getJob(id),
        api.generateMaterials(id),
        api.scoreJob(id),
      ]);
      if (cancelled) return;

      if (jobResult.status === "rejected" || materialsResult.status === "rejected") {
        setError(jobResult.status === "rejected" ? jobResult.reason : (materialsResult as PromiseRejectedResult).reason);
        setLoading(false);
        return;
      }

      setJob(jobResult.value);
      setMaterials(materialsResult.value);
      setEligibilityConfirmed(materialsResult.value.eligibility_confirmed);
      setEligibilityNotes(materialsResult.value.eligibility_notes || "");
      setDecisionNotes(materialsResult.value.decision_notes || "");
      setMatch(scoreResult.status === "fulfilled" ? scoreResult.value : null);
      saveSelectedJobId(id);
      setLoading(false);
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
        notes: decisionNotes,
        eligibilityConfirmed,
        eligibilityNotes,
      });
      setMessage(result.message);
      setMaterials((prev) =>
        prev
          ? {
              ...prev,
              approval_status: result.approval_status as ApplicationPackage["approval_status"],
              // Mirrors the backend: only an "approved" decision can move
              // eligibility_confirmed to true; edit/reject never touch it,
              // so a prior confirmation is never silently lost.
              eligibility_confirmed: decision === "approved" ? true : prev.eligibility_confirmed,
              eligibility_notes: eligibilityNotes || null,
              decision_notes: decisionNotes || null,
            }
          : prev,
      );
    } catch (err) {
      setError(err);
    } finally {
      setActing(false);
    }
  }

  async function fillApplication() {
    if (!jobId) return;
    setFilling(true);
    setFillError(null);
    try {
      const result = await api.fillApplication(jobId);
      setFillResult(result);
    } catch (err) {
      setFillError(err);
    } finally {
      setFilling(false);
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

        <label className="mt-4 block text-sm">
          <span className="text-ink-600 dark:text-ink-300">Reviewer notes</span>
          <textarea
            className="input mt-2 min-h-[72px]"
            placeholder="Optional — e.g. what needs to change, or why this was rejected…"
            value={decisionNotes}
            onChange={(event) => setDecisionNotes(event.target.value)}
          />
        </label>

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

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Assisted apply</h2>
        {materials.approval_status !== "approved" ? (
          <p className="mt-2 text-sm text-ink-500">
            Unlocks once this application is approved above. Supports Greenhouse and Lever
            postings.
          </p>
        ) : (
          <>
            <p className="mt-2 text-sm text-ink-600 dark:text-ink-300">
              Fills what it can confidently match on the real application form (Greenhouse or
              Lever) and flags anything it can't — it never submits. Review and submit the
              application yourself.
            </p>
            <ErrorBanner error={fillError} />
            <button
              type="button"
              className="btn-primary mt-4"
              disabled={filling}
              onClick={() => void fillApplication()}
            >
              <Wand2 className={`h-4 w-4 ${filling ? "animate-pulse" : ""}`} aria-hidden />
              {filling ? "Filling…" : "Fill Application Form"}
            </button>

            {fillResult ? (
              <div className="mt-4 space-y-3">
                {fillResult.ats_platform === "unsupported" ? (
                  <p className="text-sm text-ink-500">{fillResult.error_message}</p>
                ) : fillResult.status === "failed" ? (
                  <p className="text-sm text-danger-600 dark:text-rose-300">{fillResult.error_message}</p>
                ) : (
                  <>
                    <p className="text-sm text-ink-600 dark:text-ink-300">
                      Detected <strong className="capitalize">{fillResult.ats_platform}</strong> —{" "}
                      {fillResult.filled_fields.length} field(s) filled,{" "}
                      {fillResult.flagged_fields.length} need your input.
                    </p>
                    {fillResult.filled_fields.length > 0 ? (
                      <div>
                        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
                          Filled automatically
                        </h3>
                        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-600 dark:text-ink-300">
                          {fillResult.filled_fields.map((f) => (
                            <li key={f}>{f.replaceAll("_", " ")}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {fillResult.flagged_fields.length > 0 ? (
                      <div>
                        <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
                          Needs your input
                        </h3>
                        <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-600 dark:text-ink-300">
                          {fillResult.flagged_fields.map((f) => (
                            <li key={f.field}>
                              <span className="font-medium">{f.field.replaceAll("_", " ")}</span> — {f.reason}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <a href={job.url} target="_blank" rel="noreferrer" className="btn-secondary">
                      <ExternalLink className="h-4 w-4" aria-hidden />
                      Open form to finish and submit
                    </a>
                  </>
                )}
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

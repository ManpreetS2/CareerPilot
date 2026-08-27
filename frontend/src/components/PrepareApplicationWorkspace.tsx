import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, PencilLine, Wand2, X } from "lucide-react";
import { AssistedApplyPanel } from "./AssistedApplyPanel";
import { EmptyState } from "./EmptyState";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import { ResumeVersionPanel } from "./ResumeVersionPanel";
import { StatusBadge } from "./StatusBadge";
import { EvidencePathButton } from "./signature/EvidencePath";
import { LockIn } from "./signature/LockIn";
import { ScoreAssembly } from "./signature/ScoreAssembly";
import { StatusSheen } from "./signature/StatusSheen";
import { WorkflowPath } from "./signature/WorkflowPath";
import { api, ApiClientError } from "../lib/api";
import { queryKeys } from "../lib/query-keys";
import { saveSelectedJobId } from "../lib/session";
import type { ApplicationPackage, ApprovalDecision } from "../lib/types";

function materialsStateFromError(err: unknown): "missing" | "stale_pending" | "stale_reviewed" | "error" {
  if (!(err instanceof ApiClientError)) return "error";
  const detailText = `${err.message} ${typeof err.detail === "string" ? err.detail : ""}`.toLowerCase();
  if (err.status === 404) return "missing";
  if (err.status === 409 && detailText.includes("previous candidate")) {
    return detailText.includes("reviewed") || detailText.includes("were not replaced")
      ? "stale_reviewed"
      : "stale_pending";
  }
  return "error";
}

/** Matches only the grounding refusal, not every 409 this endpoint can
 * return (missing profile, missing requirements, a protected package) —
 * offering an "ignore evidence checks" button for an unrelated conflict
 * would be misleading and would not fix it. */
function isGroundingRefusal(err: unknown): boolean {
  return (
    err instanceof ApiClientError &&
    err.status === 409 &&
    err.message.toLowerCase().includes("not supported by stored evidence")
  );
}

export function PrepareApplicationWorkspace({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const [acting, setActing] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [eligibilityConfirmed, setEligibilityConfirmed] = useState(false);
  const [eligibilityNotes, setEligibilityNotes] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [scoreAssembling, setScoreAssembling] = useState(false);
  const [lockedIn, setLockedIn] = useState(false);
  // Set only after a generate attempt is refused for grounding, so the
  // override is offered as a considered response to a specific failure
  // rather than sitting on the page as a shortcut past evidence checks.
  const [groundingRefused, setGroundingRefused] = useState(false);

  const jobQuery = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => api.getJob(jobId, { signal }),
    enabled: Boolean(jobId),
  });
  const scoreQuery = useQuery({
    queryKey: queryKeys.score(jobId),
    queryFn: async ({ signal }) => {
      try {
        return await api.getStoredScore(jobId, { signal });
      } catch (err) {
        if (err instanceof ApiClientError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: Boolean(jobId),
    retry: false,
  });
  const materialsQuery = useQuery({
    queryKey: queryKeys.materials(jobId),
    queryFn: ({ signal }) => api.getStoredMaterials(jobId, { signal }),
    enabled: Boolean(jobId),
    retry: false,
  });

  const job = jobQuery.data ?? null;
  const match = scoreQuery.data ?? null;
  const materials = materialsQuery.isSuccess ? materialsQuery.data : null;
  const materialsState = materialsQuery.isSuccess
    ? "current"
    : materialsQuery.isError
      ? materialsStateFromError(materialsQuery.error)
      : "missing";

  useEffect(() => {
    if (jobId) saveSelectedJobId(jobId);
    setGroundingRefused(false);
  }, [jobId]);

  useEffect(() => {
    if (!materials) return;
    setEligibilityConfirmed(materials.eligibility_confirmed);
    setEligibilityNotes(materials.eligibility_notes || "");
    setDecisionNotes(materials.decision_notes || "");
  }, [materials]);

  async function calculateFit() {
    setScoring(true);
    setActionError(null);
    try {
      const next = await api.scoreJob(jobId);
      queryClient.setQueryData(queryKeys.score(jobId), next);
      setScoreAssembling(true);
      window.setTimeout(() => setScoreAssembling(false), 860);
      await queryClient.invalidateQueries({ queryKey: queryKeys.scores });
    } catch (err) {
      setActionError(err);
    } finally {
      setScoring(false);
    }
  }

  async function generateMaterials(overrideGrounding: boolean) {
    setGenerating(true);
    setActionError(null);
    try {
      const next = await api.generateMaterials(jobId, overrideGrounding);
      queryClient.setQueryData(queryKeys.materials(jobId), next);
      setGroundingRefused(false);
      await queryClient.invalidateQueries({ queryKey: queryKeys.materials(jobId) });
    } catch (err) {
      if (!overrideGrounding && isGroundingRefusal(err)) setGroundingRefused(true);
      setActionError(err);
    } finally {
      setGenerating(false);
    }
  }

  async function discardStale() {
    setGenerating(true);
    setActionError(null);
    try {
      await api.discardStaleMaterials(jobId);
      queryClient.removeQueries({ queryKey: queryKeys.materials(jobId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.materials(jobId) });
    } catch (err) {
      setActionError(err);
    } finally {
      setGenerating(false);
    }
  }

  async function decide(decision: ApprovalDecision) {
    setActing(true);
    setActionError(null);
    setMessage(null);
    try {
      const result = await api.approveApplication(jobId, decision, {
        notes: decisionNotes,
        eligibilityConfirmed,
        eligibilityNotes,
      });
      setMessage(result.message);
      if (decision === "approved") setLockedIn(true);
      queryClient.setQueryData(queryKeys.materials(jobId), (prev: ApplicationPackage | undefined) =>
        prev
          ? {
              ...prev,
              approval_status: result.approval_status as ApplicationPackage["approval_status"],
              eligibility_confirmed: decision === "approved" ? true : prev.eligibility_confirmed,
              eligibility_notes: eligibilityNotes || null,
              decision_notes: decisionNotes || null,
            }
          : prev,
      );
    } catch (err) {
      setActionError(err);
    } finally {
      setActing(false);
    }
  }

  if (jobQuery.isPending) return <LoadingState label="Loading application package…" />;
  if (jobQuery.error && !job) return <ErrorBanner error={jobQuery.error} />;
  if (!job) {
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

  const staleReviewed = materialsState === "stale_reviewed";
  const stalePending = materialsState === "stale_pending";
  const materialsError = materialsState === "error" ? materialsQuery.error : null;
  const approved = materials?.approval_status === "approved";
  const workflow = [
    { id: "generate", label: "Generate", state: materials ? "complete" : "current" },
    {
      id: "review",
      label: "Review",
      state: !materials ? "upcoming" : approved ? "complete" : "current",
    },
    {
      id: "approve",
      label: "Approve",
      state: approved ? "complete" : materials ? "current" : "upcoming",
    },
  ] as const;

  return (
    <div className="space-y-6" data-testid="prepare-application">
      <div>
        <h1 className="title-fluid font-display font-semibold">Prepare application</h1>
        <p className="mt-2 text-muted-foreground">
          Review stored fit and grounded materials. Scoring and generation run only when you ask.
        </p>
        <WorkflowPath className="mt-4" nodes={[...workflow]} />
      </div>

      <ErrorBanner error={actionError ?? materialsError} />
      <LockIn active={lockedIn} message="Materials approved and locked in." />
      {staleReviewed ? (
        <div role="alert" className="card border-warning/40 bg-surface-secondary p-4 text-sm">
          These reviewed materials came from an older candidate profile and were not replaced.
          Discard them, then regenerate explicitly for the current profile.
        </div>
      ) : null}
      {stalePending ? (
        <div role="alert" className="card border-warning/40 bg-surface-secondary p-4 text-sm">
          Pending materials belong to an older candidate profile. Generate again for the current
          profile when you are ready.
        </div>
      ) : null}
      {message && !lockedIn ? (
        <div className="card border-primary/30 bg-primary/5 p-4 text-sm">{message}</div>
      ) : null}

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Job</h2>
        <p className="mt-2 text-lg font-semibold">{job.title}</p>
        <p className="text-sm text-muted-foreground">
          {job.company} · {job.location || "Location n/a"}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {materials ? (
            <StatusSheen status={materials.approval_status}>
              <StatusBadge status={materials.approval_status} />
            </StatusSheen>
          ) : null}
          <Link to={`/jobs/${job.id}`} className="btn-ghost px-2 py-1.5">
            View job detail
          </Link>
        </div>
      </section>

      <section className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="font-display text-2xl font-semibold">Match summary</h2>
          <button
            type="button"
            className="btn-secondary"
            data-testid="calculate-fit"
            disabled={scoring}
            onClick={() => void calculateFit()}
          >
            {scoring ? "Calculating…" : "Calculate fit"}
          </button>
        </div>
        {match ? (
          <div className="mt-3">
            <ScoreAssembly match={match} assembling={scoreAssembling} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">
            Not scored yet. Calculate fit to store a score.
          </p>
        )}
      </section>

      <section className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="font-display text-2xl font-semibold">Tailored materials</h2>
          {materialsState === "current" ? (
            <p className="text-sm text-muted-foreground">Saved materials for the current profile.</p>
          ) : staleReviewed ? (
            <button
              type="button"
              className="btn-secondary"
              data-testid="discard-stale-materials"
              onClick={() => void discardStale()}
            >
              Discard previous reviewed materials
            </button>
          ) : (
            <button
              type="button"
              className="btn-primary"
              data-testid="generate-materials"
              disabled={generating}
              onClick={() => void generateMaterials(false)}
            >
              <Wand2 className={`h-4 w-4 ${generating ? "animate-pulse" : ""}`} aria-hidden />
              {generating
                ? "Generating…"
                : stalePending
                  ? "Generate materials for the current profile"
                  : "Generate materials"}
            </button>
          )}
        </div>
        {groundingRefused && !materials ? (
          <div role="alert" className="mt-3 card border-warning/40 bg-surface-secondary p-4">
            <p className="text-sm font-semibold">The draft claimed things your resume does not show</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Nothing was saved. You can generate anyway for this job — the draft will be kept
              without evidence checks and marked unverified everywhere, including in the browser
              extension before it fills a real application. Read it closely before you submit it.
            </p>
            <button
              type="button"
              className="btn-secondary mt-3"
              data-testid="generate-materials-override"
              disabled={generating}
              onClick={() => void generateMaterials(true)}
            >
              {generating ? "Generating…" : "Generate anyway for this job"}
            </button>
          </div>
        ) : null}
        {materials?.grounding_override ? (
          <div role="alert" className="mt-3 card border-warning/40 bg-surface-secondary p-4">
            <p className="text-sm font-semibold">Unverified materials</p>
            <p className="mt-1 text-sm text-muted-foreground">
              These were kept without evidence checks at your request. Review every claim before
              approving — they may assert experience your resume does not support. Unsupported
              claims require careful human review.
            </p>
            {(materials.unsupported_claims?.length ?? 0) > 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Unsupported:{" "}
                {(materials.unsupported_claims ?? []).map((claim, index) => (
                  <span key={`${claim}-${index}`}>
                    {index > 0 ? ", " : ""}
                    {claim.replace(/_/g, " ")}
                  </span>
                ))}
              </p>
            ) : null}
          </div>
        ) : null}
        {!materials ? (
          <p className="mt-3 text-sm text-muted-foreground">
            No grounded materials stored yet. Generate materials after a fit score exists.
          </p>
        ) : (
          <>
            <h3 className="mt-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Resume bullets
            </h3>
            <ul className="mt-2 space-y-2 text-sm">
              {materials.tailored_bullets.map((bullet, index) => (
                <li key={bullet} className="flex flex-wrap items-start gap-2">
                  <span className="min-w-0 flex-1">{bullet}</span>
                  {materials.source_traceability_notes[index] || materials.source_traceability_notes[0] ? (
                    <EvidencePathButton
                      claim={bullet}
                      evidence={
                        materials.source_traceability_notes[index] ||
                        materials.source_traceability_notes.join(" ")
                      }
                    >
                      Source
                    </EvidencePathButton>
                  ) : null}
                </li>
              ))}
            </ul>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-[var(--radius-md)] border border-border p-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Cover letter
                </h3>
                <p className="mt-2 whitespace-pre-wrap text-sm">{materials.cover_letter_draft || "None"}</p>
              </div>
              <div className="rounded-[var(--radius-md)] border border-border p-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Recruiter message
                </h3>
                <p className="mt-2 whitespace-pre-wrap text-sm">{materials.recruiter_message || "None"}</p>
              </div>
            </div>
            {materials.source_traceability_notes.length > 0 ? (
              <div className="mt-5">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Source traceability
                </h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {materials.source_traceability_notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </section>

      {materials ? <ResumeVersionPanel jobId={jobId} materials={materials} /> : null}

      {materials ? (
        <>
          <section className="sticky-action-rail glass-working p-6">
            <h2 className="font-display text-2xl font-semibold">Approval</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Current state:{" "}
              <strong className="capitalize" data-testid="approval-status">
                {materials.approval_status.replaceAll("_", " ")}
              </strong>
            </p>
            <div className="mt-4 rounded-[var(--radius-md)] border border-border p-4">
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
              <span className="text-muted-foreground">Reviewer notes</span>
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
                className="btn-ghost text-muted-foreground"
                disabled={acting}
                onClick={() => void decide("edit_requested")}
              >
                <PencilLine className="h-4 w-4" aria-hidden />
                Request edit
              </button>
              <button
                type="button"
                className="btn-ghost text-danger"
                disabled={acting}
                onClick={() => void decide("rejected")}
              >
                <X className="h-4 w-4" aria-hidden />
                Reject
              </button>
            </div>
          </section>
          <AssistedApplyPanel job={job} materials={materials} />
        </>
      ) : null}
    </div>
  );
}

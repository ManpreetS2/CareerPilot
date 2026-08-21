import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ExternalLink, ShieldCheck } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { FitScorePanel } from "../components/FitScorePanel";
import { LoadingState } from "../components/LoadingState";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import { saveSelectedJobId } from "../lib/session";
import type { Job, MatchScore } from "../lib/types";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [match, setMatch] = useState<MatchScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [scoreError, setScoreError] = useState<unknown>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const scoringInFlight = useRef(false);
  const scoringRequest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    scoringRequest.current += 1;
    scoringInFlight.current = false;
    async function load() {
      setLoading(true);
      setScoring(false);
      setError(null);
      setVerifyError(null);
      setMatch(null);
      setScoreError(null);
      try {
        const nextJob = await api.getJob(jobId);
        if (!cancelled) setJob(nextJob);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (jobId) void load();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function handleVerify() {
    if (!jobId) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const updated = await api.verifyJob(jobId);
      setJob(updated);
    } catch (err) {
      setVerifyError(err);
    } finally {
      setVerifying(false);
    }
  }

  async function handleCalculateFit() {
    if (!jobId || scoringInFlight.current) return;
    scoringInFlight.current = true;
    const requestId = ++scoringRequest.current;
    const requestJobId = jobId;
    setScoring(true);
    setScoreError(null);
    try {
      const nextMatch = await api.scoreJob(jobId);
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        setMatch(nextMatch);
      }
    } catch (err) {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        setMatch(null);
        setScoreError(err);
      }
    } finally {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        scoringInFlight.current = false;
        setScoring(false);
      }
    }
  }

  if (loading) return <LoadingState label="Loading job…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!job) return <p className="text-sm text-ink-500">Job not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-ink-500">{job.company}</p>
          <h1 className="font-display text-4xl font-semibold">{job.title}</h1>
          <p className="mt-2 text-ink-600 dark:text-ink-300">
            {job.location || "Location n/a"}
            {job.salary ? ` · ${job.salary}` : ""}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={job.status} />
            <span className="text-xs uppercase tracking-wide text-ink-500">{job.source}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={job.url} target="_blank" rel="noreferrer" className="btn-secondary">
            <ExternalLink className="h-4 w-4" aria-hidden />
            Open posting
          </a>
          <Link
            to={`/applications/${job.id}`}
            className="btn-primary"
            onClick={() => {
              if (job.id) saveSelectedJobId(job.id);
            }}
          >
            Review application
          </Link>
        </div>
      </div>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Job overview</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink-700 dark:text-ink-200">
          {job.description}
        </p>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="font-display text-2xl font-semibold">Verification</h2>
            <button
              type="button"
              className="btn-ghost px-2 py-1.5 text-accent-700 dark:text-accent-300"
              onClick={() => void handleVerify()}
              disabled={verifying}
            >
              <ShieldCheck className={`h-4 w-4 ${verifying ? "animate-pulse" : ""}`} aria-hidden />
              {verifying ? "Verifying…" : job.verified_at ? "Re-verify" : "Verify"}
            </button>
          </div>
          <ErrorBanner error={verifyError} />
          <p className="mt-3 text-sm text-ink-600 dark:text-ink-300">
            Current status: <span className="font-semibold capitalize">{job.status}</span>
          </p>
          {job.verification_notes ? (
            <p className="mt-2 text-sm text-ink-500">{job.verification_notes}</p>
          ) : (
            <p className="mt-2 text-sm text-ink-500">
              Not verified yet — run "still open" and suspicious-posting checks with Verify.
            </p>
          )}
          {job.verified_at ? (
            <p className="mt-2 text-xs text-ink-500">
              Last checked {new Date(job.verified_at).toLocaleString()}
            </p>
          ) : null}
        </section>

        <section className="card p-6">
          <h2 className="font-display text-2xl font-semibold">Extracted requirements</h2>
          <p className="mt-3 text-sm text-ink-500">Analysis available after processing</p>
        </section>
      </div>

      <FitScorePanel
        match={match?.job_id === jobId ? match : null}
        loading={scoring}
        error={scoreError}
        onCalculate={() => void handleCalculateFit()}
      />
    </div>
  );
}

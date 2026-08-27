import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { FitScorePanel } from "../components/FitScorePanel";
import { InterviewPrepPanel } from "../components/InterviewPrepPanel";
import { JobIntelligencePanel } from "../components/JobIntelligencePanel";
import {
  EligibilityPanel,
  JobRequirementSection,
  RequirementGroupView,
  VerifiedFitPanel,
  WorkLocationPanel,
} from "../components/job-analysis-panels";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "../components/SourceBadge";
import { StatusBadge } from "../components/StatusBadge";
import { ScoreOrb } from "../components/signature/ScoreOrb";
import { api, ApiClientError } from "../lib/api";
import { topMatchPercentileLabel } from "../lib/match-percentile";
import { saveSelectedJobId } from "../lib/session";
import type { InterviewPrep, Job, JobIntelligence, JobRequirementProfile, MatchScore } from "../lib/types";

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [intelligence, setIntelligence] = useState<JobIntelligence | null>(null);
  const [intelligenceLoading, setIntelligenceLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [intelligenceError, setIntelligenceError] = useState<unknown>(null);
  const [match, setMatch] = useState<MatchScore | null>(null);
  const [interviewPrep, setInterviewPrep] = useState<InterviewPrep | null>(null);
  const [interviewLoading, setInterviewLoading] = useState(true);
  const [interviewGenerating, setInterviewGenerating] = useState(false);
  const [interviewError, setInterviewError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [scoring, setScoring] = useState(false);
  const [scoreError, setScoreError] = useState<unknown>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const scoringInFlight = useRef(false);
  const scoringRequest = useRef(0);
  const extractionInFlight = useRef(false);
  const intelligenceRequest = useRef(0);
  const [neighbors, setNeighbors] = useState<{ prev: string | null; next: string | null }>({
    prev: null,
    next: null,
  });
  const [percentile, setPercentile] = useState<string | null>(null);
  const [profile, setProfile] = useState<JobRequirementProfile | null>(null);
  const storedScoreValues = useRef<Record<string, number>>({});
  const deepAnalyzeJobId = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    scoringRequest.current += 1;
    intelligenceRequest.current += 1;
    scoringInFlight.current = false;
    extractionInFlight.current = false;
    async function load() {
      setLoading(true);
      setScoring(false);
      setExtracting(false);
      setIntelligenceLoading(true);
      setError(null);
      setVerifyError(null);
      setIntelligence(null);
      setIntelligenceError(null);
      setMatch(null);
      setProfile(null);
      setScoreError(null);
      setInterviewPrep(null);
      setInterviewError(null);
      setInterviewLoading(true);
      setPercentile(null);
      setNeighbors({ prev: null, next: null });
      try {
        const nextJob = await api.getJob(jobId);
        if (cancelled) return;
        setJob(nextJob);
        try {
          const stored = await api.getJobIntelligence(jobId);
          if (!cancelled) setIntelligence(stored);
        } catch (err) {
          if (!cancelled) {
            if (err instanceof ApiClientError && err.status === 404) {
              setIntelligence(null);
            } else {
              setIntelligenceError(err);
            }
          }
        } finally {
          if (!cancelled) setIntelligenceLoading(false);
        }
        if (nextJob.id) saveSelectedJobId(nextJob.id);
        try {
          const [jobs, storedScores] = await Promise.all([api.getJobs(), api.getStoredScores()]);
          if (cancelled) return;
          const ranked = [...jobs].sort((a, b) => {
            const rank = (job: typeof a) => {
              const score = job.id ? storedScores.find((item) => item.job_id === job.id) : undefined;
              if (!score) return -1;
              if ((score.scoring_version ?? 1) < 2 && score.ranking_score == null) return -0.5;
              return score.ranking_score ?? score.overall_score ?? -1;
            };
            return rank(b) - rank(a);
          });
          const ids = ranked.map((item) => item.id).filter((id): id is string => Boolean(id));
          const index = ids.indexOf(jobId);
          storedScoreValues.current = Object.fromEntries(
            storedScores
              .filter((score) => score.job_id)
              .map((score) => [score.job_id as string, score.overall_score]),
          );
          setNeighbors({
            prev: index > 0 ? ids[index - 1] ?? null : null,
            next: index >= 0 && index < ids.length - 1 ? ids[index + 1] ?? null : null,
          });
        } catch {
          if (!cancelled) setNeighbors({ prev: null, next: null });
        }
        try {
          const storedProfile = await api.getRequirementProfile(jobId);
          if (!cancelled) setProfile(storedProfile);
        } catch (err) {
          if (!cancelled && !(err instanceof ApiClientError && err.status === 404)) {
            setIntelligenceError(err);
          }
        }
        try {
          const storedScore = await api.getStoredScore(jobId);
          if (!cancelled) {
            setMatch(storedScore);
            setPercentile(
              storedScore.score_kind === "verified"
                ? topMatchPercentileLabel(storedScore.overall_score, Object.values(storedScoreValues.current))
                : null,
            );
          }
        } catch (err) {
          if (!cancelled) {
            if (err instanceof ApiClientError && err.status === 404) {
              setMatch(null);
            } else {
              setScoreError(err);
            }
          }
        }
        try {
          const storedPrep = await api.getInterviewPrep(jobId);
          if (!cancelled) setInterviewPrep(storedPrep);
        } catch (err) {
          if (!cancelled) {
            if (err instanceof ApiClientError && err.status === 404) {
              setInterviewPrep(null);
            } else {
              setInterviewError(err);
            }
          }
        } finally {
          if (!cancelled) setInterviewLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err);
          setIntelligenceLoading(false);
          setInterviewLoading(false);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (jobId) void load();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (!jobId || loading) return;
    if (match?.score_kind === "verified") return;
    if (deepAnalyzeJobId.current === jobId) return;
    deepAnalyzeJobId.current = jobId;
    let cancelled = false;
    void (async () => {
      setScoring(true);
      try {
        const nextProfile = await api.extractRequirementProfile(jobId);
        if (!cancelled) setProfile(nextProfile);
        const nextMatch = await api.scoreJob(jobId);
        if (!cancelled) {
          setMatch(nextMatch);
          if (nextMatch.score_kind === "verified") {
            storedScoreValues.current = {
              ...storedScoreValues.current,
              [jobId]: nextMatch.overall_score,
            };
            setPercentile(
              topMatchPercentileLabel(nextMatch.overall_score, Object.values(storedScoreValues.current)),
            );
          }
        }
      } catch (err) {
        if (!cancelled) setScoreError(err);
      } finally {
        if (!cancelled) setScoring(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId, loading, match?.score_kind]);

  async function handleExtractRequirements() {
    if (!jobId || extractionInFlight.current || scoringInFlight.current) return;
    extractionInFlight.current = true;
    const requestId = ++intelligenceRequest.current;
    const requestJobId = jobId;
    setExtracting(true);
    setIntelligenceError(null);
    try {
      const extracted = await api.extractJobIntelligence(jobId);
      if (requestId === intelligenceRequest.current && requestJobId === jobId) {
        setIntelligence(extracted);
        setMatch(null);
        setScoreError(null);
      }
    } catch (err) {
      if (requestId === intelligenceRequest.current && requestJobId === jobId) {
        setIntelligenceError(err);
      }
    } finally {
      if (requestId === intelligenceRequest.current && requestJobId === jobId) {
        extractionInFlight.current = false;
        setExtracting(false);
      }
    }
  }

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
    if (!jobId || scoringInFlight.current || extractionInFlight.current) return;
    scoringInFlight.current = true;
    const requestId = ++scoringRequest.current;
    const requestJobId = jobId;
    setScoring(true);
    setScoreError(null);
    async function refreshIntelligence() {
      try {
        const stored = await api.getJobIntelligence(requestJobId);
        if (requestId === scoringRequest.current && requestJobId === jobId) {
          setIntelligence(stored);
          setIntelligenceError(null);
        }
      } catch (err) {
        if (requestId === scoringRequest.current && requestJobId === jobId) {
          if (err instanceof ApiClientError && err.status === 404) {
            setIntelligence(null);
          } else {
            setIntelligenceError(err);
          }
        }
      }
    }
    try {
      const nextMatch = await api.scoreJob(jobId);
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        setMatch(nextMatch);
        if (nextMatch.score_kind === "verified") {
          storedScoreValues.current = {
            ...storedScoreValues.current,
            [requestJobId]: nextMatch.overall_score,
          };
          setPercentile(
            topMatchPercentileLabel(nextMatch.overall_score, Object.values(storedScoreValues.current)),
          );
        } else {
          setPercentile(null);
        }
        try {
          setProfile(await api.getRequirementProfile(jobId));
        } catch {
          /* stored profile is optional */
        }
        await refreshIntelligence();
      }
    } catch (err) {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        setMatch(null);
        setScoreError(err);
        await refreshIntelligence();
      }
    } finally {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        scoringInFlight.current = false;
        setScoring(false);
      }
    }
  }

  async function handlePrepareInterview() {
    if (!jobId || interviewGenerating) return;
    setInterviewGenerating(true);
    setInterviewError(null);
    try {
      const next = await api.prepareInterview(jobId);
      setInterviewPrep(next);
    } catch (err) {
      setInterviewError(err);
    } finally {
      setInterviewGenerating(false);
    }
  }

  if (loading) return <LoadingState label="Loading job…" />;
  if (error) return <ErrorBanner error={error} />;
  if (!job) return <p className="text-sm text-ink-500">Job not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        {neighbors.prev ? (
          <Link to={`/jobs/${neighbors.prev}`} className="btn-ghost h-9 px-2">
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Previous job
          </Link>
        ) : (
          <span className="text-muted-foreground">Start of your stored list</span>
        )}
        {neighbors.next ? (
          <Link to={`/jobs/${neighbors.next}`} className="btn-ghost h-9 px-2">
            Next job
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
        ) : (
          <span className="text-muted-foreground">End of your stored list</span>
        )}
      </div>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <ScoreOrb score={match?.score_kind === "verified" ? match.overall_score : null} />
          <div className="min-w-0">
            <p className="wrap-anywhere text-sm text-ink-500">{job.company}</p>
            <h1 className="wrap-anywhere font-display text-4xl font-semibold">{job.title}</h1>
            <p className="mt-2 text-ink-600 dark:text-ink-300">
              {job.location || "Location n/a"}
              {job.salary ? ` · ${job.salary}` : ""}
              {profile?.work_mode ? ` · ${profile.work_mode}` : ""}
              {profile?.employment_type && profile.employment_type !== "unknown"
                ? ` · ${profile.employment_type.replaceAll("_", " ")}`
                : ""}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={job.status} />
              <SourceBadge source={job.source} />
              {job.content_status ? (
                <span className="text-xs text-ink-500">Posting: {job.content_status}</span>
              ) : null}
              {scoutedTimeAgo(job.date_scraped) ? (
                <span className="text-xs text-ink-500">{scoutedTimeAgo(job.date_scraped)}</span>
              ) : null}
              <MatchBadge
                score={match?.overall_score}
                recommendation={match?.recommendation}
                matchTier={match?.match_tier}
                applyRecommendation={match?.apply_recommendation}
                confidenceLevel={match?.confidence_level}
                scoreKind={match?.score_kind}
              />
              {percentile ? <span className="text-xs font-medium text-primary">{percentile}</span> : null}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={job.url} target="_blank" rel="noreferrer" className="btn-secondary max-w-full">
            <ExternalLink className="h-4 w-4 shrink-0" aria-hidden />
            <span className="wrap-anywhere">Open posting</span>
          </a>
          <Link
            to={`/jobs/${job.id}/prepare`}
            className="btn-primary"
            onClick={() => {
              if (job.id) saveSelectedJobId(job.id);
            }}
          >
            {match?.score_kind === "verified" ? "Prepare Application" : "View Full Analysis"}
          </Link>
        </div>
      </div>

      <VerifiedFitPanel match={match?.job_id === jobId ? match : null} />

      {profile ? (
        <section className="card space-y-4 p-6">
          <h2 className="font-display text-2xl font-semibold">What they&apos;re looking for</h2>
          <JobRequirementSection
            title="Must have"
            items={profile.requirements.filter((item) => item.importance !== "preferred")}
          />
          <JobRequirementSection
            title="Preferred"
            items={profile.requirements.filter((item) => item.importance === "preferred")}
          />
          {profile.requirement_groups.map((group) => (
            <RequirementGroupView key={group.id} group={group} />
          ))}
        </section>
      ) : null}

      <WorkLocationPanel profile={profile} />
      <EligibilityPanel match={match?.job_id === jobId ? match : null} />

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Full original employer posting</h2>
        <p className="mt-3 wrap-anywhere whitespace-pre-wrap text-sm leading-relaxed text-ink-700 dark:text-ink-200">
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

        <JobIntelligencePanel
          intelligence={intelligence?.job_id === jobId ? intelligence : null}
          loading={intelligenceLoading}
          extracting={extracting}
          disabled={scoring}
          error={intelligenceError}
          onExtract={() => void handleExtractRequirements()}
        />
      </div>

      <FitScorePanel
        match={match?.job_id === jobId ? match : null}
        loading={scoring}
        disabled={extracting}
        error={scoreError}
        onCalculate={() => void handleCalculateFit()}
      />

      <InterviewPrepPanel
        jobId={jobId}
        prep={interviewPrep?.job_id === jobId ? interviewPrep : null}
        loading={interviewLoading}
        generating={interviewGenerating}
        error={interviewError}
        onPrepare={() => void handlePrepareInterview()}
      />
    </div>
  );
}

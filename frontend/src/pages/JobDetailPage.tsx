import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, ExternalLink, ShieldCheck } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { FitScorePanel } from "../components/FitScorePanel";
import { InterviewPrepPanel } from "../components/InterviewPrepPanel";
import { JobIntelligencePanel } from "../components/JobIntelligencePanel";
import { MatchEvidencePanel } from "../components/MatchEvidencePanel";
import {
  EligibilityPanel,
  JobFreshnessBadge,
  JobRequirementSection,
  RequirementGroupView,
  VerificationProgress,
  VerifiedFitPanel,
  WorkLocationPanel,
} from "../components/job-analysis-panels";
import { LoadingState } from "../components/LoadingState";
import { MatchBadge } from "../components/MatchBadge";
import { scoutedTimeAgo, SourceBadge } from "../components/SourceBadge";
import { StatusBadge } from "../components/StatusBadge";
import { ScoreOrb } from "../components/signature/ScoreOrb";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { api, ApiClientError } from "../lib/api";
import { getJobsNavIds, jobsListPath } from "../lib/jobs-workspace";
import { topMatchPercentileLabel } from "../lib/match-percentile";
import { chipLabel } from "../lib/search-intent";
import { saveSelectedJobId } from "../lib/session";
import type { InterviewPrep, Job, JobIntelligence, JobRequirementProfile, MatchEvidence, MatchScore } from "../lib/types";

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
  const [evidence, setEvidence] = useState<MatchEvidence | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<unknown>(null);
  const [analysisTab, setAnalysisTab] = useState("overview");
  const storedScoreValues = useRef<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
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
      setEvidence(null);
      setEvidenceError(null);
      setAnalysisTab("overview");
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
          const storedIds = getJobsNavIds();
          const ids =
            storedIds.length > 0
              ? storedIds
              : (await api.queryJobs({ sort: "best_match", page_size: 50 })).ids;
          if (cancelled) return;
          const index = ids.indexOf(jobId);
          setNeighbors({
            prev: index > 0 ? ids[index - 1] ?? null : null,
            next: index >= 0 && index < ids.length - 1 ? ids[index + 1] ?? null : null,
          });
          const storedScores = await api.getStoredScores();
          if (cancelled) return;
          storedScoreValues.current = Object.fromEntries(
            storedScores
              .filter((score) => score.job_id)
              .map((score) => [score.job_id as string, score.overall_score]),
          );
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
        try {
          setEvidence(await api.getMatchEvidence(jobId));
          setEvidenceError(null);
        } catch (err) {
          if (err instanceof ApiClientError && err.status === 404) {
            setEvidence(null);
          } else {
            setEvidenceError(err);
          }
        }
      }
      await refreshIntelligence();
    } catch (err) {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        setMatch(null);
        setScoreError(err);
      }
      await refreshIntelligence();
    } finally {
      if (requestId === scoringRequest.current && requestJobId === jobId) {
        scoringInFlight.current = false;
        setScoring(false);
      }
    }
  }

  async function loadEvidence() {
    if (!jobId) return;
    setEvidenceLoading(true);
    setEvidenceError(null);
    try {
      const next = await api.getMatchEvidence(jobId);
      setEvidence(next);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 404) {
        setEvidence(null);
      } else {
        setEvidenceError(err);
      }
    } finally {
      setEvidenceLoading(false);
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
  if (!job) return <p className="text-sm text-muted-foreground">Job not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <Link to={jobsListPath()} className="btn-ghost h-9 px-2">
          Back to Jobs
        </Link>
        <div className="flex flex-wrap items-center gap-2">
        {neighbors.prev ? (
          <Link to={`/jobs/${neighbors.prev}`} className="btn-ghost h-9 px-2">
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Previous job
          </Link>
        ) : (
          <button type="button" className="btn-ghost h-9 px-2" disabled>
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Previous job
          </button>
        )}
        {neighbors.next ? (
          <Link to={`/jobs/${neighbors.next}`} className="btn-ghost h-9 px-2">
            Next job
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Link>
        ) : (
          <button type="button" className="btn-ghost h-9 px-2" disabled>
            Next job
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        )}
        </div>
      </div>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <ScoreOrb score={match?.score_kind === "verified" ? match.overall_score : null} />
          <div className="min-w-0">
            <p className="wrap-anywhere text-sm text-muted-foreground">{job.company}</p>
            <h1 className="wrap-anywhere font-display text-4xl font-semibold">{job.title}</h1>
            <p className="mt-2 text-muted-foreground">
              {[
                job.location || "Location n/a",
                job.salary,
                profile?.work_mode ? chipLabel(profile.work_mode) : null,
                profile?.employment_type && profile.employment_type !== "unknown"
                  ? chipLabel(profile.employment_type)
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={job.status} />
              <SourceBadge source={job.source} />
              {job.content_status ? (
                <span className="text-xs text-muted-foreground">Posting: {job.content_status}</span>
              ) : null}
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
            Prepare Application
          </Link>
        </div>
      </div>

      <VerifiedFitPanel match={match?.job_id === jobId ? match : null} />
      <VerificationProgress active={scoring && match?.score_kind !== "verified"} />
      {scoreError ? (
        <div className="space-y-2">
          <ErrorBanner error={scoreError} heading="Could not verify this posting" />
          <button type="button" className="btn-secondary" onClick={() => void handleCalculateFit()}>
            Retry verification
          </button>
        </div>
      ) : null}

      <Tabs
        value={analysisTab}
        onValueChange={(value) => {
          setAnalysisTab(value);
          if (value === "evidence") void loadEvidence();
        }}
      >
        <TabsList aria-label="Job analysis sections">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="match">Match</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-4 space-y-4">
          <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6">
            <h2 className="font-display text-2xl font-semibold">Employer posting</h2>
            <JobFreshnessBadge
              datePosted={job.date_posted}
              dateScraped={job.date_scraped}
              verifiedAt={job.verified_at}
              status={job.status}
            />
            <p className="mt-4 wrap-anywhere whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {job.description}
            </p>
          </section>
          <WorkLocationPanel profile={profile} />
        </TabsContent>
        <TabsContent value="match" className="mt-4 space-y-4">
          {profile ? (
            <section className="rounded-[var(--radius-lg)] border border-border/70 bg-surface/90 p-6 space-y-4">
              <h2 className="font-display text-2xl font-semibold">What they&apos;re looking for</h2>
              <JobRequirementSection
                title="Must have"
                items={profile.requirements.filter((item) => item.importance !== "preferred")}
              />
              <JobRequirementSection
                title="Preferred"
                items={profile.requirements.filter((item) => item.importance === "preferred")}
              />
              {profile.requirement_groups.map((group) => {
                const blockers = match?.gap_reasons ?? [];
                const groupStatus =
                  match?.score_kind !== "verified"
                    ? "unknown"
                    : blockers.some((reason) => reason === group.text || reason.includes(group.text))
                      ? "not_satisfied"
                      : match?.eligibility_status === "likely_eligible"
                        ? "satisfied"
                        : "unknown";
                return (
                  <RequirementGroupView
                    key={group.id}
                    group={group}
                    requirements={profile.requirements}
                    groupStatus={groupStatus}
                  />
                );
              })}
            </section>
          ) : null}
          <EligibilityPanel match={match?.job_id === jobId ? match : null} />
          <FitScorePanel
            match={match?.job_id === jobId ? match : null}
            loading={scoring}
            disabled={extracting}
            error={scoreError}
            onCalculate={() => void handleCalculateFit()}
          />
        </TabsContent>
        <TabsContent value="evidence" className="mt-4">
          <MatchEvidencePanel
            data={evidence}
            loading={evidenceLoading}
            error={evidenceError}
            onRetry={() => void loadEvidence()}
          />
        </TabsContent>
      </Tabs>

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
          <p className="mt-3 text-sm text-muted-foreground">
            Current status: <span className="font-semibold capitalize">{job.status}</span>
          </p>
          {job.verification_notes ? (
            <p className="mt-2 text-sm text-muted-foreground">{job.verification_notes}</p>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              Not verified yet — run "still open" and suspicious-posting checks with Verify.
            </p>
          )}
          {job.verified_at ? (
            <p className="mt-2 text-xs text-muted-foreground">
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

import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Link2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { JobDiscoveryProgress } from "../components/JobDiscoveryProgress";
import { MatchBadge } from "../components/MatchBadge";
import { LoadingState } from "../components/LoadingState";
import { NaturalSearchBar } from "../components/NaturalSearchBar";
import { scoutedTimeAgo, SourceBadge } from "../components/SourceBadge";
import { StatusBadge } from "../components/StatusBadge";
import { ScoreAssembly } from "../components/signature/ScoreAssembly";
import { ScoreOrb } from "../components/signature/ScoreOrb";
import { Glass } from "../components/ui/glass";
import { PageHeader } from "../components/ui/page-header";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import {
  matchesRoleTypeFilter,
  type RoleTypeFilter,
} from "../lib/job-role-type";
import { topMatchPercentileLabel } from "../lib/match-percentile";
import { jobDiscoveryErrorHeading } from "../lib/job-discovery-error";
import { getSelectedJobId, saveSelectedJobId } from "../lib/session";
import type { Job, MatchScore, ScoutJobsResponse } from "../lib/types";

function sortJobs(list: Job[], scores: Record<string, MatchScore>, sort: "match" | "title") {
  return [...list].sort((a, b) => {
    if (sort === "title") return a.title.localeCompare(b.title);
    const rank = (job: Job) => {
      const score = job.id ? scores[job.id] : undefined;
      if (!score) return -1;
      if ((score.scoring_version ?? 1) < 2 && score.ranking_score == null) return -0.5;
      return score.ranking_score ?? score.overall_score ?? -1;
    };
    return rank(b) - rank(a);
  });
}

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [scores, setScores] = useState<Record<string, MatchScore>>({});
  const [loading, setLoading] = useState(true);
  const [scouting, setScouting] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [naturalQuery, setNaturalQuery] = useState("");
  const [minMatch, setMinMatch] = useState("0");
  const [location, setLocation] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<"match" | "title">("match");
  const [recommendation, setRecommendation] = useState<
    "all" | "apply" | "consider" | "skip" | "unscored"
  >("all");
  const [roleType, setRoleType] = useState<RoleTypeFilter>("both");
  const [jobsPane, setJobsPane] = useState<"discover" | "matches" | "saved">("discover");
  const [manualUrl, setManualUrl] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(() => getSelectedJobId());
  const [scoutSummary, setScoutSummary] = useState<{
    jobsFound: number;
    matchedCount: number;
    sourcesSearched: number;
    sourcesUnavailable: number;
    partial: boolean;
  } | null>(null);
  const scoutingRef = useRef(false);

  async function loadStoredScores() {
    const stored = await api.getStoredScores();
    const nextScores: Record<string, MatchScore> = {};
    for (const score of stored) {
      if (score.job_id) nextScores[score.job_id] = score;
    }
    setScores(nextScores);
  }

  async function loadJobs(fromScout = false) {
    if (fromScout) {
      if (scoutingRef.current) return;
      scoutingRef.current = true;
    }
    setError(null);
    if (fromScout) {
      setScouting(true);
      setScoutSummary(null);
    } else {
      setLoading(true);
    }
    try {
      if (fromScout) {
        const result: ScoutJobsResponse = await api.scoutJobs();
        setJobs(result.jobs);
        const jobsFound = result.jobs_found ?? result.jobs.length;
        const matchedCount = result.matched_count ?? 0;
        const sourcesSearched = result.sources_searched ?? 0;
        const sourcesUnavailable = result.sources_unavailable ?? 0;
        setScoutSummary({
          jobsFound,
          matchedCount,
          sourcesSearched,
          sourcesUnavailable,
          partial: sourcesUnavailable > 0 && jobsFound > 0,
        });
      } else {
        setJobs(await api.getJobs());
      }
      await loadStoredScores();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      setScouting(false);
      if (fromScout) scoutingRef.current = false;
    }
  }

  useEffect(() => {
    void loadJobs();
  }, []);

  async function handleIngestUrl() {
    const url = manualUrl.trim();
    if (!url) {
      setError(new Error("Paste a job URL first."));
      return;
    }
    setError(null);
    setIngesting(true);
    try {
      const job = await api.ingestJobUrl(url);
      setJobs((prev) => [job, ...prev.filter((existing) => existing.id !== job.id)]);
      setManualUrl("");
      if (job.id) {
        setSelectedId(job.id);
        saveSelectedJobId(job.id);
      }
    } catch (err) {
      setError(err);
    } finally {
      setIngesting(false);
    }
  }

  async function handleVerify() {
    setError(null);
    setVerifying(true);
    try {
      const result = await api.verifyJobs("discovered");
      setJobs((prev) => {
        const byId = new Map(result.jobs.map((job) => [job.id, job]));
        return prev.map((job) => (job.id && byId.has(job.id) ? byId.get(job.id)! : job));
      });
    } catch (err) {
      setError(err);
    } finally {
      setVerifying(false);
    }
  }

  const locations = useMemo(() => {
    const values = new Set(
      jobs.map((job) => job.location).filter((value): value is string => Boolean(value)),
    );
    return Array.from(values);
  }, [jobs]);

  const filtered = useMemo(() => {
    const min = Number(minMatch) || 0;
    let list = [...jobs];
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (job) =>
          job.title.toLowerCase().includes(q) ||
          job.company.toLowerCase().includes(q) ||
          (job.location || "").toLowerCase().includes(q),
      );
    }
    if (location !== "all") {
      list = list.filter((job) => job.location === location);
    }
    if (status !== "all") {
      list = list.filter((job) => job.status === status);
    }
    list = list.filter((job) => matchesRoleTypeFilter(job.title, roleType));
    list = list.filter((job) => {
      const score = job.id ? scores[job.id] : undefined;
      if (recommendation === "unscored") return score == null;
      if (recommendation === "apply" || recommendation === "consider" || recommendation === "skip") {
        return score?.recommendation === recommendation;
      }
      return true;
    });
    list = list.filter((job) => {
      const score = job.id ? scores[job.id]?.overall_score : undefined;
      return score == null ? min === 0 : score >= min;
    });
    return sortJobs(list, scores, sort);
  }, [jobs, scores, query, minMatch, location, status, sort, recommendation, roleType]);

  const paneJobs = useMemo(() => {
    if (jobsPane === "saved") return [];
    if (jobsPane === "matches") {
      return filtered.filter((job) => job.id && scores[job.id]);
    }
    return filtered;
  }, [filtered, jobsPane, scores]);

  const verifiedMatches = useMemo(
    () => paneJobs.filter((job) => job.id && scores[job.id]?.score_kind === "verified"),
    [paneJobs, scores],
  );
  const potentialMatches = useMemo(
    () => paneJobs.filter((job) => !(job.id && scores[job.id]?.score_kind === "verified")),
    [paneJobs, scores],
  );
  const listedJobs = useMemo(
    () => (jobsPane === "matches" ? [...verifiedMatches, ...potentialMatches] : paneJobs),
    [jobsPane, verifiedMatches, potentialMatches, paneJobs],
  );

  useEffect(() => {
    if (listedJobs.length === 0) return;
    const stillVisible = selectedId && listedJobs.some((job) => job.id === selectedId);
    if (!stillVisible) {
      const firstId = listedJobs[0]?.id ?? null;
      setSelectedId(firstId);
      if (firstId) saveSelectedJobId(firstId);
    }
  }, [listedJobs, selectedId]);

  const selected = listedJobs.find((job) => job.id === selectedId) ?? null;
  const selectedMatch = selected?.id ? scores[selected.id] : null;
  const storedScoreValues = Object.values(scores).map((score) => score.overall_score);
  const percentile =
    selectedMatch != null && selectedMatch.score_kind === "verified"
      ? topMatchPercentileLabel(selectedMatch.overall_score, storedScoreValues)
      : null;

  function selectJob(jobId: string) {
    setSelectedId(jobId);
    saveSelectedJobId(jobId);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Jobs"
        description="Discover roles, then open a posting for Verified Fit. Find Jobs keeps a fast discovery rank. Authoritative Fit percentages appear only after CareerPilot reads the complete posting."
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary btn-stable"
              onClick={() => void loadJobs(true)}
              disabled={scouting}
              aria-busy={scouting}
              data-testid="find-jobs-button"
            >
              <RefreshCw className={`h-4 w-4 ${scouting ? "animate-pulse" : ""}`} aria-hidden />
              {scouting ? "Searching…" : "Find Jobs"}
            </button>
            <button type="button" className="btn-secondary" onClick={() => void handleIngestUrl()} disabled={ingesting}>
              <Link2 className={`h-4 w-4 ${ingesting ? "animate-pulse" : ""}`} aria-hidden />
              {ingesting ? "Adding…" : "Add Job URL"}
            </button>
            <button type="button" className="btn-secondary" onClick={() => void handleVerify()} disabled={verifying}>
              <ShieldCheck className={`h-4 w-4 ${verifying ? "animate-pulse" : ""}`} aria-hidden />
              {verifying ? "Verifying…" : "Verify Jobs"}
            </button>
          </div>
        }
      />

      <ErrorBanner error={error} heading={jobDiscoveryErrorHeading(error)} />

      {scouting ? <JobDiscoveryProgress active /> : null}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Jobs workspace">
        {(["discover", "matches", "saved"] as const).map((pane) => (
          <button
            key={pane}
            type="button"
            role="tab"
            aria-selected={jobsPane === pane}
            className={cn("btn-secondary capitalize", jobsPane === pane && "btn-primary")}
            onClick={() => setJobsPane(pane)}
          >
            {pane}
          </button>
        ))}
      </div>
      {jobsPane === "saved" ? (
        <p className="text-sm text-muted-foreground">
          Saving jobs is not available yet. This tab is a workspace placeholder, not a fake bookmark
          list.
        </p>
      ) : null}
      {!scouting && scoutSummary ? (
        <Glass
          variant="atmosphere"
          className="rounded-[var(--radius-lg)] p-4"
          data-testid="job-discovery-summary"
        >
          <p className="font-display text-base font-semibold tracking-tight">
            {scoutSummary.jobsFound} {scoutSummary.jobsFound === 1 ? "opportunity" : "opportunities"} found
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {scoutSummary.matchedCount} matched to your profile
            {scoutSummary.sourcesSearched > 0
              ? ` · ${scoutSummary.sourcesSearched} ${scoutSummary.sourcesSearched === 1 ? "source" : "sources"} searched`
              : ""}
          </p>
          {scoutSummary.partial ? (
            <p className="mt-2 text-sm text-muted-foreground">
              Some sources were unavailable, but we found opportunities from the remaining sources.
            </p>
          ) : null}
        </Glass>
      ) : null}

      <Glass variant="atmosphere" className="grid min-w-0 grid-cols-1 gap-3 rounded-[var(--radius-lg)] p-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="sm:col-span-2 xl:col-span-4">
          <NaturalSearchBar value={naturalQuery} onChange={setNaturalQuery} />
        </div>
        <label className="relative block min-w-0">
          <span className="sr-only">Search jobs</span>
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <input
            className="input pl-10"
            placeholder="Search title, company, or location"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="min-w-0">
          <span className="sr-only">Manual job URL</span>
          <input
            className="input"
            placeholder="https://company.com/jobs/…"
            value={manualUrl}
            onChange={(event) => setManualUrl(event.target.value)}
          />
        </label>
        <label className="min-w-0">
          <span className="sr-only">Minimum match</span>
          <select className="input" value={minMatch} onChange={(event) => setMinMatch(event.target.value)}>
            <option value="0">Min match: any</option>
            <option value="60">Min match: 60%</option>
            <option value="75">Min match: 75%</option>
            <option value="85">Min match: 85%</option>
          </select>
        </label>
        <label className="min-w-0">
          <span className="sr-only">Location</span>
          <select className="input" value={location} onChange={(event) => setLocation(event.target.value)}>
            <option value="all">All locations</option>
            {locations.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="min-w-0">
          <span className="sr-only">Status</span>
          <select className="input" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="discovered">Discovered</option>
            <option value="verified">Verified</option>
            <option value="flagged">Flagged</option>
            <option value="stale">Stale</option>
          </select>
        </label>
        <label className="min-w-0">
          <span className="sr-only">Recommendation</span>
          <select
            className="input"
            data-testid="recommendation-filter"
            value={recommendation}
            onChange={(event) =>
              setRecommendation(event.target.value as "all" | "apply" | "consider" | "skip" | "unscored")
            }
          >
            <option value="all">All recommendations</option>
            <option value="apply">Apply</option>
            <option value="consider">Consider</option>
            <option value="skip">Skip</option>
            <option value="unscored">Unscored</option>
          </select>
        </label>
        <label className="min-w-0">
          <span className="sr-only">Role type</span>
          <select
            className="input"
            data-testid="role-type-filter"
            value={roleType}
            onChange={(event) => setRoleType(event.target.value as RoleTypeFilter)}
          >
            <option value="both">Internships and full-time</option>
            <option value="internships">Internships</option>
            <option value="full_time">Full-time</option>
          </select>
        </label>
        <label className="min-w-0">
          <span className="sr-only">Sort</span>
          <select className="input" value={sort} onChange={(event) => setSort(event.target.value as "match" | "title")}>
            <option value="match">Sort by match</option>
            <option value="title">Sort by title</option>
          </select>
        </label>
      </Glass>

      {loading ? (
        <LoadingState label="Loading jobs…" />
      ) : paneJobs.length === 0 && !scouting ? (
        <EmptyState
          title="No jobs to show"
          description="Try Find Jobs, clear filters, or wait until Job Scout persists live listings."
          action={
            <button
              type="button"
              className="btn-primary"
              onClick={() => void loadJobs(true)}
              disabled={scouting}
            >
              Find Jobs
            </button>
          }
        />
      ) : paneJobs.length === 0 && scouting ? null : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul className="space-y-2" aria-label="Job results">
            {jobsPane === "matches" ? (
              <li className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Verified Matches ({verifiedMatches.length}) · Potential Matches ({potentialMatches.length})
              </li>
            ) : null}
            {listedJobs.map((job) => {
              const match = job.id ? scores[job.id] : null;
              const active = job.id === selectedId;
              return (
                <li key={job.id || `${job.company}-${job.title}`}>
                  <article
                    className={cn(
                      "card w-full p-3 text-left transition",
                      active ? "border-primary/50 bg-primary/[0.06]" : "hover:border-accent-400/50",
                    )}
                  >
                    <button
                      type="button"
                      className="w-full text-left"
                      onClick={() => {
                        if (job.id) selectJob(job.id);
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="wrap-anywhere font-semibold">{job.title}</p>
                          <p className="wrap-anywhere text-sm text-muted-foreground">{job.company}</p>
                        </div>
                        <MatchBadge
                          score={match?.overall_score}
                          recommendation={match?.recommendation}
                          matchTier={match?.match_tier}
                          confidenceLevel={match?.confidence_level}
                          scoreKind={match?.score_kind}
                          compact
                        />
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <StatusBadge status={job.status} />
                        <SourceBadge source={job.source} />
                        {job.location ? (
                          <span className="text-xs text-muted-foreground">{job.location}</span>
                        ) : null}
                      </div>
                      {match?.eligibility_status === "likely_ineligible" ? (
                        <p className="mt-2 text-xs text-danger-600 dark:text-rose-200">Likely ineligible</p>
                      ) : null}
                    </button>
                    {job.id ? (
                      <Link
                        to={`/jobs/${job.id}`}
                        className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary"
                        onClick={() => selectJob(job.id!)}
                      >
                        View Analysis
                        <ArrowUpRight className="h-4 w-4" aria-hidden />
                      </Link>
                    ) : null}
                  </article>
                </li>
              );
            })}
          </ul>
          <aside className="hidden lg:block">
            {selected ? (
              <Glass variant="working" refract className="sticky top-6 min-w-0 space-y-4 rounded-[var(--radius-lg)] p-6">
                <div className="flex min-w-0 items-start gap-4">
                  <ScoreOrb score={selectedMatch?.score_kind === "verified" ? selectedMatch.overall_score : null} />
                  <div className="min-w-0">
                    <p className="wrap-anywhere text-sm text-muted-foreground">{selected.company}</p>
                    <h2 className="wrap-anywhere font-display text-2xl font-semibold">{selected.title}</h2>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {selected.location || "Location n/a"}
                      {selected.salary ? ` · ${selected.salary}` : ""}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <StatusBadge status={selected.status} />
                      <SourceBadge source={selected.source} />
                      {scoutedTimeAgo(selected.date_scraped) ? (
                        <span className="text-xs text-muted-foreground">{scoutedTimeAgo(selected.date_scraped)}</span>
                      ) : null}
                      <MatchBadge
                        score={selectedMatch?.overall_score}
                        recommendation={selectedMatch?.recommendation}
                        matchTier={selectedMatch?.match_tier}
                        applyRecommendation={selectedMatch?.apply_recommendation}
                        confidenceLevel={selectedMatch?.confidence_level}
                        scoreKind={selectedMatch?.score_kind}
                      />
                    </div>
                    {percentile ? <p className="mt-2 text-xs font-medium text-primary">{percentile}</p> : null}
                  </div>
                </div>
                {selectedMatch ? <ScoreAssembly match={selectedMatch} assembling={false} /> : null}
                <p className="line-clamp-8 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {selected.description}
                </p>
                {selected.id ? (
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/jobs/${selected.id}`} className="btn-secondary">
                      View Full Analysis
                    </Link>
                    <Link to={`/jobs/${selected.id}/prepare`} className="btn-primary">
                      Prepare Application
                    </Link>
                  </div>
                ) : null}
              </Glass>
            ) : (
              <p className="text-sm text-muted-foreground">Select a job to preview it here.</p>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

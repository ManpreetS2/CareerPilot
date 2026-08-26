import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Link2, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { MatchBadge } from "../components/MatchBadge";
import { LoadingState } from "../components/LoadingState";
import { scoutedTimeAgo, SourceBadge } from "../components/SourceBadge";
import { StatusBadge } from "../components/StatusBadge";
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
import { getSelectedJobId, saveSelectedJobId } from "../lib/session";
import type { Job, MatchScore } from "../lib/types";

function sortJobs(list: Job[], scores: Record<string, MatchScore>, sort: "match" | "title") {
  return [...list].sort((a, b) => {
    if (sort === "title") return a.title.localeCompare(b.title);
    const as = a.id ? (scores[a.id]?.overall_score ?? -1) : -1;
    const bs = b.id ? (scores[b.id]?.overall_score ?? -1) : -1;
    return bs - as;
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
  const [minMatch, setMinMatch] = useState("0");
  const [location, setLocation] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<"match" | "title">("match");
  const [recommendation, setRecommendation] = useState<
    "all" | "apply" | "consider" | "skip" | "unscored"
  >("all");
  const [roleType, setRoleType] = useState<RoleTypeFilter>("both");
  const [manualUrl, setManualUrl] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(() => getSelectedJobId());

  async function loadJobs(fromScout = false) {
    setError(null);
    if (fromScout) setScouting(true);
    else setLoading(true);
    try {
      const nextJobs = fromScout ? (await api.scoutJobs()).jobs : await api.getJobs();
      setJobs(nextJobs);
      const stored = await api.getStoredScores();
      const nextScores: Record<string, MatchScore> = {};
      for (const score of stored) {
        if (score.job_id) nextScores[score.job_id] = score;
      }
      setScores(nextScores);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      setScouting(false);
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

  useEffect(() => {
    if (filtered.length === 0) return;
    const stillVisible = selectedId && filtered.some((job) => job.id === selectedId);
    if (!stillVisible) {
      const firstId = filtered[0]?.id ?? null;
      setSelectedId(firstId);
      if (firstId) saveSelectedJobId(firstId);
    }
  }, [filtered, selectedId]);

  const selected = filtered.find((job) => job.id === selectedId) ?? null;
  const selectedMatch = selected?.id ? scores[selected.id] : null;
  const storedScoreValues = Object.values(scores).map((score) => score.overall_score);
  const percentile =
    selectedMatch != null ? topMatchPercentileLabel(selectedMatch.overall_score, storedScoreValues) : null;

  function selectJob(jobId: string) {
    setSelectedId(jobId);
    saveSelectedJobId(jobId);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Jobs"
        description="Discover and triage roles from Greenhouse, Lever, Remotive, Adzuna, RemoteOK, and manually added URLs. Scores already stored appear immediately. Selecting a job never scores or extracts on its own."
        actions={
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary btn-stable" onClick={() => void loadJobs(true)} disabled={scouting}>
              <RefreshCw className={`h-4 w-4 ${scouting ? "animate-spin" : ""}`} aria-hidden />
              {scouting ? "Finding…" : "Find Jobs"}
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

      <ErrorBanner error={error} />

      <Glass variant="atmosphere" className="grid min-w-0 grid-cols-1 gap-3 rounded-[var(--radius-lg)] p-4 sm:grid-cols-2 xl:grid-cols-4">
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
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No jobs to show"
          description="Try Find Jobs, clear filters, or wait until Job Scout persists live listings."
          action={
            <button type="button" className="btn-primary" onClick={() => void loadJobs(true)}>
              Find Jobs
            </button>
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ul className="space-y-2" aria-label="Job results">
            {filtered.map((job) => {
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
                        <MatchBadge score={match?.overall_score} recommendation={match?.recommendation} />
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <StatusBadge status={job.status} />
                        <SourceBadge source={job.source} />
                      </div>
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
                  <ScoreOrb score={selectedMatch?.overall_score} />
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
                      />
                    </div>
                    {percentile ? <p className="mt-2 text-xs font-medium text-primary">{percentile}</p> : null}
                  </div>
                </div>
                <p className="line-clamp-8 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {selected.description}
                </p>
                {selected.id ? (
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/jobs/${selected.id}`} className="btn-secondary">
                      Open analysis
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

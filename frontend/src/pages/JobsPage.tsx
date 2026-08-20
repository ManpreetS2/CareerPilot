import { useEffect, useMemo, useState } from "react";
import { Link2, RefreshCw, Search } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { JobCard } from "../components/JobCard";
import { LoadingState } from "../components/LoadingState";
import { api } from "../lib/api";
import type { Job, MatchScore } from "../lib/types";

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [scores, setScores] = useState<Record<string, MatchScore>>({});
  const [loading, setLoading] = useState(true);
  const [scouting, setScouting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [minMatch, setMinMatch] = useState("0");
  const [location, setLocation] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<"match" | "title">("match");
  const [manualUrl, setManualUrl] = useState("");

  async function loadJobs(fromScout = false) {
    setError(null);
    if (fromScout) setScouting(true);
    else setLoading(true);
    try {
      const nextJobs = fromScout ? (await api.scoutJobs()).jobs : await api.getJobs();
      setJobs(nextJobs);
      const nextScores: Record<string, MatchScore> = {};
      await Promise.all(
        nextJobs.map(async (job) => {
          if (!job.id) return;
          try {
            nextScores[job.id] = await api.scoreJob(job.id);
          } catch {
            // Scores are optional until Day 3.
          }
        }),
      );
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
    list = list.filter((job) => {
      const score = job.id ? scores[job.id]?.overall_score : undefined;
      return score == null ? min === 0 : score >= min;
    });
    list.sort((a, b) => {
      if (sort === "title") return a.title.localeCompare(b.title);
      const as = a.id ? (scores[a.id]?.overall_score ?? -1) : -1;
      const bs = b.id ? (scores[b.id]?.overall_score ?? -1) : -1;
      return bs - as;
    });
    return list;
  }, [jobs, scores, query, minMatch, location, status, sort]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-4xl font-semibold">Jobs</h1>
          <p className="mt-2 max-w-2xl text-ink-600 dark:text-ink-300">
            Discover and triage roles. Job Scout integration points are ready; listings may still be
            mock data until Developer B wires live sources.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary" onClick={() => void loadJobs(true)} disabled={scouting}>
            <RefreshCw className={`h-4 w-4 ${scouting ? "animate-spin" : ""}`} aria-hidden />
            Find Jobs
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              // TODO(Day 2 / Dev B): POST manual job URL ingestion endpoint.
              window.alert(
                manualUrl.trim()
                  ? "Manual job URL ingestion is not implemented yet. Endpoint contract arrives with Job Scout."
                  : "Paste a job URL first, then try again once Job Scout supports manual ingestion.",
              );
            }}
          >
            <Link2 className="h-4 w-4" aria-hidden />
            Add Job URL
          </button>
        </div>
      </div>

      <ErrorBanner error={error} />

      <div className="card grid gap-3 p-4 lg:grid-cols-[1.4fr_1fr_auto_auto_auto]">
        <label className="relative block">
          <span className="sr-only">Search jobs</span>
          <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink-400" />
          <input
            className="input pl-10"
            placeholder="Search title, company, or location"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          <span className="sr-only">Manual job URL</span>
          <input
            className="input"
            placeholder="https://company.com/jobs/…"
            value={manualUrl}
            onChange={(event) => setManualUrl(event.target.value)}
          />
        </label>
        <label>
          <span className="sr-only">Minimum match</span>
          <select className="input" value={minMatch} onChange={(event) => setMinMatch(event.target.value)}>
            <option value="0">Min match: any</option>
            <option value="60">Min match: 60%</option>
            <option value="75">Min match: 75%</option>
            <option value="85">Min match: 85%</option>
          </select>
        </label>
        <label>
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
        <label>
          <span className="sr-only">Status</span>
          <select className="input" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="discovered">Discovered</option>
            <option value="verified">Verified</option>
          </select>
        </label>
        <label className="lg:col-span-5">
          <span className="sr-only">Sort</span>
          <select className="input max-w-xs" value={sort} onChange={(event) => setSort(event.target.value as "match" | "title")}>
            <option value="match">Sort by match</option>
            <option value="title">Sort by title</option>
          </select>
        </label>
      </div>

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
        <div className="grid gap-4">
          {filtered.map((job) => (
            <JobCard
              key={job.id || `${job.company}-${job.title}`}
              job={job}
              match={job.id ? scores[job.id] : null}
            />
          ))}
        </div>
      )}
    </div>
  );
}

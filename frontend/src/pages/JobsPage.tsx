import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, RefreshCw, SlidersHorizontal } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { JobCard } from "../components/JobCard";
import { JobDiscoveryProgress } from "../components/JobDiscoveryProgress";
import { JobPreviewPanel } from "../components/JobPreviewPanel";
import { JobsFilterPanel } from "../components/JobsFilterPanel";
import { LoadingState } from "../components/LoadingState";
import { NaturalSearchBar, type FilterChip } from "../components/NaturalSearchBar";
import { Glass } from "../components/ui/glass";
import { PageHeader } from "../components/ui/page-header";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { jobDiscoveryErrorHeading } from "../lib/job-discovery-error";
import {
  getJobsNavIds,
  keepJobsQueryData,
  readJobsWorkspace,
  saveJobsNavIds,
  saveJobsWorkspaceHref,
  toJobQueryParams,
  writeJobsWorkspace,
  type JobsWorkspaceState,
} from "../lib/jobs-workspace";
import { chipLabel, parseSearchIntent, scoutTermsFromIntent } from "../lib/search-intent";
import { saveSelectedJobId } from "../lib/session";
import type { JobListItem, JobListPage, ScoutJobsResponse } from "../lib/types";

const TABS = [
  { id: "discover", label: "Discover" },
  { id: "matches", label: "Matches" },
  { id: "saved", label: "Saved" },
] as const;

function pageFromQuery(data: JobListPage | undefined, previous?: JobListPage): JobListPage | undefined {
  return data ?? previous;
}

export function JobsPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const state = readJobsWorkspace(params);
  const [draftSearch, setDraftSearch] = useState(state.search);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [manualUrl, setManualUrl] = useState("");
  const [isDesktop, setIsDesktop] = useState(true);
  const [scoutSummary, setScoutSummary] = useState<{
    jobsFound: number;
    matchedCount: number;
    sourcesSearched: number;
    sourcesUnavailable: number;
    partial: boolean;
  } | null>(null);

  useEffect(() => {
    setDraftSearch(state.search);
  }, [state.search]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const sync = () => setIsDesktop(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  function patch(next: Partial<JobsWorkspaceState>) {
    setParams((current) => writeJobsWorkspace(current, next), { replace: true });
  }

  const queryParams = toJobQueryParams(state);
  const jobsQuery = useQuery({
    queryKey: ["jobs-workspace", queryParams],
    queryFn: ({ signal }) => api.queryJobs(queryParams, { signal }),
    placeholderData: (previousData, previousQuery) =>
      keepJobsQueryData(previousData, previousQuery, queryParams),
  });

  useEffect(() => {
    if (jobsQuery.data?.ids) saveJobsNavIds(jobsQuery.data.ids);
  }, [jobsQuery.data?.ids]);

  useEffect(() => {
    saveJobsWorkspaceHref(params.toString());
  }, [params]);

  const items = jobsQuery.data?.items ?? [];
  const selectedItem =
    items.find((item) => item.job.id === state.selected) ?? (isDesktop ? items[0] : undefined);
  const selectedId = selectedItem?.job.id ?? null;

  useEffect(() => {
    if (!isDesktop || !jobsQuery.data) return;
    const ids = jobsQuery.data.ids;
    if (
      state.selected &&
      ids.includes(state.selected) &&
      !items.some((item) => item.job.id === state.selected)
    ) {
      const index = ids.indexOf(state.selected);
      const nextPage = Math.floor(index / jobsQuery.data.page_size) + 1;
      if (nextPage !== jobsQuery.data.page) {
        patch({ page: nextPage });
      }
      return;
    }
    if (selectedId && selectedId !== state.selected) {
      patch({ selected: selectedId });
      saveSelectedJobId(selectedId);
    }
  }, [isDesktop, selectedId, state.selected, jobsQuery.data, items]);

  const scoutMutation = useMutation({
    mutationFn: (payload?: { what?: string; where?: string }) => api.scoutJobs(payload),
    onSuccess: (result: ScoutJobsResponse) => {
      const jobsFound = result.jobs_found ?? result.jobs.length;
      setScoutSummary({
        jobsFound,
        matchedCount: result.matched_count ?? 0,
        sourcesSearched: result.sources_searched ?? 0,
        sourcesUnavailable: result.sources_unavailable ?? 0,
        partial: (result.sources_unavailable ?? 0) > 0 && jobsFound > 0,
      });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs-workspace"] });
    },
  });

  const ingestMutation = useMutation({
    mutationFn: (url: string) => api.ingestJobUrl(url),
    onSuccess: (job) => {
      setManualUrl("");
      if (job.id) {
        patch({ selected: job.id, tab: "discover" });
        saveSelectedJobId(job.id);
      }
      void queryClient.invalidateQueries({ queryKey: ["jobs-workspace"] });
    },
  });

  const saveMutation = useMutation({
    mutationFn: async ({ jobId, saved }: { jobId: string; saved: boolean }) => {
      if (saved) await api.unsaveJob(jobId);
      else await api.saveJob(jobId);
    },
    onMutate: async ({ jobId, saved }) => {
      await queryClient.cancelQueries({ queryKey: ["jobs-workspace"] });
      const snapshots = queryClient.getQueriesData<JobListPage>({ queryKey: ["jobs-workspace"] });
      const previousSelected = state.selected ?? null;
      let nextSelected = previousSelected;
      for (const [key, current] of snapshots) {
        if (!current) continue;
        const params = key[1] as { tab?: string } | undefined;
        const unsavingFromSaved = saved && params?.tab === "saved";
        if (unsavingFromSaved) {
          const index = current.items.findIndex((item) => item.job.id === jobId);
          const removedItem = current.items.find((item) => item.job.id === jobId);
          const items = current.items.filter((item) => item.job.id !== jobId);
          const ids = current.ids.filter((id) => id !== jobId);
          if (previousSelected === jobId) {
            const neighbor = items[index] ?? items[index - 1] ?? null;
            nextSelected = neighbor?.job.id ?? null;
          }
          queryClient.setQueryData<JobListPage>(key, {
            ...current,
            items,
            ids,
            total: removedItem ? Math.max(0, current.total - 1) : current.total,
            verified_count:
              removedItem?.match?.score_kind === "verified"
                ? Math.max(0, current.verified_count - 1)
                : current.verified_count,
            potential_count:
              removedItem && removedItem.match?.score_kind !== "verified"
                ? Math.max(0, current.potential_count - 1)
                : current.potential_count,
          });
        } else {
          queryClient.setQueryData<JobListPage>(key, {
            ...current,
            items: current.items.map((item) =>
              item.job.id === jobId ? { ...item, saved: !saved, job: { ...item.job, saved: !saved } } : item,
            ),
          });
        }
      }
      if (nextSelected !== previousSelected) {
        patch({ selected: nextSelected });
      }
      return { snapshots, selected: previousSelected };
    },
    onError: (_err, _vars, context) => {
      for (const [key, data] of context?.snapshots ?? []) {
        queryClient.setQueryData(key, data);
      }
      if (context && context.selected !== undefined) {
        patch({ selected: context.selected });
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs-workspace"] });
    },
  });

  const chips: FilterChip[] = useMemo(() => {
    const list: FilterChip[] = [];
    if (state.opportunity === "internship" || state.opportunity === "role") {
      list.push({
        id: `opportunity:${state.opportunity}`,
        label: state.opportunity === "internship" ? "Internships" : "Roles",
        onRemove: () => patch({ opportunity: "both", page: 1 }),
      });
    }
    if (state.q) {
      list.push({
        id: "q",
        label: state.q,
        onRemove: () => patch({ q: undefined, search: "", page: 1 }),
      });
    }
    for (const value of state.employment_type ?? []) {
      if (state.opportunity === "internship" && value === "internship") continue;
      list.push({
        id: `employment:${value}`,
        label: chipLabel(value),
        onRemove: () =>
          patch({ employment_type: (state.employment_type ?? []).filter((item) => item !== value), page: 1 }),
      });
    }
    for (const value of state.work_mode ?? []) {
      list.push({
        id: `work:${value}`,
        label: chipLabel(value),
        onRemove: () => patch({ work_mode: (state.work_mode ?? []).filter((item) => item !== value), page: 1 }),
      });
    }
    for (const value of state.location ?? []) {
      list.push({
        id: `location:${value}`,
        label: value,
        onRemove: () => patch({ location: (state.location ?? []).filter((item) => item !== value), page: 1 }),
      });
    }
    for (const value of state.industry ?? []) {
      list.push({
        id: `industry:${value}`,
        label: chipLabel(value),
        onRemove: () => patch({ industry: (state.industry ?? []).filter((item) => item !== value), page: 1 }),
      });
    }
    for (const value of state.experience_level ?? []) {
      list.push({
        id: `experience:${value}`,
        label: chipLabel(value),
        onRemove: () =>
          patch({ experience_level: (state.experience_level ?? []).filter((item) => item !== value), page: 1 }),
      });
    }
    if (state.verified_state && state.verified_state !== "all") {
      list.push({
        id: "verified",
        label: chipLabel(state.verified_state),
        onRemove: () => patch({ verified_state: "all", page: 1 }),
      });
    }
    if (state.eligibility && state.eligibility !== "all") {
      list.push({
        id: "eligibility",
        label: chipLabel(state.eligibility),
        onRemove: () => patch({ eligibility: "all", page: 1 }),
      });
    }
    if (state.confidence && state.confidence !== "all") {
      list.push({
        id: "confidence",
        label: chipLabel(state.confidence),
        onRemove: () => patch({ confidence: "all", page: 1 }),
      });
    }
    if (state.date_posted) {
      list.push({
        id: "date",
        label: chipLabel(state.date_posted),
        onRemove: () => patch({ date_posted: undefined, page: 1 }),
      });
    }
    return list;
  }, [state]);

  function submitSearch() {
    const intent = parseSearchIntent(draftSearch);
    const terms = scoutTermsFromIntent(intent);
    patch({
      search: draftSearch,
      q: [intent.roles.join(" "), intent.query].filter(Boolean).join(" ").trim() || draftSearch.trim() || undefined,
      opportunity:
        intent.opportunity_types[0] === "internship"
          ? "internship"
          : intent.opportunity_types[0] === "role"
            ? "role"
            : "both",
      employment_type: intent.employment_types,
      work_mode: intent.work_modes,
      location: intent.locations,
      industry: intent.industries,
      experience_level: intent.experience_levels,
      page: 1,
    });
    scoutMutation.mutate(terms);
  }

  const error = jobsQuery.error ?? scoutMutation.error ?? ingestMutation.error ?? saveMutation.error;
  const scouting = scoutMutation.isPending;
  const loading = jobsQuery.isPending && !jobsQuery.data;
  const pageData = pageFromQuery(jobsQuery.data);
  const verifiedCount = pageData?.verified_count ?? 0;
  const potentialCount = pageData?.potential_count ?? 0;
  const showMobileDetail = !isDesktop && Boolean(state.selected && selectedItem);

  function emptyCopy() {
    if (state.tab === "saved") {
      return {
        title: "No saved jobs yet",
        description: "Save roles you're interested in and they'll appear here.",
      };
    }
    if (state.tab === "matches" && verifiedCount === 0 && potentialCount > 0) {
      return {
        title: "We haven't verified enough matches yet",
        description: "Potential Matches are listed below as CareerPilot finishes reading full postings.",
      };
    }
    if (state.tab === "matches") {
      return {
        title: "No matches yet",
        description: "Find jobs, then CareerPilot will rank Verified and Potential Matches here.",
      };
    }
    return {
      title: "We couldn't find jobs matching all of those filters.",
      description: "Clear one filter or search broader. Previously stored jobs are still in your catalog.",
    };
  }

  const listed: JobListItem[] = items;
  const navIds = pageData?.ids ?? getJobsNavIds();
  const verifiedItems = listed.filter((item) => item.match?.score_kind === "verified");
  const potentialItems = listed.filter((item) => item.match?.score_kind !== "verified");

  function renderCard(item: JobListItem) {
    const job = item.job;
    const active = job.id === selectedId;
    return (
      <JobCard
        job={job}
        match={item.match}
        selected={active}
        onSelect={() => {
          if (!job.id) return;
          patch({ selected: job.id });
          saveSelectedJobId(job.id);
        }}
        onToggleSave={() => job.id && saveMutation.mutate({ jobId: job.id, saved: Boolean(job.saved) })}
        savePending={saveMutation.isPending && saveMutation.variables?.jobId === job.id}
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Jobs"
        description="Discover what's available, then open Matches for your personal ranking. Verified Fit appears only after CareerPilot reads the complete posting."
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary btn-stable"
              onClick={() => submitSearch()}
              disabled={scouting}
              aria-busy={scouting}
              data-testid="find-jobs-button"
            >
              <RefreshCw className={`h-4 w-4 ${scouting ? "animate-pulse" : ""}`} aria-hidden />
              {scouting ? "Searching…" : "Find Jobs"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                if (manualUrl.trim()) ingestMutation.mutate(manualUrl.trim());
              }}
              disabled={ingestMutation.isPending}
            >
              <Link2 className={`h-4 w-4 ${ingestMutation.isPending ? "animate-pulse" : ""}`} aria-hidden />
              {ingestMutation.isPending ? "Adding…" : "Add Job URL"}
            </button>
          </div>
        }
      />

      <ErrorBanner error={error} heading={jobDiscoveryErrorHeading(error)} />
      {saveMutation.isError ? (
        <ErrorBanner error={saveMutation.error} heading="Couldn't update saved jobs" />
      ) : null}

      {scouting ? <JobDiscoveryProgress active /> : null}
      {!scouting && scoutSummary ? (
        <Glass variant="atmosphere" className="rounded-[var(--radius-lg)] p-4" data-testid="job-discovery-summary">
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

      {!showMobileDetail ? (
        <Glass variant="atmosphere" className="space-y-4 rounded-[var(--radius-lg)] p-4">
          <NaturalSearchBar
            value={draftSearch}
            onChange={setDraftSearch}
            onSubmit={submitSearch}
            chips={chips}
          />
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="input max-w-md"
              placeholder="https://company.com/jobs/…"
              value={manualUrl}
              onChange={(event) => setManualUrl(event.target.value)}
              aria-label="Manual job URL"
            />
            <button type="button" className="btn-secondary" onClick={() => setFiltersOpen(true)}>
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Filters
            </button>
            <label className="min-w-0">
              <span className="sr-only">Sort</span>
              <select
                className="input"
                value={state.sort ?? "best_match"}
                onChange={(event) => patch({ sort: event.target.value as JobsWorkspaceState["sort"], page: 1 })}
                data-testid="jobs-sort"
              >
                <option value="best_match">Best Match</option>
                <option value="newest">Newest</option>
                <option value="qualification">Highest Qualification Fit</option>
                <option value="preference">Highest Preference Fit</option>
              </select>
            </label>
          </div>
        </Glass>
      ) : null}

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Jobs workspace">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={state.tab === tab.id}
            className={cn("btn-secondary", state.tab === tab.id && "btn-primary")}
            onClick={() => patch({ tab: tab.id, page: 1, selected: isDesktop ? state.selected : null })}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingState label="Loading jobs…" />
      ) : showMobileDetail && selectedItem ? (
        <div className="space-y-3">
          <button type="button" className="btn-ghost" onClick={() => patch({ selected: null })}>
            Back to results
          </button>
          <JobPreviewPanel
            job={selectedItem.job}
            match={selectedItem.match}
            onToggleSave={() =>
              selectedItem.job.id &&
              saveMutation.mutate({ jobId: selectedItem.job.id, saved: Boolean(selectedItem.job.saved) })
            }
            savePending={saveMutation.isPending && saveMutation.variables?.jobId === selectedItem.job.id}
          />
        </div>
      ) : listed.length === 0 && !scouting ? (
        <EmptyState
          title={emptyCopy().title}
          description={emptyCopy().description}
          action={
            state.tab === "saved" ? (
              <button type="button" className="btn-secondary" onClick={() => patch({ tab: "discover" })}>
                Browse Discover
              </button>
            ) : chips.length > 0 ? (
              <button
                type="button"
                className="btn-secondary"
                onClick={() =>
                  patch({
                    search: "",
                    q: undefined,
                    opportunity: "both",
                    employment_type: [],
                    work_mode: [],
                    location: [],
                    industry: [],
                    verified_state: "all",
                    eligibility: "all",
                    confidence: "all",
                    date_posted: undefined,
                    page: 1,
                  })
                }
              >
                Clear filters
              </button>
            ) : (
              <button type="button" className="btn-primary" onClick={() => submitSearch()} disabled={scouting}>
                Search broader
              </button>
            )
          }
        />
      ) : listed.length === 0 && scouting ? null : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
          <ul className="max-h-[70vh] space-y-2 overflow-y-auto pr-1" aria-label="Job results">
            {state.tab === "matches" && verifiedCount === 0 && potentialCount > 0 ? (
              <li className="rounded-[var(--radius-md)] border border-border/70 bg-surface/80 p-3 text-sm text-muted-foreground">
                We haven&apos;t verified enough matches yet. Potential Matches are listed below.
              </li>
            ) : null}
            {state.tab === "matches" ? (
              <>
                <li className="px-1 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Verified Matches ({verifiedCount})
                </li>
                {verifiedItems.map((item) => (
                  <li key={item.job.id || `${item.job.company}-${item.job.title}`}>{renderCard(item)}</li>
                ))}
                <li className="px-1 pt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Potential Matches ({potentialCount})
                </li>
                {potentialItems.map((item) => (
                  <li key={item.job.id || `${item.job.company}-${item.job.title}`}>{renderCard(item)}</li>
                ))}
              </>
            ) : (
              listed.map((item) => (
                <li key={item.job.id || `${item.job.company}-${item.job.title}`}>{renderCard(item)}</li>
              ))
            )}
          </ul>
          <aside className="hidden lg:block">
            {selectedItem ? (
              <JobPreviewPanel
                job={selectedItem.job}
                match={selectedItem.match}
                onToggleSave={() =>
                  selectedItem.job.id &&
                  saveMutation.mutate({
                    jobId: selectedItem.job.id,
                    saved: Boolean(selectedItem.job.saved),
                  })
                }
                savePending={saveMutation.isPending && saveMutation.variables?.jobId === selectedItem.job.id}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Select a job to preview it here.</p>
            )}
          </aside>
        </div>
      )}

      {pageData && pageData.total > pageData.page_size ? (
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            className="btn-secondary"
            disabled={pageData.page <= 1}
            onClick={() => patch({ page: Math.max(1, (state.page ?? 1) - 1) })}
          >
            Previous page
          </button>
          <p className="text-muted-foreground">
            Page {pageData.page} · {pageData.total} jobs
          </p>
          <button
            type="button"
            className="btn-secondary"
            disabled={pageData.page * pageData.page_size >= pageData.total}
            onClick={() => patch({ page: (state.page ?? 1) + 1 })}
          >
            Next page
          </button>
        </div>
      ) : null}

      <JobsFilterPanel open={filtersOpen} onOpenChange={setFiltersOpen} state={state} onChange={patch} />
      <p className="sr-only" aria-live="polite">
        {navIds.length} jobs in the current result set.
      </p>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { Bell, Link2, RefreshCw, SlidersHorizontal } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { JobCard } from "../components/JobCard";
import { JobDiscoveryProgress } from "../components/JobDiscoveryProgress";
import { JobPreviewPanel } from "../components/JobPreviewPanel";
import { JobsFilterPanel } from "../components/JobsFilterPanel";
import { LoadingState } from "../components/LoadingState";
import { NaturalSearchBar, type FilterChip } from "../components/NaturalSearchBar";
import { SavedSearchesPanel, type SavedSearchDraft } from "../components/SavedSearchesPanel";
import { DashboardAtmosphere } from "../components/DashboardAtmosphere";
import { Glass } from "../components/ui/glass";
import { PageHeader } from "../components/ui/page-header";
import { cn } from "../lib/cn";
import { jobDiscoveryErrorHeading } from "../lib/job-discovery-error";
import {
  applySavedJobUnsave,
  getJobsNavIds,
  keepJobsQueryData,
  patchJobSavedFlag,
  readJobsWorkspace,
  rollbackJobInCachedPage,
  saveJobsNavIds,
  saveJobsWorkspaceHref,
  toJobQueryParams,
  writeJobsWorkspace,
  type JobsWorkspaceState,
} from "../lib/jobs-workspace";
import { chipLabel, parseSearchIntent, scoutTermsFromIntent } from "../lib/search-intent";
import { queryKeys } from "../lib/query-keys";
import { api } from "../lib/api";
import { canScoutJobs, missingRequirementLabel, resolveProfileGate } from "../lib/profile-gate";
import { saveSelectedJobId, useCandidateSession } from "../lib/session";
import type { JobListItem, JobListPage, JobQueryParams, ScoutJobsResponse } from "../lib/types";

function isActiveJobsQuery(cached: unknown, active: JobQueryParams): boolean {
  return JSON.stringify(cached) === JSON.stringify(active);
}

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
  const { sessionUserId } = useCandidateSession();
  const [params, setParams] = useSearchParams();
  const state = readJobsWorkspace(params);
  const [draftSearch, setDraftSearch] = useState(state.search);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [savedSearchesOpen, setSavedSearchesOpen] = useState(false);
  const [manualUrl, setManualUrl] = useState("");
  const [isDesktop, setIsDesktop] = useState(true);
  const [scoutSummary, setScoutSummary] = useState<{
    jobsFound: number;
    matchedCount: number;
    sourcesSearched: number;
    sourcesUnavailable: number;
    partial: boolean;
  } | null>(null);
  const pendingSaveIdsRef = useRef(new Set<string>());
  const [pendingSaveIds, setPendingSaveIds] = useState<Set<string>>(() => new Set());

  function markSavePending(jobId: string, pending: boolean) {
    if (pending) pendingSaveIdsRef.current.add(jobId);
    else pendingSaveIdsRef.current.delete(jobId);
    setPendingSaveIds(new Set(pendingSaveIdsRef.current));
  }

  function requestSaveToggle(jobId: string, saved: boolean) {
    if (pendingSaveIdsRef.current.has(jobId)) return;
    markSavePending(jobId, true);
    saveMutation.mutate({ jobId, saved });
  }

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
  const profileQuery = useQuery({
    queryKey: queryKeys.profile(sessionUserId),
    queryFn: ({ signal }) => api.getProfile({ signal }),
    retry: false,
  });
  const profileStatus = profileQuery.isPending ? "pending" : profileQuery.isError ? "error" : "success";
  const profileGate = resolveProfileGate({
    status: profileStatus,
    readiness: profileQuery.data?.readiness,
  });
  const profileIncomplete = profileGate.kind === "incomplete";
  const scoutBlocked = !canScoutJobs(profileGate);
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
      let usedActiveSelection = false;
      let stepBackPage: number | undefined;
      const jobSnapshots: Array<[QueryKey, JobListPage]> = [];
      for (const [key, current] of snapshots) {
        if (!current) continue;
        const params = key[1] as JobQueryParams | undefined;
        const unsavingFromSaved = saved && params?.tab === "saved";
        jobSnapshots.push([key, current]);
        if (unsavingFromSaved) {
          const result = applySavedJobUnsave(current, jobId, previousSelected);
          queryClient.setQueryData(key, result.page);
          const active = isActiveJobsQuery(params, queryParams);
          if (result.nextSelected !== undefined && (active || !usedActiveSelection)) {
            nextSelected = result.nextSelected;
            if (active) usedActiveSelection = true;
          }
          if (active && result.shouldStepBack) {
            stepBackPage = result.nextPage;
          }
        } else {
          queryClient.setQueryData(key, patchJobSavedFlag(current, jobId, !saved));
        }
      }
      if (nextSelected !== previousSelected || stepBackPage != null) {
        patch({
          ...(nextSelected !== previousSelected ? { selected: nextSelected } : {}),
          ...(stepBackPage != null ? { page: stepBackPage } : {}),
        });
      }
      return {
        snapshots: jobSnapshots,
        selected: previousSelected,
        page: state.page,
        didChangeSelected: nextSelected !== previousSelected,
        didStepBack: stepBackPage != null,
      };
    },
    onError: (_err, vars, context) => {
      for (const [key, data] of context?.snapshots ?? []) {
        const current = queryClient.getQueryData<JobListPage>(key);
        if (!current || !data) continue;
        queryClient.setQueryData(key, rollbackJobInCachedPage(data, current, vars.jobId));
      }
      const restore: Partial<JobsWorkspaceState> = {};
      if (context?.didChangeSelected) restore.selected = context.selected;
      if (context?.didStepBack) restore.page = context.page;
      if (Object.keys(restore).length > 0) patch(restore);
    },
    onSettled: (_data, _err, vars) => {
      markSavePending(vars.jobId, false);
      if (pendingSaveIdsRef.current.size === 0) {
        void queryClient.invalidateQueries({ queryKey: ["jobs-workspace"] });
      }
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
    if (scoutBlocked) return;
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

  const currentQueryText = (state.q || draftSearch).trim();
  const savedSearchDraft: SavedSearchDraft | null = currentQueryText
    ? {
        query_text: currentQueryText,
        location: state.location?.[0] ?? null,
        opportunity: state.opportunity && state.opportunity !== "both" ? state.opportunity : null,
        employment_type: state.employment_type ?? [],
        work_mode: state.work_mode ?? [],
        date_posted: state.date_posted ?? null,
      }
    : null;

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
        onToggleSave={() => job.id && requestSaveToggle(job.id, Boolean(job.saved))}
        savePending={Boolean(job.id && pendingSaveIds.has(job.id))}
      />
    );
  }

  return (
    <div className="relative space-y-6">
      <DashboardAtmosphere showGlobe={false} />
      <div className="relative z-[1]">
      <PageHeader
        title="Jobs"
        description="Discover what's available, then open Matches for your personal ranking. Verified Fit appears only after CareerPilot reads the complete posting."
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary btn-stable"
              onClick={() => submitSearch()}
              disabled={scouting || scoutBlocked}
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
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSavedSearchesOpen(true)}
              data-testid="saved-searches-button"
            >
              <Bell className="h-4 w-4" aria-hidden />
              Saved Searches
            </button>
          </div>
        }
      />

      <ErrorBanner error={error} heading={jobDiscoveryErrorHeading(error)} />
      {profileIncomplete ? (
        <Glass variant="atmosphere" className="rounded-[var(--radius-lg)] p-4" data-testid="jobs-profile-gate">
          <p className="font-display text-base font-semibold tracking-tight">
            Complete your profile before CareerPilot searches for matches.
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Still needed:</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {profileGate.readiness.missing.map((item) => (
              <li key={item}>{missingRequirementLabel(item)}</li>
            ))}
          </ul>
          <Link
            to={profileGate.readiness.next_route || "/profile"}
            className="btn-primary mt-3 inline-flex min-h-11"
          >
            Continue profile
          </Link>
        </Glass>
      ) : null}
      {profileGate.kind === "error" ? (
        <Glass variant="atmosphere" className="rounded-[var(--radius-lg)] p-4" data-testid="jobs-profile-error">
          <p className="font-display text-base font-semibold tracking-tight">Couldn't load your profile</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Job search is paused until CareerPilot can read your profile.
          </p>
          <button type="button" className="btn-primary mt-3 inline-flex" onClick={() => void profileQuery.refetch()}>
            Retry profile
          </button>
        </Glass>
      ) : null}
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
            disabled={scoutBlocked}
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

      <div
        className="inline-flex flex-wrap gap-1 rounded-2xl border border-border/80 bg-foreground/[0.03] p-1 backdrop-blur-md"
        role="tablist"
        aria-label="Jobs workspace"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={state.tab === tab.id}
            className={cn(
              "rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors",
              state.tab === tab.id
                ? "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-md shadow-primary/25"
                : "text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground",
            )}
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
              selectedItem.job.id && requestSaveToggle(selectedItem.job.id, Boolean(selectedItem.job.saved))
            }
            savePending={Boolean(selectedItem.job.id && pendingSaveIds.has(selectedItem.job.id))}
          />
        </div>
      ) : listed.length === 0 && !scouting && !profileIncomplete ? (
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
              <button type="button" className="btn-primary" onClick={() => submitSearch()} disabled={scouting || profileGate.kind === "pending" || profileGate.kind === "error"}>
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
                  requestSaveToggle(selectedItem.job.id, Boolean(selectedItem.job.saved))
                }
                savePending={Boolean(selectedItem.job.id && pendingSaveIds.has(selectedItem.job.id))}
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
      <SavedSearchesPanel
        open={savedSearchesOpen}
        onOpenChange={setSavedSearchesOpen}
        currentSearch={savedSearchDraft}
      />
      <p className="sr-only" aria-live="polite">
        {navIds.length} jobs in the current result set.
      </p>
      </div>
    </div>
  );
}

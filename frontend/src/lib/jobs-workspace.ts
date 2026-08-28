import { getActiveSessionUserId } from "./session";
import type { JobListPage, JobQueryParams, JobsSort, JobsTab, OpportunityFilter } from "./types";

export type JobsWorkspaceState = JobQueryParams & {
  search: string;
  selected?: string | null;
};

/**
 * Discover-only: the search the user just asked sources for (`search`, `q`,
 * locations, industries). Matches/Saved answer "what should I consider?" and
 * must not inherit that query. Shared: work mode, opportunity, employment,
 * experience, verification, eligibility, confidence, date posted, sort.
 */
export function scopeJobsWorkspaceForTab(state: JobsWorkspaceState): JobsWorkspaceState {
  if (state.tab === "discover") return state;
  return {
    ...state,
    search: "",
    q: undefined,
    location: [],
    industry: [],
  };
}

function allParams(search: URLSearchParams): URLSearchParams {
  return new URLSearchParams(search);
}

export function readJobsWorkspace(search: URLSearchParams): JobsWorkspaceState {
  const tab = search.get("tab");
  const sort = search.get("sort");
  const opportunity = search.get("opportunity");
  return scopeJobsWorkspaceForTab({
    search: search.get("search") ?? "",
    q: search.get("q") ?? undefined,
    tab: tab === "matches" || tab === "saved" || tab === "discover" ? tab : "discover",
    opportunity:
      opportunity === "internship" || opportunity === "role" || opportunity === "both"
        ? opportunity
        : "both",
    employment_type: search.getAll("employment_type"),
    experience_level: search.getAll("experience_level"),
    work_mode: search.getAll("work_mode"),
    location: search.getAll("location"),
    industry: search.getAll("industry"),
    verified_state: search.get("verified_state") ?? "all",
    eligibility: search.get("eligibility") ?? "all",
    confidence: search.get("confidence") ?? "all",
    date_posted: search.get("date_posted") ?? undefined,
    sort:
      sort === "newest" || sort === "qualification" || sort === "preference" || sort === "best_match"
        ? sort
        : "best_match",
    page: Number(search.get("page") || "1") || 1,
    selected: search.get("selected"),
  });
}

export function writeJobsWorkspace(
  current: URLSearchParams,
  patch: Partial<JobsWorkspaceState>,
): URLSearchParams {
  const next = allParams(current);
  const merged = scopeJobsWorkspaceForTab({ ...readJobsWorkspace(current), ...patch });
  const setList = (key: string, values?: string[]) => {
    next.delete(key);
    for (const value of values ?? []) {
      if (value) next.append(key, value);
    }
  };
  if (merged.tab === "discover" && merged.search) next.set("search", merged.search);
  else next.delete("search");
  if (merged.tab === "discover" && merged.q) next.set("q", merged.q);
  else next.delete("q");
  if (merged.tab && merged.tab !== "discover") next.set("tab", merged.tab);
  else next.delete("tab");
  if (merged.opportunity && merged.opportunity !== "both") next.set("opportunity", merged.opportunity);
  else next.delete("opportunity");
  setList("employment_type", merged.employment_type);
  setList("experience_level", merged.experience_level);
  setList("work_mode", merged.work_mode);
  setList("location", merged.tab === "discover" ? merged.location : []);
  setList("industry", merged.tab === "discover" ? merged.industry : []);
  if (merged.verified_state && merged.verified_state !== "all") next.set("verified_state", merged.verified_state);
  else next.delete("verified_state");
  if (merged.eligibility && merged.eligibility !== "all") next.set("eligibility", merged.eligibility);
  else next.delete("eligibility");
  if (merged.confidence && merged.confidence !== "all") next.set("confidence", merged.confidence);
  else next.delete("confidence");
  if (merged.date_posted) next.set("date_posted", merged.date_posted);
  else next.delete("date_posted");
  if (merged.sort && merged.sort !== "best_match") next.set("sort", merged.sort);
  else next.delete("sort");
  if (merged.page && merged.page > 1) next.set("page", String(merged.page));
  else next.delete("page");
  if (merged.selected) next.set("selected", merged.selected);
  else next.delete("selected");
  return next;
}

export function toJobQueryParams(state: JobsWorkspaceState): JobQueryParams {
  const scoped = scopeJobsWorkspaceForTab(state);
  return {
    q: scoped.q,
    tab: scoped.tab as JobsTab,
    opportunity: scoped.opportunity as OpportunityFilter,
    employment_type: scoped.employment_type,
    experience_level: scoped.experience_level,
    work_mode: scoped.work_mode,
    location: scoped.location,
    industry: scoped.industry,
    verified_state: scoped.verified_state,
    eligibility: scoped.eligibility,
    confidence: scoped.confidence,
    date_posted: scoped.date_posted,
    sort: scoped.sort as JobsSort,
    page: scoped.page,
    page_size: 40,
  };
}

/** Keep prior page data for sort/pagination, never for a different Jobs tab. */
export function keepJobsQueryData(
  previousData: JobListPage | undefined,
  previousQuery: { queryKey: readonly unknown[] } | undefined,
  nextParams: JobQueryParams,
): JobListPage | undefined {
  const prev = previousQuery?.queryKey[1] as JobQueryParams | undefined;
  if (!previousData || !prev || prev.tab !== nextParams.tab) return undefined;
  if (prev.page !== nextParams.page && previousData.items.length === 0) return undefined;
  return previousData;
}

export type SavedUnsavePatch = {
  page: JobListPage;
  nextSelected?: string | null;
  shouldStepBack: boolean;
  nextPage: number;
};

export function applySavedJobUnsave(
  page: JobListPage,
  jobId: string,
  selectedJobId: string | null,
): SavedUnsavePatch {
  const index = page.items.findIndex((item) => item.job.id === jobId);
  const removedItem = index >= 0 ? page.items[index] : undefined;
  if (!removedItem) {
    return { page, shouldStepBack: false, nextPage: page.page };
  }
  const items = page.items.filter((item) => item.job.id !== jobId);
  const ids = page.ids.filter((id) => id !== jobId);
  const total = Math.max(0, page.total - 1);
  const nextPageData: JobListPage = {
    ...page,
    items,
    ids,
    total,
    verified_count:
      removedItem.match?.score_kind === "verified"
        ? Math.max(0, page.verified_count - 1)
        : page.verified_count,
    potential_count:
      removedItem.match?.score_kind !== "verified"
        ? Math.max(0, page.potential_count - 1)
        : page.potential_count,
  };
  let nextSelected: string | null | undefined;
  if (selectedJobId === jobId) {
    const neighbor = items[index] ?? items[index - 1] ?? null;
    nextSelected = neighbor?.job.id ?? null;
  }
  const pageSize = Math.max(1, page.page_size || 1);
  const lastValidPage = Math.max(1, Math.ceil(total / pageSize) || 1);
  const shouldStepBack = items.length === 0 && total > 0 && page.page > 1;
  return {
    page: nextPageData,
    nextSelected,
    shouldStepBack,
    nextPage: shouldStepBack ? lastValidPage : page.page,
  };
}

export function patchJobSavedFlag(page: JobListPage, jobId: string, saved: boolean): JobListPage {
  return {
    ...page,
    items: page.items.map((item) =>
      item.job.id === jobId ? { ...item, saved, job: { ...item.job, saved } } : item,
    ),
  };
}

export function rollbackJobInCachedPage(
  snapshot: JobListPage,
  current: JobListPage,
  jobId: string,
): JobListPage {
  const snapItem = snapshot.items.find((item) => item.job.id === jobId);
  if (!snapItem) return current;
  const currentIndex = current.items.findIndex((item) => item.job.id === jobId);
  if (currentIndex >= 0) {
    return {
      ...current,
      items: current.items.map((item) => (item.job.id === jobId ? snapItem : item)),
    };
  }
  const insertAt = snapshot.items.findIndex((item) => item.job.id === jobId);
  const items = [...current.items];
  items.splice(Math.min(Math.max(insertAt, 0), items.length), 0, snapItem);
  const ids = [...current.ids];
  if (!ids.includes(jobId)) {
    const idAt = snapshot.ids.indexOf(jobId);
    ids.splice(Math.min(Math.max(idAt, 0), ids.length), 0, jobId);
  }
  return {
    ...current,
    items,
    ids,
    total: current.total + 1,
    verified_count:
      snapItem.match?.score_kind === "verified" ? current.verified_count + 1 : current.verified_count,
    potential_count:
      snapItem.match?.score_kind !== "verified" ? current.potential_count + 1 : current.potential_count,
  };
}

const NAV_KEY = "careerpilot.jobsNavIds";
const WORKSPACE_HREF_KEY = "careerpilot.jobsWorkspaceHref";

function scopedSessionKey(base: string): string | null {
  const userId = getActiveSessionUserId();
  if (userId == null) return null;
  return `${base}.u${userId}`;
}

export function saveJobsNavIds(ids: string[]) {
  const key = scopedSessionKey(NAV_KEY);
  if (!key) return;
  try {
    sessionStorage.setItem(key, JSON.stringify(ids));
  } catch {
    /* ignore quota */
  }
}

export function getJobsNavIds(): string[] {
  const key = scopedSessionKey(NAV_KEY);
  if (!key) return [];
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function saveJobsWorkspaceHref(search: string) {
  const key = scopedSessionKey(WORKSPACE_HREF_KEY);
  if (!key) return;
  try {
    sessionStorage.setItem(key, search);
  } catch {
    /* ignore quota */
  }
}

export function getJobsWorkspaceHref(): string {
  const key = scopedSessionKey(WORKSPACE_HREF_KEY);
  if (!key) return "";
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

export function jobsListPath(): string {
  const search = getJobsWorkspaceHref();
  return search ? `/jobs?${search}` : "/jobs";
}

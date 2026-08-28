import type { JobListPage, JobQueryParams, JobsSort, JobsTab, OpportunityFilter } from "./types";

export type JobsWorkspaceState = JobQueryParams & {
  search: string;
  selected?: string | null;
};

function allParams(search: URLSearchParams): URLSearchParams {
  return new URLSearchParams(search);
}

export function readJobsWorkspace(search: URLSearchParams): JobsWorkspaceState {
  const tab = search.get("tab");
  const sort = search.get("sort");
  const opportunity = search.get("opportunity");
  return {
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
  };
}

export function writeJobsWorkspace(
  current: URLSearchParams,
  patch: Partial<JobsWorkspaceState>,
): URLSearchParams {
  const next = allParams(current);
  const merged = { ...readJobsWorkspace(current), ...patch };
  const setList = (key: string, values?: string[]) => {
    next.delete(key);
    for (const value of values ?? []) {
      if (value) next.append(key, value);
    }
  };
  if (merged.search) next.set("search", merged.search);
  else next.delete("search");
  if (merged.q) next.set("q", merged.q);
  else next.delete("q");
  if (merged.tab && merged.tab !== "discover") next.set("tab", merged.tab);
  else next.delete("tab");
  if (merged.opportunity && merged.opportunity !== "both") next.set("opportunity", merged.opportunity);
  else next.delete("opportunity");
  setList("employment_type", merged.employment_type);
  setList("experience_level", merged.experience_level);
  setList("work_mode", merged.work_mode);
  setList("location", merged.location);
  setList("industry", merged.industry);
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
  return {
    q: state.q,
    tab: state.tab as JobsTab,
    opportunity: state.opportunity as OpportunityFilter,
    employment_type: state.employment_type,
    experience_level: state.experience_level,
    work_mode: state.work_mode,
    location: state.location,
    industry: state.industry,
    verified_state: state.verified_state,
    eligibility: state.eligibility,
    confidence: state.confidence,
    date_posted: state.date_posted,
    sort: state.sort as JobsSort,
    page: state.page,
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
  return previousData;
}

const NAV_KEY = "careerpilot.jobsNavIds";

export function saveJobsNavIds(ids: string[]) {
  try {
    sessionStorage.setItem(NAV_KEY, JSON.stringify(ids));
  } catch {
    /* ignore quota */
  }
}

export function getJobsNavIds(): string[] {
  try {
    const raw = sessionStorage.getItem(NAV_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

const WORKSPACE_HREF_KEY = "careerpilot.jobsWorkspaceHref";

export function saveJobsWorkspaceHref(search: string) {
  try {
    sessionStorage.setItem(WORKSPACE_HREF_KEY, search);
  } catch {
    /* ignore quota */
  }
}

export function getJobsWorkspaceHref(): string {
  try {
    return sessionStorage.getItem(WORKSPACE_HREF_KEY) ?? "";
  } catch {
    return "";
  }
}

export function jobsListPath(): string {
  const search = getJobsWorkspaceHref();
  return search ? `/jobs?${search}` : "/jobs";
}

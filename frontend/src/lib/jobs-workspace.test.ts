import { afterEach, describe, expect, it } from "vitest";
import {
  applySavedJobUnsave,
  getJobsNavIds,
  getJobsWorkspaceHref,
  jobsListPath,
  keepJobsQueryData,
  readJobsWorkspace,
  rollbackJobInCachedPage,
  saveJobsNavIds,
  saveJobsWorkspaceHref,
  scopeJobsWorkspaceForTab,
  writeJobsWorkspace,
} from "./jobs-workspace";
import { bindSessionUser } from "./session";
import type { JobListPage } from "./types";

describe("jobs workspace URL state", () => {
  it("round-trips tab, search, work mode, and selected job without profile data", () => {
    const params = writeJobsWorkspace(new URLSearchParams(), {
      search: "software internships",
      q: "Software Engineering",
      tab: "discover",
      opportunity: "internship",
      work_mode: ["hybrid", "onsite"],
      sort: "best_match",
      selected: "job-1",
    });
    expect(params.get("tab")).toBeNull();
    expect(params.get("search")).toBe("software internships");
    expect(params.getAll("work_mode")).toEqual(["hybrid", "onsite"]);
    expect(params.get("selected")).toBe("job-1");
    expect(params.toString()).not.toMatch(/resume|email|phone/i);
    const state = readJobsWorkspace(params);
    expect(state.tab).toBe("discover");
    expect(state.opportunity).toBe("internship");
    expect(state.work_mode).toEqual(["hybrid", "onsite"]);
  });

  it("does not apply Discover search location or industry to Matches or Saved", () => {
    const fromDiscover = writeJobsWorkspace(
      new URLSearchParams(
        "search=software+internships&q=Software+Engineering&location=San+Francisco+Bay+Area&industry=fintech&work_mode=hybrid&opportunity=internship",
      ),
      { tab: "matches", page: 1 },
    );
    expect(fromDiscover.get("tab")).toBe("matches");
    expect(fromDiscover.get("search")).toBeNull();
    expect(fromDiscover.get("q")).toBeNull();
    expect(fromDiscover.get("location")).toBeNull();
    expect(fromDiscover.get("industry")).toBeNull();
    expect(fromDiscover.get("work_mode")).toBe("hybrid");
    expect(fromDiscover.get("opportunity")).toBe("internship");

    const matches = readJobsWorkspace(
      new URLSearchParams(
        "tab=matches&q=Software+Engineering&location=San+Francisco+Bay+Area&industry=fintech&work_mode=hybrid",
      ),
    );
    expect(matches.search).toBe("");
    expect(matches.q).toBeUndefined();
    expect(matches.location).toEqual([]);
    expect(matches.industry).toEqual([]);
    expect(matches.work_mode).toEqual(["hybrid"]);

    const scoped = scopeJobsWorkspaceForTab({
      search: "software internships",
      q: "Software Engineering",
      tab: "saved",
      work_mode: ["remote"],
      location: ["Austin"],
      industry: ["fintech"],
    });
    expect(scoped.search).toBe("");
    expect(scoped.q).toBeUndefined();
    expect(scoped.location).toEqual([]);
    expect(scoped.industry).toEqual([]);
    expect(scoped.work_mode).toEqual(["remote"]);
  });

  it("does not serialize private profile fields", () => {
    const params = writeJobsWorkspace(new URLSearchParams(), { search: "python", tab: "discover" });
    expect([...params.keys()].every((key) => !/resume|email|phone|name/i.test(key))).toBe(true);
  });

  it("keeps prior page data only within the same Jobs tab", () => {
    const savedPage: JobListPage = {
      items: [{ job: { id: "job-1", title: "A", company: "Acme", url: "https://example.com/a", description: "", source: "manual", status: "discovered" }, saved: true }],
      total: 2,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 1,
      ids: ["job-1", "job-2"],
    };
    const previousQuery = { queryKey: ["jobs-workspace", { tab: "saved", page: 1 }] as const };
    expect(
      keepJobsQueryData(savedPage, previousQuery, { tab: "matches", page: 1, page_size: 40 }),
    ).toBeUndefined();
    expect(
      keepJobsQueryData(savedPage, previousQuery, { tab: "saved", page: 2, page_size: 40 }),
    ).toBe(savedPage);
  });

  it("does not reuse an emptied later Saved page as placeholder data for page 1", () => {
    const emptiedPageTwo: JobListPage = {
      items: [],
      total: 2,
      page: 2,
      page_size: 2,
      verified_count: 0,
      potential_count: 0,
      ids: ["job-a", "job-b"],
    };
    const previousQuery = { queryKey: ["jobs-workspace", { tab: "saved", page: 2 }] as const };
    expect(
      keepJobsQueryData(emptiedPageTwo, previousQuery, { tab: "saved", page: 1, page_size: 2 }),
    ).toBeUndefined();
  });
});

describe("saved unsave cache patches", () => {
  const job = (id: string, title: string) => ({
    job: {
      id,
      title,
      company: "Acme",
      url: `https://example.com/${id}`,
      description: "",
      source: "manual" as const,
      status: "discovered" as const,
      saved: true,
    },
    match: null,
    saved: true,
  });

  it("does not derive a neighbor from a Saved cache that never contained the job", () => {
    const withB: JobListPage = {
      items: [job("a", "A"), job("b", "B"), job("c", "C")],
      total: 3,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 3,
      ids: ["a", "b", "c"],
    };
    const withoutB: JobListPage = {
      items: [job("x", "X")],
      total: 1,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 1,
      ids: ["x"],
    };
    expect(applySavedJobUnsave(withoutB, "b", "b").nextSelected).toBeUndefined();
    expect(applySavedJobUnsave(withB, "b", "b").nextSelected).toBe("c");
  });

  it("steps back when the last item on a later Saved page is removed and earlier pages still have jobs", () => {
    const pageTwo: JobListPage = {
      items: [job("c", "C")],
      total: 3,
      page: 2,
      page_size: 2,
      verified_count: 0,
      potential_count: 1,
      ids: ["a", "b", "c"],
    };
    const result = applySavedJobUnsave(pageTwo, "c", "c");
    expect(result.page.items).toEqual([]);
    expect(result.page.total).toBe(2);
    expect(result.shouldStepBack).toBe(true);
    expect(result.nextPage).toBe(1);
    expect(result.nextSelected).toBeNull();
  });

  it("rolls back only the failed job inside a later cache snapshot", () => {
    const before: JobListPage = {
      items: [job("a", "A"), job("b", "B")],
      total: 2,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 2,
      ids: ["a", "b"],
    };
    const afterAFailedButBSaved: JobListPage = {
      items: [
        { ...job("a", "A"), saved: false, job: { ...job("a", "A").job, saved: false } },
        { ...job("b", "B"), saved: true, job: { ...job("b", "B").job, saved: true } },
      ],
      total: 2,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 2,
      ids: ["a", "b"],
    };
    const restored = rollbackJobInCachedPage(before, afterAFailedButBSaved, "a");
    expect(restored.items.find((item) => item.job.id === "a")?.saved).toBe(true);
    expect(restored.items.find((item) => item.job.id === "b")?.saved).toBe(true);
  });
});

describe("jobs workspace session isolation", () => {
  afterEach(() => {
    bindSessionUser(null);
    sessionStorage.clear();
  });

  it("does not leak User A's search or nav ids to User B after logout", () => {
    bindSessionUser(11);
    saveJobsNavIds(["job-alice-1", "job-alice-2"]);
    saveJobsWorkspaceHref("search=A-query&selected=A-job");

    bindSessionUser(null);
    expect(getJobsNavIds()).toEqual([]);
    expect(getJobsWorkspaceHref()).toBe("");
    expect(jobsListPath()).toBe("/jobs");

    bindSessionUser(22);
    expect(getJobsNavIds()).toEqual([]);
    expect(getJobsWorkspaceHref()).toBe("");
    expect(jobsListPath()).toBe("/jobs");

    bindSessionUser(11);
    expect(getJobsNavIds()).toEqual(["job-alice-1", "job-alice-2"]);
    expect(getJobsWorkspaceHref()).toBe("search=A-query&selected=A-job");
    expect(jobsListPath()).toBe("/jobs?search=A-query&selected=A-job");
  });
});

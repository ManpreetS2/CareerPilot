import { describe, expect, it } from "vitest";
import { keepJobsQueryData, readJobsWorkspace, writeJobsWorkspace } from "./jobs-workspace";
import type { JobListPage } from "./types";

describe("jobs workspace URL state", () => {
  it("round-trips tab, search, work mode, and selected job without profile data", () => {
    const params = writeJobsWorkspace(new URLSearchParams(), {
      search: "software internships",
      q: "Software Engineering",
      tab: "matches",
      opportunity: "internship",
      work_mode: ["hybrid", "onsite"],
      sort: "best_match",
      selected: "job-1",
    });
    expect(params.get("tab")).toBe("matches");
    expect(params.get("search")).toBe("software internships");
    expect(params.getAll("work_mode")).toEqual(["hybrid", "onsite"]);
    expect(params.get("selected")).toBe("job-1");
    expect(params.toString()).not.toMatch(/resume|email|phone/i);
    const state = readJobsWorkspace(params);
    expect(state.tab).toBe("matches");
    expect(state.opportunity).toBe("internship");
    expect(state.work_mode).toEqual(["hybrid", "onsite"]);
  });

  it("does not serialize private profile fields", () => {
    const params = writeJobsWorkspace(new URLSearchParams(), { search: "python", tab: "discover" });
    expect([...params.keys()].every((key) => !/resume|email|phone|name/i.test(key))).toBe(true);
  });

  it("keeps prior page data only within the same Jobs tab", () => {
    const savedPage: JobListPage = {
      items: [],
      total: 2,
      page: 1,
      page_size: 40,
      verified_count: 0,
      potential_count: 0,
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
});

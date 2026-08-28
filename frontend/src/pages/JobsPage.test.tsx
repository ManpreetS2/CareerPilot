import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobsPage } from "./JobsPage";
import { api, ApiClientError } from "../lib/api";
import { readJobsWorkspace, toJobQueryParams } from "../lib/jobs-workspace";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";
import { JOB_DISCOVERY_STAGES } from "../components/JobDiscoveryProgress";
import type { Job, JobListPage, ScoutJobsResponse } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getJobs: vi.fn(),
      queryJobs: vi.fn(),
      scoutJobs: vi.fn(),
      getStoredScores: vi.fn(),
      ingestJobUrl: vi.fn(),
      verifyJobs: vi.fn(),
      saveJob: vi.fn(),
      unsaveJob: vi.fn(),
    },
  };
});

const existingJob: Job = {
  id: "jobicy-existing",
  title: "Backend Engineer",
  company: "Northwind",
  url: "https://example.com/jobs/backend-engineer",
  description: "Build APIs.",
  source: "jobicy",
  status: "discovered",
};

const newJob: Job = {
  id: "himalayas-new",
  title: "Platform Engineer",
  company: "Helios",
  url: "https://example.com/jobs/platform-engineer",
  description: "Own platform work.",
  source: "himalayas",
  status: "discovered",
};

function pageOf(jobs: Job[], extra?: Partial<JobListPage>): JobListPage {
  return {
    items: jobs.map((job) => ({ job, match: null, saved: Boolean(job.saved) })),
    total: jobs.length,
    page: 1,
    page_size: 40,
    verified_count: 0,
    potential_count: jobs.length,
    ids: jobs.map((job) => job.id!).filter(Boolean),
    ...extra,
  };
}

function renderJobs(route = "/jobs", queryClient = createTestQueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <JobsPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("JobsPage workspace", () => {
  beforeEach(() => {
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([existingJob]));
    vi.mocked(api.getStoredScores).mockResolvedValue([]);
    vi.mocked(api.scoutJobs).mockReset();
    vi.mocked(api.saveJob).mockReset();
    vi.mocked(api.unsaveJob).mockReset();
  });

  it("shows discovery progress while scoutJobs is unresolved and keeps existing jobs", async () => {
    let resolveScout: (value: ScoutJobsResponse) => void = () => undefined;
    vi.mocked(api.scoutJobs).mockImplementation(
      () =>
        new Promise<ScoutJobsResponse>((resolve) => {
          resolveScout = resolve;
        }),
    );
    renderJobs();
    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("find-jobs-button"));
    expect(await screen.findByTestId("job-discovery-progress")).toBeInTheDocument();
    for (const label of JOB_DISCOVERY_STAGES) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText("Backend Engineer").length).toBeGreaterThan(0);
    expect(screen.getByTestId("find-jobs-button")).toBeDisabled();
    expect(screen.getByTestId("find-jobs-button")).toHaveTextContent("Searching…");
    await userEvent.click(screen.getByTestId("find-jobs-button"));
    expect(api.scoutJobs).toHaveBeenCalledTimes(1);
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([newJob, existingJob]));
    resolveScout({
      jobs: [newJob, existingJob],
      jobs_found: 2,
      matched_count: 2,
      sources_searched: 6,
      sources_unavailable: 1,
    });
    expect(await screen.findByTestId("job-discovery-summary")).toBeInTheDocument();
    expect(screen.getByText("2 opportunities found")).toBeInTheDocument();
    expect(screen.getByText(/2 matched to your profile/)).toBeInTheDocument();
    expect(screen.getByText(/6 sources searched/)).toBeInTheDocument();
    expect(screen.queryByTestId("job-discovery-progress")).not.toBeInTheDocument();
    expect(await screen.findByText("Platform Engineer")).toBeInTheDocument();
  });

  it("sorts using the backend Best Match order", async () => {
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([newJob, existingJob]));
    renderJobs();
    const list = await screen.findByLabelText("Job results");
    await waitFor(() => {
      const titles = [...list.querySelectorAll("p.font-semibold")].map((node) => node.textContent);
      expect(titles[0]).toBe("Platform Engineer");
    });
  });

  it("exits loading after a discovery failure", async () => {
    vi.mocked(api.scoutJobs).mockRejectedValue(new ApiClientError(504, "timed out"));
    renderJobs();
    await screen.findByText("Backend Engineer");
    await userEvent.click(screen.getByTestId("find-jobs-button"));
    expect(await screen.findByText("Job discovery timed out")).toBeInTheDocument();
    expect(screen.queryByTestId("job-discovery-progress")).not.toBeInTheDocument();
    expect(screen.getByTestId("find-jobs-button")).toBeEnabled();
    expect(screen.getAllByText("Backend Engineer").length).toBeGreaterThan(0);
  });

  it("parses natural language into chips and scouts with structured terms", async () => {
    vi.mocked(api.scoutJobs).mockResolvedValue({
      jobs: [existingJob],
      jobs_found: 1,
      matched_count: 1,
      sources_searched: 3,
      sources_unavailable: 0,
    });
    renderJobs();
    await screen.findByText("Backend Engineer");
    const input = screen.getByTestId("jobs-search-input");
    await userEvent.clear(input);
    await userEvent.type(
      input,
      "Software engineering internships in the Bay Area at fintech companies, hybrid or onsite",
    );
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(api.scoutJobs).toHaveBeenCalled());
    const payload = vi.mocked(api.scoutJobs).mock.calls[0]?.[0];
    expect(payload?.what?.toLowerCase()).toContain("software");
    expect(payload?.where).toMatch(/Bay Area/i);
    expect(await screen.findByLabelText("Remove Internships")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove Hybrid")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove On-site")).toBeInTheDocument();
    expect(screen.getByLabelText("Remove Fintech")).toBeInTheDocument();
    await waitFor(() => {
      const lastQuery = vi.mocked(api.queryJobs).mock.calls.at(-1)?.[0];
      expect(lastQuery?.opportunity).toBe("internship");
      expect(lastQuery?.work_mode).toEqual(expect.arrayContaining(["hybrid", "onsite"]));
    });
  });

  it("switches Discover / Matches / Saved without a top-level Applications tab", async () => {
    renderJobs();
    await screen.findByText("Backend Engineer");
    expect(screen.getByRole("tab", { name: "Discover" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Matches" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Saved" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /applications/i })).not.toBeInTheDocument();
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([]));
    await userEvent.click(screen.getByRole("tab", { name: "Saved" }));
    expect(await screen.findByText(/Save roles you're interested in/i)).toBeInTheDocument();
  });

  it("saves and unsaves from the card control", async () => {
    vi.mocked(api.saveJob).mockResolvedValue({ ...existingJob, saved: true });
    vi.mocked(api.unsaveJob).mockResolvedValue(undefined as never);
    renderJobs();
    await screen.findByText("Backend Engineer");
    await userEvent.click(screen.getByTestId("save-job-jobicy-existing"));
    await waitFor(() => expect(api.saveJob).toHaveBeenCalledWith("jobicy-existing"));
  });

  it("does not keep Saved results visible while Matches is loading", async () => {
    const savedJob: Job = { ...existingJob, id: "saved-only", title: "Saved Only Role", saved: true };
    let resolveMatches: ((value: JobListPage) => void) | undefined;
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") return Promise.resolve(pageOf([savedJob]));
      if (params.tab === "matches") {
        return new Promise<JobListPage>((resolve) => {
          resolveMatches = resolve;
        });
      }
      return Promise.resolve(pageOf([existingJob]));
    });
    renderJobs("/jobs?tab=saved");
    expect(await screen.findByText("Saved Only Role")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Matches" }));
    expect(await screen.findByText("Loading jobs…")).toBeInTheDocument();
    expect(screen.queryByText("Saved Only Role")).not.toBeInTheDocument();
    resolveMatches?.(pageOf([newJob]));
    expect(await screen.findByText("Platform Engineer")).toBeInTheDocument();
  });

  it("does not let an older query overwrite a newer tab", async () => {
    let resolveFirst: ((value: JobListPage) => void) | undefined;
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "matches") {
        return Promise.resolve(pageOf([newJob]));
      }
      return new Promise<JobListPage>((resolve) => {
        resolveFirst = resolve;
      });
    });
    renderJobs();
    await userEvent.click(screen.getByRole("tab", { name: "Matches" }));
    expect(await screen.findByText("Platform Engineer")).toBeInTheDocument();
    resolveFirst?.(pageOf([existingJob]));
    await waitFor(() => {
      expect(screen.queryByText("Backend Engineer")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Platform Engineer")).toBeInTheDocument();
  });

  it("separates verified and potential matches", async () => {
    vi.mocked(api.queryJobs).mockResolvedValue(
      pageOf([newJob, existingJob], {
        verified_count: 1,
        potential_count: 1,
        items: [
          {
            job: newJob,
            match: {
              job_id: newJob.id!,
              overall_score: 86,
              matched_skills: [],
              partial_matches: [],
              missing_skills: [],
              recommendation: "apply",
              rationale: "verified",
              score_kind: "verified",
            },
            saved: false,
          },
          {
            job: existingJob,
            match: {
              job_id: existingJob.id!,
              overall_score: 90,
              matched_skills: [],
              partial_matches: [],
              missing_skills: [],
              recommendation: "consider",
              rationale: "preliminary",
              score_kind: "preliminary",
            },
            saved: false,
          },
        ],
      }),
    );
    renderJobs("/jobs?tab=matches");
    expect(await screen.findByText("Verified Matches (1)")).toBeInTheDocument();
    expect(screen.getByText("Potential Matches (1)")).toBeInTheDocument();
    expect(screen.getByText(/86% Verified Fit/)).toBeInTheDocument();
    expect(screen.getAllByText(/Potential Match/).length).toBeGreaterThan(0);
    expect(screen.queryByText("90%")).not.toBeInTheDocument();
  });

  it("does not carry Discover search into Matches while keeping work mode", async () => {
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "matches") return Promise.resolve(pageOf([newJob]));
      return Promise.resolve(pageOf([existingJob]));
    });
    renderJobs(
      "/jobs?search=Software+engineering+internships+in+the+Bay+Area&q=Software+Engineering&location=San+Francisco+Bay+Area&industry=fintech&work_mode=hybrid",
    );
    const input = await screen.findByTestId("jobs-search-input");
    expect(input).toHaveValue("Software engineering internships in the Bay Area");
    expect(input).toHaveAttribute("data-has-query", "true");
    await userEvent.click(screen.getByRole("tab", { name: "Matches" }));
    expect(await screen.findByText("Platform Engineer")).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("data-has-query", "false");
    expect(input).toHaveAttribute("placeholder", "Search roles, locations, or work setup");
    await waitFor(() => {
      const lastQuery = vi.mocked(api.queryJobs).mock.calls.at(-1)?.[0];
      expect(lastQuery?.tab).toBe("matches");
      expect(lastQuery?.q).toBeUndefined();
      expect(lastQuery?.location ?? []).toEqual([]);
      expect(lastQuery?.industry ?? []).toEqual([]);
      expect(lastQuery?.work_mode).toEqual(["hybrid"]);
    });
  });

  it("clears the search field so placeholder is not an active query", async () => {
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([]));
    renderJobs("/jobs?search=Software+engineering+internships+in+the+Bay+Area&q=Software+Engineering");
    const input = await screen.findByTestId("jobs-search-input");
    expect(input).toHaveValue("Software engineering internships in the Bay Area");
    await userEvent.click(await screen.findByRole("button", { name: "Clear filters" }));
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("data-has-query", "false");
    expect((input as HTMLInputElement).placeholder).not.toMatch(/Software engineering internships in the Bay Area/i);
  });

  it("removes an unsaved job from the Saved tab immediately and keeps other cards usable", async () => {
    const jobA: Job = { ...existingJob, id: "saved-a", title: "Saved Role A", saved: true };
    const jobB: Job = { ...existingJob, id: "saved-b", title: "Saved Role B", saved: true };
    const jobC: Job = { ...existingJob, id: "saved-c", title: "Saved Role C", saved: true };
    let rejectUnsave: ((error: ApiClientError) => void) | undefined;
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") return Promise.resolve(pageOf([jobA, jobB, jobC]));
      return Promise.resolve(pageOf([existingJob]));
    });
    vi.mocked(api.unsaveJob).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectUnsave = reject;
        }),
    );

    renderJobs("/jobs?tab=saved");
    expect(await screen.findByText("Saved Role B")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("save-job-saved-b"));

    expect(screen.queryByText("Saved Role B")).not.toBeInTheDocument();
    expect(screen.getByText("Saved Role A")).toBeInTheDocument();
    expect(screen.getByText("Saved Role C")).toBeInTheDocument();
    expect(screen.queryByTestId("save-job-saved-b")).not.toBeInTheDocument();
    expect(screen.getByTestId("save-job-saved-a")).not.toBeDisabled();
    expect(screen.getByTestId("save-job-saved-c")).not.toBeDisabled();

    rejectUnsave?.(new ApiClientError(500, "save failed"));
    expect(await screen.findByText("Saved Role B")).toBeInTheDocument();
    expect(screen.getByText("Saved Role A")).toBeInTheDocument();
    expect(screen.getByText("Saved Role C")).toBeInTheDocument();
  });

  it("moves selection to a remaining saved job when the selected card is unsaved", async () => {
    const jobA: Job = { ...existingJob, id: "saved-a", title: "Saved Role A", saved: true };
    const jobB: Job = { ...existingJob, id: "saved-b", title: "Saved Role B", saved: true };
    const jobC: Job = { ...existingJob, id: "saved-c", title: "Saved Role C", saved: true };
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") return Promise.resolve(pageOf([jobA, jobB, jobC]));
      return Promise.resolve(pageOf([existingJob]));
    });
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));
    renderJobs("/jobs?tab=saved&selected=saved-b");
    expect(await screen.findByRole("heading", { name: "Saved Role B" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Saved" }));
    expect(screen.queryByRole("heading", { name: "Saved Role B" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved Role C" })).toBeInTheDocument();
  });

  it("clears Saved to the empty state when the last job is unsaved", async () => {
    const only: Job = { ...existingJob, id: "saved-only", title: "Last Saved Role", saved: true };
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") return Promise.resolve(pageOf([only]));
      return Promise.resolve(pageOf([existingJob]));
    });
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));
    renderJobs("/jobs?tab=saved");
    expect(await screen.findByText("Last Saved Role")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("save-job-saved-only"));
    expect(await screen.findByText("No saved jobs yet")).toBeInTheDocument();
    expect(screen.queryByText("Last Saved Role")).not.toBeInTheDocument();
  });

  it("keeps an unsaved Discover card visible and only toggles that card's pending bookmark", async () => {
    const listed: Job = { ...existingJob, saved: true };
    const other: Job = { ...newJob, id: "other-discover", title: "Other Discover Role", saved: false };
    vi.mocked(api.queryJobs).mockResolvedValue(pageOf([listed, other]));
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));
    renderJobs("/jobs");
    expect(await screen.findByText("Backend Engineer")).toBeInTheDocument();
    const bookmark = screen.getByTestId("save-job-jobicy-existing");
    expect(bookmark).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(bookmark);
    expect(screen.getByText("Backend Engineer")).toBeInTheDocument();
    expect(screen.getByTestId("save-job-jobicy-existing")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("save-job-jobicy-existing")).toBeDisabled();
    expect(screen.getByTestId("save-job-other-discover")).not.toBeDisabled();
  });

  it("opens the filter panel and applies a work-mode filter", async () => {
    renderJobs();
    await screen.findByText("Backend Engineer");
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(await screen.findByText("Work setup")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Hybrid" }));
    await waitFor(() => {
      const lastQuery = vi.mocked(api.queryJobs).mock.calls.at(-1)?.[0];
      expect(lastQuery?.work_mode).toEqual(expect.arrayContaining(["hybrid"]));
    });
  });

  it("lets Location keep spaces while typing multi-word cities", async () => {
    renderJobs();
    await screen.findByText("Backend Engineer");
    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    const location = await screen.findByPlaceholderText(/San Francisco, Remote US/i);
    for (const city of ["San Francisco", "New York", "Palo Alto", "Remote US"]) {
      await userEvent.clear(location);
      await userEvent.type(location, city);
      expect(location).toHaveValue(city);
    }
  });

  it("keeps B saved when A's in-flight save fails after B succeeds", async () => {
    const jobA: Job = { ...existingJob, id: "disc-a", title: "Discover Role A", saved: false };
    const jobB: Job = { ...existingJob, id: "disc-b", title: "Discover Role B", saved: false };
    const savedIds = new Set<string>();
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") {
        return Promise.resolve(
          pageOf(
            [jobA, jobB].filter((job) => savedIds.has(job.id!)).map((job) => ({ ...job, saved: true })),
          ),
        );
      }
      return Promise.resolve(
        pageOf([
          { ...jobA, saved: savedIds.has("disc-a") },
          { ...jobB, saved: savedIds.has("disc-b") },
        ]),
      );
    });
    let rejectA: ((error: ApiClientError) => void) | undefined;
    let resolveB: ((value: Job) => void) | undefined;
    vi.mocked(api.saveJob).mockImplementation((jobId: string) => {
      if (jobId === "disc-a") {
        return new Promise<Job>((_resolve, reject) => {
          rejectA = reject;
        });
      }
      return new Promise<Job>((resolve) => {
        resolveB = resolve;
      });
    });

    renderJobs();
    expect(await screen.findByText("Discover Role A")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("save-job-disc-a"));
    await userEvent.click(screen.getByTestId("save-job-disc-b"));
    expect(screen.getByTestId("save-job-disc-a")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("save-job-disc-b")).toHaveAttribute("aria-pressed", "true");

    savedIds.add("disc-b");
    resolveB?.({ ...jobB, saved: true });
    await waitFor(() => expect(screen.getByTestId("save-job-disc-b")).toHaveAttribute("aria-pressed", "true"));
    rejectA?.(new ApiClientError(500, "save failed"));

    await waitFor(() => expect(screen.getByTestId("save-job-disc-a")).toHaveAttribute("aria-pressed", "false"));
    expect(screen.getByTestId("save-job-disc-b")).toHaveAttribute("aria-pressed", "true");
  });

  it("does not issue a conflicting unsave when the same unsaved card is clicked twice", async () => {
    vi.mocked(api.saveJob).mockImplementation(() => new Promise(() => undefined));
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));
    renderJobs();
    await screen.findByText("Backend Engineer");
    const bookmark = screen.getByTestId("save-job-jobicy-existing");
    await userEvent.click(bookmark);
    await userEvent.click(bookmark);
    expect(api.saveJob).toHaveBeenCalledTimes(1);
    expect(api.unsaveJob).not.toHaveBeenCalled();
  });

  it("does not clear selection because a stale Saved cache lacked the unsaved job", async () => {
    const jobA: Job = { ...existingJob, id: "saved-a", title: "Saved Role A", saved: true };
    const jobB: Job = { ...existingJob, id: "saved-b", title: "Saved Role B", saved: true };
    const jobC: Job = { ...existingJob, id: "saved-c", title: "Saved Role C", saved: true };
    const route = "/jobs?tab=saved&selected=saved-b";
    const activeParams = toJobQueryParams(readJobsWorkspace(new URLSearchParams(route.slice("/jobs?".length))));
    const staleParams = { ...activeParams, sort: "newest" as const };
    const client = createTestQueryClient();
    client.setQueryData(["jobs-workspace", staleParams], pageOf([jobA], { page: 1, total: 1 }));
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved") return Promise.resolve(pageOf([jobA, jobB, jobC]));
      return Promise.resolve(pageOf([existingJob]));
    });
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));

    renderJobs(route, client);
    expect(await screen.findByRole("heading", { name: "Saved Role B" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Saved" }));
    expect(screen.queryByRole("heading", { name: "Saved Role B" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved Role C" })).toBeInTheDocument();
  });

  it("does not show the empty Saved state after unsaving the last job on a later page", async () => {
    const jobA: Job = { ...existingJob, id: "saved-a", title: "Saved Role A", saved: true };
    const jobC: Job = { ...existingJob, id: "saved-c", title: "Saved Page Two Role", saved: true };
    vi.mocked(api.queryJobs).mockImplementation((params = {}) => {
      if (params.tab === "saved" && params.page === 2) {
        return Promise.resolve(
          pageOf([jobC], { page: 2, page_size: 40, total: 41, ids: ["saved-a", jobC.id!] }),
        );
      }
      if (params.tab === "saved") {
        return Promise.resolve(pageOf([jobA], { page: 1, page_size: 40, total: 40 }));
      }
      return Promise.resolve(pageOf([existingJob]));
    });
    vi.mocked(api.unsaveJob).mockImplementation(() => new Promise(() => undefined));

    renderJobs("/jobs?tab=saved&page=2");
    expect(await screen.findByText("Saved Page Two Role")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("save-job-saved-c"));
    expect(screen.queryByText("No saved jobs yet")).not.toBeInTheDocument();
    expect(await screen.findByText("Saved Role A")).toBeInTheDocument();
  });
});

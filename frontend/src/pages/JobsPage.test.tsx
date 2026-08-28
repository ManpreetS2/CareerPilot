import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobsPage } from "./JobsPage";
import { api, ApiClientError } from "../lib/api";
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

function renderJobs(route = "/jobs") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
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
});

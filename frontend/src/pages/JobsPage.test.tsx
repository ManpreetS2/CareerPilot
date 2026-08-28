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
import type { Job, ScoutJobsResponse } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getJobs: vi.fn(),
      scoutJobs: vi.fn(),
      getStoredScores: vi.fn(),
      ingestJobUrl: vi.fn(),
      verifyJobs: vi.fn(),
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

function renderJobs() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <JobsPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("JobsPage discovery progress", () => {
  beforeEach(() => {
    vi.mocked(api.getJobs).mockResolvedValue([existingJob]);
    vi.mocked(api.getStoredScores).mockResolvedValue([
      {
        job_id: "jobicy-existing",
        overall_score: 40,
        scoring_version: 2,
        ranking_score: 40,
        recommendation: "consider",
        matched_skills: [],
        partial_matches: [],
        missing_skills: [],
        rationale: "stored",
      },
    ]);
    vi.mocked(api.scoutJobs).mockReset();
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
    await waitFor(() => expect(api.getStoredScores).toHaveBeenCalled());
  });

  it("sorts by ranking_score even when overall_score would reverse the order", async () => {
    vi.mocked(api.scoutJobs).mockResolvedValue({
      jobs: [existingJob, newJob],
      jobs_found: 2,
      matched_count: 2,
      sources_searched: 6,
      sources_unavailable: 0,
    });
    vi.mocked(api.getStoredScores).mockResolvedValue([
      {
        job_id: "jobicy-existing",
        overall_score: 91,
        scoring_version: 2,
        ranking_score: 52,
        recommendation: "consider",
        matched_skills: [],
        partial_matches: [],
        missing_skills: [],
        rationale: "stored",
      },
      {
        job_id: "himalayas-new",
        overall_score: 74,
        scoring_version: 2,
        ranking_score: 71,
        recommendation: "consider",
        matched_skills: [],
        partial_matches: [],
        missing_skills: [],
        rationale: "stored",
      },
    ]);
    renderJobs();
    await screen.findByText("Backend Engineer");
    await userEvent.click(screen.getByTestId("find-jobs-button"));
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
});

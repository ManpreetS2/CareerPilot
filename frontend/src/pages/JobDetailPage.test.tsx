import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobDetailPage } from "./JobDetailPage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient } from "../test/render";
import "../index.css";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getJob: vi.fn(),
      getJobIntelligence: vi.fn(),
      extractJobIntelligence: vi.fn(),
      getJobs: vi.fn(),
      getStoredScores: vi.fn(),
      getStoredScore: vi.fn(),
      scoreJob: vi.fn(),
      getInterviewPrep: vi.fn(),
      prepareInterview: vi.fn(),
      verifyJob: vi.fn(),
    },
  };
});

function renderJob() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={["/jobs/job-1"]}>
          <Routes>
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("JobDetailPage", () => {
  beforeEach(() => {
    vi.mocked(api.getJob).mockResolvedValue({
      id: "job-1",
      title: "Staff Platform Engineer for Extremely-Long-Company-Name-That-Must-Wrap",
      company: "Northwind Analytics International",
      url: "https://jobs.example.com/very/long/path/to/a/posting",
      description: "Python",
      source: "manual",
      status: "verified",
    });
    vi.mocked(api.getJobIntelligence).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getJobs).mockResolvedValue([]);
    vi.mocked(api.getStoredScores).mockResolvedValue([]);
    vi.mocked(api.getStoredScore).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.getInterviewPrep).mockRejectedValue(new ApiClientError(404, "None"));
    vi.mocked(api.extractJobIntelligence).mockReset();
    vi.mocked(api.scoreJob).mockReset();
    vi.mocked(api.prepareInterview).mockReset();
  });

  it("loads stored job evidence without extracting, scoring, or generating interview prep", async () => {
    renderJob();
    expect(await screen.findByRole("heading", { name: /Staff Platform Engineer/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getJob).toHaveBeenCalled();
      expect(api.getJobIntelligence).toHaveBeenCalled();
      expect(api.getStoredScore).toHaveBeenCalled();
    });
    expect(api.extractJobIntelligence).not.toHaveBeenCalled();
    expect(api.scoreJob).not.toHaveBeenCalled();
    expect(api.prepareInterview).not.toHaveBeenCalled();
  });

  it("wraps long job titles instead of truncating them", async () => {
    renderJob();
    const heading = await screen.findByRole("heading", { name: /Staff Platform Engineer/i });
    expect(heading).toHaveClass("wrap-anywhere");
    expect(getComputedStyle(heading).overflowWrap).toBe("anywhere");
  });
});

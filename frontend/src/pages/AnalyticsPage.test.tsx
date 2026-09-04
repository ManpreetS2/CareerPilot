import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsPage } from "./AnalyticsPage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";
import type { ApplicationAnalyticsSummary } from "../lib/types";
import "../index.css";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    user: testUser,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    deleteAccount: vi.fn(),
  }),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getAnalyticsSummary: vi.fn(),
    },
  };
});

const emptySummary: ApplicationAnalyticsSummary = {
  generated_at: "2026-09-04T00:00:00Z",
  funnel: [
    { stage: "saved", label: "Saved", jobs_count: 0, conversion_from_previous: null },
    { stage: "materials_generated", label: "Materials generated", jobs_count: 0, conversion_from_previous: null },
    { stage: "materials_approved", label: "Materials approved", jobs_count: 0, conversion_from_previous: null },
    { stage: "applied", label: "Applied", jobs_count: 0, conversion_from_previous: null },
    { stage: "interviewing", label: "Interviewing", jobs_count: 0, conversion_from_previous: null },
    { stage: "offer", label: "Offer", jobs_count: 0, conversion_from_previous: null },
  ],
  rejected_count: 0,
  withdrawn_count: 0,
  median_days_saved_to_applied: null,
  median_days_applied_to_interviewing: null,
  by_source: [],
  by_match_score_band: [],
  notice: null,
};

const populatedSummary: ApplicationAnalyticsSummary = {
  generated_at: "2026-09-04T00:00:00Z",
  funnel: [
    { stage: "saved", label: "Saved", jobs_count: 10, conversion_from_previous: null },
    { stage: "materials_generated", label: "Materials generated", jobs_count: 6, conversion_from_previous: 0.6 },
    { stage: "materials_approved", label: "Materials approved", jobs_count: 4, conversion_from_previous: 0.667 },
    { stage: "applied", label: "Applied", jobs_count: 3, conversion_from_previous: 0.75 },
    { stage: "interviewing", label: "Interviewing", jobs_count: 1, conversion_from_previous: 0.333 },
    { stage: "offer", label: "Offer", jobs_count: 0, conversion_from_previous: 0 },
  ],
  rejected_count: 2,
  withdrawn_count: 1,
  median_days_saved_to_applied: 4.5,
  median_days_applied_to_interviewing: null,
  by_source: [
    { label: "greenhouse", applied_count: 2, total_count: 5, applied_rate: 0.4, small_sample: false },
    { label: "manual", applied_count: 1, total_count: 2, applied_rate: 0.5, small_sample: true },
  ],
  by_match_score_band: [
    { label: "85+", applied_count: 2, total_count: 2, applied_rate: 1.0, small_sample: true },
  ],
  notice: null,
};

function renderAnalytics(route = "/analytics") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/profile" element={<p>Profile destination</p>} />
            <Route path="/jobs" element={<p>Discover destination</p>} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    vi.mocked(api.getAnalyticsSummary).mockReset();
  });

  it("renders the Analytics route heading", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    renderAnalytics();
    expect(await screen.findByRole("heading", { name: "Analytics" })).toBeInTheDocument();
  });

  it("shows a profile-required empty state", async () => {
    vi.mocked(api.getAnalyticsSummary).mockRejectedValue(
      new ApiClientError(409, "Complete your profile", {
        code: "profile_required",
        next_route: "/profile",
        missing: ["candidate_profile"],
      }),
    );
    renderAnalytics();
    expect(await screen.findByRole("heading", { name: "Complete your profile first" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Profile" })).toHaveAttribute("href", "/profile");
  });

  it("shows a loading state while the summary is pending", async () => {
    vi.mocked(api.getAnalyticsSummary).mockReturnValue(new Promise(() => undefined));
    renderAnalytics();
    expect(await screen.findByText("Loading analytics…")).toBeInTheDocument();
  });

  it("shows an API error with retry", async () => {
    vi.mocked(api.getAnalyticsSummary).mockRejectedValue(new ApiClientError(500, "analytics failed"));
    renderAnalytics();
    expect(await screen.findByText("analytics failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows a no-activity empty state alongside the zeroed funnel", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(emptySummary);
    renderAnalytics();
    expect(await screen.findByRole("heading", { name: "No conversion activity yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Discover" })).toHaveAttribute("href", "/jobs");
    // The funnel itself still renders — zero is a real, honest value, not an error.
    expect(screen.getByTestId("analytics-funnel")).toBeInTheDocument();
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);
  });

  it("renders funnel counts and conversion rates", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    renderAnalytics();
    await screen.findByTestId("analytics-funnel");
    expect(screen.queryByRole("heading", { name: "No conversion activity yet" })).not.toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText(/6 · 60% of previous/)).toBeInTheDocument();
    expect(screen.getByText(/3 · 75% of previous/)).toBeInTheDocument();
  });

  it("shows exit counts and median days", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    renderAnalytics();
    await screen.findByTestId("analytics-summary");
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("4.5 days")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows source and match-score-band breakdowns with a small-sample caveat", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    renderAnalytics();
    await screen.findByRole("heading", { name: "By job source" });
    expect(screen.getByText(/2 \/ 5 applied \(40%\)/)).toBeInTheDocument();
    expect(screen.getByText(/1 \/ 2 applied \(50%\) · too few to trust/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "By match-score band" })).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 2 applied \(100%\) · too few to trust/)).toBeInTheDocument();
  });

  it("shows the backend notice when analytics predate the tracked history", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue({
      ...populatedSummary,
      notice: "Some of your applications predate conversion tracking.",
    });
    renderAnalytics();
    expect(await screen.findByTestId("analytics-notice")).toHaveTextContent(
      "Some of your applications predate conversion tracking.",
    );
  });

  it("uses dark and light tokens without cyan or beige", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    renderAnalytics();
    await screen.findByRole("heading", { name: "Analytics" });
    const page = screen.getByTestId("analytics-page");
    expect(page.className).not.toMatch(/cyan|beige/);
    document.documentElement.classList.add("dark");
    expect(getComputedStyle(page).color).not.toBe("rgb(0, 255, 255)");
    document.documentElement.classList.remove("dark");
  });

  it("stacks on a 390px-wide surface without a giant table", async () => {
    vi.mocked(api.getAnalyticsSummary).mockResolvedValue(populatedSummary);
    const { container } = renderAnalytics();
    await screen.findByTestId("analytics-summary");
    const page = screen.getByTestId("analytics-page");
    expect(page).toHaveClass("max-w-full");
    expect(container.querySelector("table")).toBeNull();
    expect(page.className).toMatch(/space-y-6/);
  });
});

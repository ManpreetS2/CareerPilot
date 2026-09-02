import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { OnboardingPage } from "./OnboardingPage";
import { api, ApiClientError } from "../lib/api";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";

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
      savePreferences: vi.fn().mockResolvedValue({
        target_roles: [],
        preferred_locations: [],
        constraints: [],
      }),
      parseResume: vi.fn(),
    },
  };
});

const parsedResume = {
  candidate: {
    id: "cand-001",
    name: "Alex Rivera",
    skills: ["Python"],
    projects: [],
    experience: [],
    education: [],
    certifications: [],
    strengths: [],
    evidence_links: [],
  },
  preferences: null,
  note: "Grounded",
};

function renderOnboarding() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={["/onboarding"]}>
          <Routes>
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/dashboard" element={<div>Entered app</div>} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

async function goToResumeStep(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId("onboarding-continue"));
  await user.click(screen.getByTestId("onboarding-continue"));
  expect(await screen.findByTestId("onboarding-step-3")).toBeInTheDocument();
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.mocked(api.parseResume).mockReset();
    vi.mocked(api.savePreferences).mockResolvedValue({
      target_roles: [],
      preferred_locations: [],
      constraints: [],
    });
  });
  it("walks through seven steps", async () => {
    const user = userEvent.setup();
    renderOnboarding();
    expect(screen.getByTestId("onboarding-step-1")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-2")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-3")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-4")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-5")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-6")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-7")).toBeInTheDocument();
  });

  it("shows a human-readable role type on the review step, not the raw value", async () => {
    const user = userEvent.setup();
    renderOnboarding();
    for (let step = 1; step < 7; step += 1) {
      await user.click(screen.getByTestId("onboarding-continue"));
    }
    expect(await screen.findByTestId("onboarding-step-7")).toBeInTheDocument();
    expect(screen.getByText("Both internships and full-time")).toBeInTheDocument();
    expect(screen.queryByText("both")).not.toBeInTheDocument();
  });

  it("lets Skip / End setup enter the app without blocking", async () => {
    const user = userEvent.setup();
    renderOnboarding();
    await user.click(screen.getByTestId("onboarding-skip"));
    expect(await screen.findByText("Entered app")).toBeInTheDocument();
    const stored = JSON.parse(localStorage.getItem("careerpilot.onboarding.u1") || "{}");
    expect(stored.skipped).toBe(true);
    expect(stored.completed).toBe(false);
  });

  it("allows continuing past resume upload without a file", async () => {
    const user = userEvent.setup();
    renderOnboarding();
    await user.click(screen.getByTestId("onboarding-continue"));
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-3")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-4")).toBeInTheDocument();
    expect(screen.getByText(/No parsed profile yet/i)).toBeInTheDocument();
  });

  it("moves back to the previous step", async () => {
    const user = userEvent.setup();
    renderOnboarding();
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("onboarding-step-2")).toBeInTheDocument();
    await user.click(screen.getByTestId("onboarding-back"));
    expect(await screen.findByTestId("onboarding-step-1")).toBeInTheDocument();
  });

  it("goes back two full steps on a real double-click, and does not get stuck", async () => {
    // Documents a real bug found in a live browser, not one this test
    // reproduces the original mechanism of: an ordinary double-click on
    // Back — not a contrived edge case — left both the exiting and
    // entering step cards permanently stuck at opacity 0, with no error
    // and no way to recover short of a reload. Confirmed live in Chrome.
    // It reproduced identically with AnimatePresence's mode="wait" on or
    // off, so the fault was the animated exit/enter lifecycle itself under
    // back-to-back key changes, not that one option — the fix removes the
    // animation from this transition rather than tuning it. jsdom's
    // animation timing never reproduced the stuck state either way, so
    // this guards against a future regression obvious enough to break
    // navigation outright, not the original failure itself.
    //
    // Separately, onBack previously computed its target step from the
    // `step` closed over at render time rather than a functional update,
    // so two Back clicks fired in the same tick (no `await` between them,
    // deliberate here) both read the same stale value and only moved back
    // one step instead of two — silently dropping half a double-click.
    const user = userEvent.setup();
    renderOnboarding();
    await user.click(screen.getByTestId("onboarding-continue"));
    await user.click(screen.getByTestId("onboarding-continue"));
    await user.click(screen.getByTestId("onboarding-back"));
    void user.click(screen.getByTestId("onboarding-back"));
    expect(await screen.findByTestId("onboarding-step-1")).toBeInTheDocument();
    expect(screen.queryByTestId("onboarding-step-2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("onboarding-step-3")).not.toBeInTheDocument();
  });

  it("uses the Discover Analyze Prepare Track workflow labels", () => {
    renderOnboarding();
    const path = screen.getByTestId("workflow-path");
    expect(path).toHaveTextContent("Discover");
    expect(path).toHaveTextContent("Analyze");
    expect(path).toHaveTextContent("Prepare");
    expect(path).toHaveTextContent("Track");
    expect(path).not.toHaveTextContent("Jobs");
    expect(path).not.toHaveTextContent("Match");
  });

  it("shows resume parsing stages while the API is still unresolved", async () => {
    const user = userEvent.setup();
    let resolveParse: (value: typeof parsedResume) => void = () => {};
    vi.mocked(api.parseResume).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveParse = resolve;
        }),
    );
    renderOnboarding();
    await goToResumeStep(user);
    const file = new File(["%PDF-1.4 test"], "resume.pdf", { type: "application/pdf" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByTestId("resume-parsing-progress")).toBeInTheDocument();
    expect(screen.getByText("Reading your resume")).toBeInTheDocument();
    expect(screen.getByText("Almost ready")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-step-3")).toBeInTheDocument();
    expect(screen.queryByText(/No parsed profile yet/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("resume-parse-stage-4")).not.toHaveAttribute("data-state", "complete");
    resolveParse(parsedResume);
    expect(await screen.findByTestId("onboarding-step-4")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-parsing-progress")).not.toBeInTheDocument();
    expect(screen.getByText("Alex Rivera")).toBeInTheDocument();
  });

  it("exits loading and offers Retry when parsing fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.parseResume)
      .mockRejectedValueOnce(
        new ApiClientError(502, "AI service temporarily unavailable. Please try again."),
      )
      .mockResolvedValueOnce(parsedResume);
    renderOnboarding();
    await goToResumeStep(user);
    const file = new File(["%PDF-1.4 test"], "resume.pdf", { type: "application/pdf" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(screen.getByTestId("onboarding-continue"));
    expect(await screen.findByText("AI service temporarily unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-parsing-progress")).not.toBeInTheDocument();
    expect(screen.getByTestId("onboarding-step-3")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("onboarding-step-4")).toBeInTheDocument();
    expect(api.parseResume).toHaveBeenCalledTimes(2);
  });
});

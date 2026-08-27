import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OnboardingPage } from "./OnboardingPage";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    user: testUser,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock("../lib/api", () => ({
  api: {
    savePreferences: vi.fn().mockResolvedValue({
      target_roles: [],
      preferred_locations: [],
      constraints: [],
    }),
    parseResume: vi.fn(),
  },
}));

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

describe("OnboardingPage", () => {
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
});

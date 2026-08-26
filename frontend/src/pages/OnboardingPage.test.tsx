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

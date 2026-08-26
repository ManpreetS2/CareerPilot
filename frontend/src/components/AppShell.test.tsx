import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell, PRIMARY_NAV, WORKFLOW_NAV } from "./AppShell";
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

function renderShell(route = "/dashboard") {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<div>Dashboard body</div>} />
              <Route path="/jobs" element={<div>Jobs body</div>} />
              <Route path="/jobs/:jobId" element={<div>Analyze body</div>} />
              <Route path="/jobs/:jobId/prepare" element={<div>Prepare body</div>} />
              <Route path="/analyze" element={<div>Analyze empty</div>} />
              <Route path="/prepare" element={<div>Prepare empty</div>} />
              <Route path="/track" element={<div>Track body</div>} />
              <Route path="/profile" element={<div>Profile body</div>} />
              <Route path="/resume" element={<div>Resume body</div>} />
              <Route path="/settings" element={<div>Settings body</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("exposes skip to content and the workflow-first primary nav order", () => {
    renderShell();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(WORKFLOW_NAV.map((item) => item.label)).toEqual([
      "Overview",
      "Discover",
      "Analyze",
      "Prepare",
      "Track",
    ]);
    expect(PRIMARY_NAV.map((item) => item.label)).toEqual([
      "Overview",
      "Discover",
      "Analyze",
      "Prepare",
      "Track",
      "Profile",
      "Resume",
      "Settings",
    ]);
    expect(screen.queryByRole("link", { name: "Applications" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
  });

  it("opens the command palette with Control+K", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByTestId("command-palette")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Overview/i })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("command-palette")).not.toBeInTheDocument();
  });

  it("opens the mobile navigation drawer, traps focus, and closes on Escape", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByTestId("mobile-nav-trigger"));
    const drawer = await screen.findByTestId("mobile-nav");
    const labels = within(drawer)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(labels).toEqual([
      "Overview",
      "Discover",
      "Analyze",
      "Prepare",
      "Track",
      "Profile",
      "Resume",
      "Settings",
    ]);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("mobile-nav")).not.toBeInTheDocument();
  });
});

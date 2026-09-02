import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell, PRIMARY_NAV, WORKFLOW_NAV } from "./AppShell";
import { ThemeProvider } from "../lib/theme";
import { createTestQueryClient, testUser } from "../test/render";
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
              <Route path="/growth" element={<div>Growth body</div>} />
              <Route path="/profile" element={<div>Profile body</div>} />
              <Route path="/resume" element={<div>Resume body</div>} />
              <Route
                path="/settings"
                element={
                  <div data-testid="settings-page">
                    <h1>Settings</h1>
                    <button type="button">Light</button>
                  </div>
                }
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

function centeringClass(value: string) {
  return /\b(items-center|justify-center|place-items-center|min-h-screen)\b/.test(value);
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
      "Growth",
      "Resume",
      "Settings",
    ]);
    expect(screen.queryByRole("link", { name: "Applications" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("pointer-halo")).not.toBeInTheDocument();
    expect(document.querySelector(".pointer-halo")).toBeNull();
    expect(screen.getByTestId("app-sidebar").querySelector(".glass-refract")).toBeNull();
  });

  it("keeps the skip link visually hidden until keyboard focus, then focuses #main", async () => {
    const user = userEvent.setup();
    renderShell("/settings");
    const skip = screen.getByTestId("skip-to-content");
    const main = document.getElementById("main");

    expect(skip).toHaveClass("skip-link");
    expect(skip).not.toHaveFocus();
    expect(getComputedStyle(skip).position).toBe("absolute");
    expect(main).toHaveAttribute("tabIndex", "-1");

    await user.tab();
    expect(skip).toHaveFocus();
    expect(getComputedStyle(skip).position).toBe("fixed");
    expect(Number.parseInt(getComputedStyle(skip).zIndex, 10)).toBeGreaterThanOrEqual(100);

    await user.keyboard("{Enter}");
    expect(main).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Light" })).toHaveFocus();
  });

  it("does not vertically center Settings content in the shell", () => {
    renderShell("/settings");
    const main = document.getElementById("main");
    expect(main).not.toBeNull();
    expect(centeringClass(main?.className ?? "")).toBe(false);
    expect(main).toHaveClass("pt-8");
    expect(screen.getByTestId("settings-page")).toBeInTheDocument();
    const shell = screen.getByTestId("app-shell");
    expect(shell.className).not.toMatch(/\b(items-center|justify-center|place-items-center)\b/);
  });

  it("opens the command palette with Control+K as a fixed top overlay and closes on Escape", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByTestId("command-palette");
    expect(palette).toBeInTheDocument();
    expect(palette).toHaveClass("command-palette");
    expect(screen.getByRole("option", { name: /Overview/i })).toBeInTheDocument();
    expect(document.body.contains(palette)).toBe(true);
    expect(screen.getByTestId("app-shell").contains(palette)).toBe(false);
    const style = getComputedStyle(palette);
    expect(style.position).toBe("fixed");
    expect(style.bottom).toBe("auto");
    expect(style.bottom).not.toBe("0px");
    expect(Number.parseInt(style.zIndex, 10)).toBeGreaterThanOrEqual(80);
    const probe = document.createElement("div");
    probe.className = "command-palette";
    document.body.appendChild(probe);
    expect(getComputedStyle(probe).position).toBe("fixed");
    probe.remove();
    expect(screen.getByLabelText("Filter commands")).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("command-palette")).not.toBeInTheDocument();
  });

  it("opens the command palette with Command+K", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.keyboard("{Meta>}k{/Meta}");
    expect(await screen.findByTestId("command-palette")).toBeInTheDocument();
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
      "Growth",
      "Resume",
      "Settings",
    ]);
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
    const sheet = screen.getByRole("dialog");
    expect(sheet.className).toMatch(/max-h-\[100dvh\]/);
    expect(getComputedStyle(sheet).overflowY).toBe("auto");
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("mobile-nav")).not.toBeInTheDocument();
  });

  it("keeps the desktop sidebar fixed and out of document flow", () => {
    renderShell("/settings");
    const sidebar = screen.getByTestId("app-sidebar");
    const main = document.getElementById("main");
    expect(getComputedStyle(sidebar).position).toBe("fixed");
    expect(getComputedStyle(sidebar).left).toBe("0px");
    expect(main).toHaveClass("lg:ml-56", "pt-8");
    expect(getComputedStyle(main as HTMLElement).paddingTop).toBe("2rem");
    expect(screen.getByRole("heading", { name: "Settings" }).getBoundingClientRect().top).toBeLessThan(160);
  });

  it("filters command palette items and navigates with Enter", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.keyboard("{Control>}k{/Control}");
    await user.type(screen.getByLabelText("Filter commands"), "set");
    expect(screen.getByRole("option", { name: /Settings/i })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /^Overview/i })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByTestId("command-palette")).not.toBeInTheDocument();
  });

  it("requests a top scroll when the route changes", async () => {
    const user = userEvent.setup();
    const scrollTo = vi.mocked(window.scrollTo);
    renderShell("/dashboard");
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    scrollTo.mockClear();
    await user.click(
      within(screen.getByTestId("app-sidebar")).getByRole("link", { name: "Settings", hidden: true }),
    );
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });
});

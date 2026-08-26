import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SettingsPage } from "../pages/SettingsPage";
import { ThemeProvider } from "../lib/theme";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createTestQueryClient, testUser } from "../test/render";
import { vi } from "vitest";

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
    health: vi.fn().mockResolvedValue({ status: "ok", database: "ok" }),
  },
}));

function renderSettings() {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider>
        <MemoryRouter>
          <SettingsPage />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("theme", () => {
  it("supports light, dark, and system preferences", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("careerpilot-theme")).toBe("dark");
    await user.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    await user.click(screen.getByRole("button", { name: "System" }));
    expect(localStorage.getItem("careerpilot-theme")).toBe("system");
  });

  it("does not wrap Settings in a vertically centered viewport", () => {
    const { container } = renderSettings();
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).not.toMatch(/\b(min-h-screen|items-center|justify-center|place-items-center)\b/);
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "../pages/SettingsPage";
import { ThemeProvider } from "../lib/theme";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { createTestQueryClient, testUser } from "../test/render";

const deleteAccount = vi.fn();

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    user: testUser,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    deleteAccount,
  }),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      health: vi.fn().mockResolvedValue({ status: "ok", database: "ok" }),
    },
  };
});

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

  it("persists reduced motion on the document", async () => {
    const user = userEvent.setup();
    renderSettings();
    await user.click(screen.getByLabelText("Reduce motion"));
    expect(document.documentElement.classList.contains("reduce-motion")).toBe(true);
  });
});

describe("privacy and deletion", () => {
  beforeEach(() => {
    deleteAccount.mockReset();
  });

  it("links to the public privacy page", () => {
    renderSettings();
    expect(screen.getByRole("link", { name: "Read the privacy page" })).toHaveAttribute(
      "href",
      "/privacy",
    );
  });

  it("requires typing DELETE before destroying the account", async () => {
    const user = userEvent.setup();
    deleteAccount.mockResolvedValue(undefined);
    renderSettings();
    await user.click(screen.getByRole("button", { name: "Delete account and data" }));
    const confirm = screen.getByRole("button", { name: "Delete permanently" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Type DELETE to confirm account deletion"), "DELETE");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => {
      expect(deleteAccount).toHaveBeenCalledTimes(1);
    });
  });

  it("keeps the session and allows retry when deletion fails", async () => {
    const user = userEvent.setup();
    deleteAccount.mockRejectedValueOnce(new Error("API unreachable"));
    renderSettings();
    await user.click(screen.getByRole("button", { name: "Delete account and data" }));
    await user.type(screen.getByLabelText("Type DELETE to confirm account deletion"), "DELETE");
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    expect(await screen.findByText(/Couldn't delete the account/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete permanently" })).toBeEnabled();
    expect(deleteAccount).toHaveBeenCalled();
  });
});

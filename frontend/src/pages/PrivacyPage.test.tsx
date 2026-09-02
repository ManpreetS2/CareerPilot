import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PrivacyPage } from "./PrivacyPage";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
    deleteAccount: vi.fn(),
  }),
}));

describe("PrivacyPage", () => {
  it("is readable without authentication and does not claim certifications", () => {
    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Privacy" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByText(/local SQLite database/i)).toBeInTheDocument();
    expect(screen.getByText(/Fit scoring is deterministic/i)).toBeInTheDocument();
    expect(screen.getByText(/does not claim end-to-end encryption, SOC 2, HIPAA/i)).toBeInTheDocument();
    expect(screen.queryByText(/we are SOC 2 certified/i)).not.toBeInTheDocument();
  });
});

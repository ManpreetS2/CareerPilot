import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "./ProtectedRoute";

vi.mock("../lib/auth", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../lib/auth";

describe("ProtectedRoute", () => {
  it("shows a loading state instead of flashing /login while the session is checked", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: true,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      deleteAccount: vi.fn(),
    });
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/login" element={<p>Login page</p>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<p>Dashboard secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Checking your session…")).toBeInTheDocument();
    expect(screen.queryByText("Login page")).not.toBeInTheDocument();
    expect(screen.queryByText("Dashboard secret")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users to /login after loading finishes", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      deleteAccount: vi.fn(),
    });
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/login" element={<p>Login page</p>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<p>Dashboard secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard secret")).not.toBeInTheDocument();
  });

  it("remembers the full requested URL, including query and hash, for after sign-in", () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      deleteAccount: vi.fn(),
    });
    function LoginProbe() {
      const location = useLocation();
      return <p>from={(location.state as { from?: string } | null)?.from}</p>;
    }
    render(
      <MemoryRouter initialEntries={["/jobs?tab=matches&selected=job-7#preview"]}>
        <Routes>
          <Route path="/login" element={<LoginProbe />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/jobs" element={<p>Jobs secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("from=/jobs?tab=matches&selected=job-7#preview")).toBeInTheDocument();
  });
});

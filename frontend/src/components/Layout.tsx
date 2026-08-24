import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  LayoutDashboard,
  LogOut,
  Moon,
  Plane,
  Sun,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { APP_NAME, APP_TAGLINE } from "../lib/config";
import { useTheme } from "../lib/theme";
import { ErrorBoundary } from "./ErrorBoundary";

type NavItem = { to: string; label: string; icon: LucideIcon };

const nav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { to: "/applications", label: "Applications", icon: FileText },
];

export function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const location = useLocation();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  async function onLogout() {
    setLoggingOut(true);
    try {
      // No explicit navigate() here: logout() clears the auth user, and
      // Layout only ever renders inside ProtectedRoute (see App.tsx) — that
      // re-render is what redirects to /login once `user` goes null.
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then(() => {
        if (!cancelled) setBackendOk(true);
      })
      .catch(() => {
        if (!cancelled) setBackendOk(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-[var(--bg)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-ink-900 focus:px-3 focus:py-2 focus:text-ink-50"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-[var(--line)] bg-[var(--bg)]/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/dashboard" className="group flex min-w-0 items-center gap-2.5">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-accent-600/10 text-accent-700 dark:bg-accent-400/10 dark:text-accent-300">
              <Plane className="h-4 w-4" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block font-display text-xl font-semibold tracking-tight text-ink-950 dark:text-ink-50 sm:text-2xl">
                {APP_NAME}
              </span>
              <span className="hidden text-xs text-ink-500 group-hover:text-ink-700 dark:text-ink-300 sm:block">
                {APP_TAGLINE}
              </span>
            </span>
          </Link>

          <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                aria-label={item.label}
                className={({ isActive }) =>
                  `inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-ink-900 text-white dark:bg-accent-400 dark:text-ink-950"
                      : "text-ink-700 hover:bg-ink-100/80 dark:text-ink-300 dark:hover:bg-ink-800"
                  }`
                }
              >
                <item.icon className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">{item.label}</span>
              </NavLink>
            ))}

            <span
              className={`status-pill ml-1 hidden md:inline-flex ${
                backendOk === null
                  ? "bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-200"
                  : backendOk
                    ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
                    : "bg-rose-100 text-danger-600 dark:bg-rose-950/40 dark:text-rose-200"
              }`}
              title="Backend connection"
            >
              {backendOk === null ? "Checking…" : backendOk ? "API connected" : "API offline"}
            </span>

            <button
              type="button"
              className="btn-ghost"
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" aria-hidden />
              ) : (
                <Moon className="h-4 w-4" aria-hidden />
              )}
            </button>

            {user ? (
              <>
                <span className="hidden text-sm text-ink-500 lg:inline">{user.email}</span>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={onLogout}
                  disabled={loggingOut}
                  aria-label="Log out"
                >
                  <LogOut className="h-4 w-4" aria-hidden />
                </button>
              </>
            ) : null}
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {/* Keyed by path so a crash's fallback clears on navigation instead
            of persisting after the user has already left the broken page —
            nav/header above stay live either way since they're outside this
            boundary. */}
        <ErrorBoundary key={location.pathname} scope="This page">
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}

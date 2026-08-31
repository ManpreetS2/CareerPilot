import { useEffect, useState, type MouseEvent } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Settings,
  Sun,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { CommandPalette } from "./CommandPalette";
import { ErrorBoundary } from "./ErrorBoundary";
import { Sheet, SheetContent } from "./ui/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Glass } from "./ui/glass";
import { useAuth } from "../lib/auth";
import { APP_NAME } from "../lib/config";
import { cn } from "../lib/cn";
import { shouldPromptFinishSetup } from "../lib/onboarding";
import { useTheme, type ThemePreference } from "../lib/theme";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  id: "dashboard" | "jobs" | "profile" | "resume" | "settings";
};

export const PRIMARY_NAV: NavItem[] = [
  { id: "dashboard", to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "jobs", to: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { id: "profile", to: "/profile", label: "Profile", icon: UserRound },
  { id: "resume", to: "/resume", label: "Resume", icon: FileText },
];

export const ACCOUNT_NAV: NavItem[] = [
  { id: "settings", to: "/settings", label: "Settings", icon: Settings },
];

/** @deprecated Use PRIMARY_NAV. Kept so older tests can migrate in this PR. */
export const WORKFLOW_NAV = PRIMARY_NAV;

function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.id === "dashboard") return pathname.startsWith("/dashboard");
  if (item.id === "jobs") return pathname.startsWith("/jobs") || pathname.startsWith("/analyze") || pathname.startsWith("/prepare");
  if (item.id === "resume") return pathname.startsWith("/resume");
  if (item.id === "settings") return pathname.startsWith("/settings");
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function navClass(isActive: boolean) {
  return cn(
    "relative flex min-h-11 items-center gap-2.5 rounded-[var(--radius-sm)] px-2.5 text-[14px] font-medium",
    isActive
      ? "nav-indicator text-foreground"
      : "text-muted-foreground hover:bg-[color-mix(in_srgb,var(--foreground)_6%,transparent)] hover:text-foreground",
  );
}

function NavGroup({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate?: () => void;
}) {
  const location = useLocation();
  return (
    <div className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = isNavActive(item, location.pathname);
        return (
          <NavLink
            key={item.id}
            to={item.to}
            className={navClass(active)}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden />
            {item.label}
          </NavLink>
        );
      })}
    </div>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Primary" className="flex min-h-0 flex-1 flex-col">
      <NavGroup items={PRIMARY_NAV} onNavigate={onNavigate} />
      <div className="mt-auto space-y-1 pt-6">
        <NavGroup items={ACCOUNT_NAV} onNavigate={onNavigate} />
      </div>
    </nav>
  );
}

function ThemeMenu() {
  const { preference, setPreference } = useTheme();
  const options: { id: ThemePreference; label: string; icon: LucideIcon }[] = [
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
    { id: "system", label: "System", icon: Monitor },
  ];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="btn-ghost h-11 min-h-11 w-full justify-start px-2.5 text-[14px]" aria-label="Appearance">
        {preference === "dark" ? (
          <Moon className="h-4 w-4" aria-hidden />
        ) : preference === "light" ? (
          <Sun className="h-4 w-4" aria-hidden />
        ) : (
          <Monitor className="h-4 w-4" aria-hidden />
        )}
        Appearance
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {options.map((option) => (
          <DropdownMenuItem
            key={option.id}
            onSelect={() => setPreference(option.id)}
            aria-checked={preference === option.id}
          >
            <option.icon className="mr-2 h-4 w-4" aria-hidden />
            {option.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AccountFooter() {
  const { user, logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);

  async function onLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="space-y-2 border-t border-border pt-3">
      <ThemeMenu />
      {user ? (
        <p className="truncate px-2.5 text-xs text-muted-foreground" title={user.email}>
          {user.email}
        </p>
      ) : null}
      <p className="px-2.5 text-[11px] text-muted-foreground">
        <kbd className="rounded border border-border px-1 py-0.5">Ctrl</kbd>
        {" / "}
        <kbd className="rounded border border-border px-1 py-0.5">⌘</kbd> K
      </p>
      <button
        type="button"
        className="btn-ghost h-11 min-h-11 w-full justify-start px-2.5 text-[14px]"
        onClick={() => void onLogout()}
        disabled={loggingOut}
        aria-label="Log out"
      >
        <LogOut className="h-4 w-4" aria-hidden />
        Log out
      </button>
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const wide =
    location.pathname.startsWith("/jobs") ||
    location.pathname.startsWith("/resume") ||
    location.pathname.startsWith("/track") ||
    location.pathname.startsWith("/applications");
  const showFinish = user ? shouldPromptFinishSetup(user.id) : false;

  useEffect(() => {
    window.scrollTo?.(0, 0);
    const main = document.getElementById("main");
    if (main && typeof main.scrollTo === "function") {
      main.scrollTo(0, 0);
    }
  }, [location.pathname]);

  function focusMain(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    document.getElementById("main")?.focus();
  }

  return (
    <div className="app-canvas min-h-screen bg-background" data-testid="app-shell">
      <a href="#main" className="skip-link" data-testid="skip-to-content" onClick={focusMain}>
        Skip to content
      </a>
      <CommandPalette />

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 p-3 lg:flex" data-testid="app-sidebar">
        <Glass variant="panel" className="flex h-full min-h-0 w-full flex-col overflow-y-auto rounded-[var(--radius-lg)] p-3">
          <Link to="/dashboard" className="mb-6 flex items-center gap-2.5 px-1.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] bg-primary text-[11px] font-semibold text-primary-foreground">
              CP
            </span>
            <span className="font-display text-[15px] font-semibold">{APP_NAME}</span>
          </Link>
          <NavLinks />
          <AccountFooter />
        </Glass>
      </aside>

      <header className="safe-pad sticky top-0 z-40 flex items-center gap-3 px-3 py-2 lg:hidden">
        <Glass variant="panel" className="flex w-full items-center gap-3 rounded-[var(--radius-md)] px-2 py-1">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <button
              type="button"
              className="btn-ghost h-11 w-11 min-h-11 px-0"
              aria-label="Open menu"
              data-testid="mobile-nav-trigger"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <SheetContent title="CareerPilot" side="left">
              <div className="flex h-full flex-col" data-testid="mobile-nav">
                <NavLinks onNavigate={() => setMobileOpen(false)} />
                <AccountFooter />
              </div>
            </SheetContent>
          </Sheet>
          <Link to="/dashboard" className="font-display text-base font-semibold">
            {APP_NAME}
          </Link>
        </Glass>
      </header>

      <main
        id="main"
        tabIndex={-1}
        className={cn(
          "relative z-[1] px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-8 outline-none sm:px-6 lg:ml-56 lg:pt-10",
          "safe-pad",
          wide ? "max-w-none" : "",
        )}
      >
        <div className={cn("min-w-0", wide ? "mx-auto max-w-[1360px]" : "mx-auto max-w-5xl")}>
          {showFinish ? (
            <div className="solid-surface mb-4 rounded-[var(--radius-md)] px-4 py-3 text-sm">
              Setup is unfinished.{" "}
              <Link to="/onboarding" className="font-semibold text-foreground underline-offset-2 hover:underline">
                Finish setup
              </Link>
            </div>
          ) : null}
          <ErrorBoundary key={location.pathname} scope="This page">
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}

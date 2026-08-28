import { useEffect, useState, type MouseEvent } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import {
  BriefcaseBusiness,
  FileSearch,
  FileText,
  Kanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  Moon,
  PenLine,
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
import { getSelectedJobId } from "../lib/session";
import { useTheme, type ThemePreference } from "../lib/theme";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  id: "overview" | "discover" | "analyze" | "prepare" | "track" | "profile" | "resume" | "settings";
};

export const WORKFLOW_NAV: NavItem[] = [
  { id: "overview", to: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { id: "discover", to: "/jobs", label: "Discover", icon: BriefcaseBusiness },
  { id: "analyze", to: "/analyze", label: "Analyze", icon: FileSearch },
  { id: "prepare", to: "/prepare", label: "Prepare", icon: PenLine },
  { id: "track", to: "/track", label: "Track", icon: Kanban },
];

export const SUPPORTING_NAV: NavItem[] = [
  { id: "profile", to: "/profile", label: "Profile", icon: UserRound },
  { id: "resume", to: "/resume", label: "Resume", icon: FileText },
  { id: "settings", to: "/settings", label: "Settings", icon: Settings },
];

export const PRIMARY_NAV: NavItem[] = [...WORKFLOW_NAV, ...SUPPORTING_NAV];

function resolveNavTo(item: NavItem): string {
  if (item.id === "analyze") {
    const jobId = getSelectedJobId();
    return jobId ? `/jobs/${jobId}` : "/analyze";
  }
  if (item.id === "prepare") {
    const jobId = getSelectedJobId();
    return jobId ? `/jobs/${jobId}/prepare` : "/prepare";
  }
  return item.to;
}

function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.id === "overview") return pathname.startsWith("/dashboard");
  if (item.id === "discover") return pathname === "/jobs";
  if (item.id === "analyze") return /^\/jobs\/[^/]+$/.test(pathname) || pathname === "/analyze";
  if (item.id === "prepare") return /\/jobs\/[^/]+\/prepare/.test(pathname) || pathname === "/prepare";
  if (item.id === "track") return pathname.startsWith("/track") || pathname.startsWith("/applications");
  if (item.id === "resume") return pathname.startsWith("/resume");
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function navClass(isActive: boolean) {
  return cn(
    "relative flex min-h-10 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium",
    isActive
      ? "nav-indicator bg-primary/[0.09] text-foreground"
      : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
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
  const { reducedMotion } = useTheme();
  return (
    <div className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = isNavActive(item, location.pathname);
        return (
          <NavLink
            key={item.id}
            to={resolveNavTo(item)}
            className={navClass(active)}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
          >
            {active && !reducedMotion ? (
              <motion.span
                layoutId="nav-active"
                className="absolute inset-0 -z-10 rounded-md bg-primary/[0.1]"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : null}
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
    <nav aria-label="Primary" className="flex flex-col gap-4">
      <NavGroup items={WORKFLOW_NAV} onNavigate={onNavigate} />
      <div>
        <p className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Account
        </p>
        <NavGroup items={SUPPORTING_NAV} onNavigate={onNavigate} />
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
      <DropdownMenuTrigger className="btn-ghost h-10 min-h-10 w-full justify-start px-2.5 text-[13px]" aria-label="Appearance">
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
    <div className="mt-auto space-y-2 border-t border-border/80 pt-3">
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
        className="btn-ghost h-10 min-h-10 w-full justify-start px-2.5 text-[13px]"
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
  const { reducedMotion } = useTheme();

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
        <Glass variant="atmosphere" className="flex h-full w-full flex-col rounded-[1.25rem] p-3">
          <Link to="/dashboard" className="mb-5 flex items-center gap-2 px-1.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-primary to-accent text-[11px] font-semibold text-primary-foreground">
              CP
            </span>
            <span className="font-display text-[15px] font-semibold tracking-tight">{APP_NAME}</span>
          </Link>
          <NavLinks />
          <AccountFooter />
        </Glass>
      </aside>

      <header className="safe-pad sticky top-0 z-40 flex items-center gap-3 px-3 py-2 lg:hidden">
        <Glass variant="atmosphere" className="flex w-full items-center gap-3 rounded-[var(--radius-md)] px-2 py-1">
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
            <SheetContent title="CareerPilot" side="left" className="glass-floating">
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
        <div className={cn("min-w-0", wide ? "mx-auto max-w-7xl" : "mx-auto max-w-5xl")}>
          {showFinish ? (
            <div className="glass-working mb-4 rounded-[var(--radius-md)] px-4 py-3 text-sm">
              Setup is unfinished.{" "}
              <Link to="/onboarding" className="font-semibold text-primary">
                Finish setup
              </Link>
            </div>
          ) : null}
          <ErrorBoundary key={location.pathname} scope="This page">
            <motion.div
              key={location.pathname}
              initial={reducedMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reducedMotion ? 0 : 0.2 }}
            >
              <Outlet />
            </motion.div>
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}

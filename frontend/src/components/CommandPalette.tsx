import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileSearch,
  FileText,
  Kanban,
  LayoutDashboard,
  PenLine,
  Search,
  Settings,
  Upload,
  UserRound,
} from "lucide-react";
import { Dialog } from "./ui/dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "../lib/cn";
import { useAuth } from "../lib/auth";
import { shouldPromptFinishSetup } from "../lib/onboarding";

type Command = {
  id: string;
  label: string;
  hint: string;
  to: string;
  icon: typeof LayoutDashboard;
};

const BASE_COMMANDS: Command[] = [
  { id: "overview", label: "Overview", hint: "Next action and stored signals", to: "/dashboard", icon: LayoutDashboard },
  { id: "discover", label: "Discover", hint: "Find and triage roles", to: "/jobs", icon: BriefcaseBusiness },
  { id: "analyze", label: "Analyze", hint: "Job evidence and fit", to: "/analyze", icon: FileSearch },
  { id: "prepare", label: "Prepare", hint: "Grounded application workspace", to: "/prepare", icon: PenLine },
  { id: "track", label: "Track", hint: "Pipeline Kanban and list", to: "/track", icon: Kanban },
  { id: "profile", label: "Upload Resume", hint: "Profile workspace", to: "/profile", icon: Upload },
  { id: "resume", label: "Resume", hint: "Immutable version library", to: "/resume", icon: FileText },
  { id: "settings", label: "Settings", hint: "Appearance and privacy", to: "/settings", icon: Settings },
  { id: "profile-nav", label: "Profile", hint: "Grounded candidate record", to: "/profile", icon: UserRound },
];

export function CommandPalette() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const commands = useMemo(() => {
    const extra: Command[] =
      user && shouldPromptFinishSetup(user.id)
        ? [
            {
              id: "onboarding",
              label: "Finish setup",
              hint: "Continue onboarding",
              to: "/onboarding",
              icon: Search,
            },
          ]
        : [];
    const all = [...BASE_COMMANDS, ...extra];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter((item) => item.label.toLowerCase().includes(q) || item.hint.toLowerCase().includes(q));
  }, [query, user]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  function run(command: Command) {
    setOpen(false);
    setQuery("");
    navigate(command.to);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="command-tunnel fixed inset-0 z-[60]" />
        <DialogPrimitive.Content
          aria-label="Command palette"
          data-testid="command-palette"
          className="glass-floating glass-refract fixed left-1/2 top-[18%] z-[60] w-[min(36rem,calc(100%-2rem))] -translate-x-1/2 rounded-[var(--radius-lg)] border border-border p-2 shadow-floating"
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((value) => Math.min(value + 1, Math.max(commands.length - 1, 0)));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((value) => Math.max(value - 1, 0));
            }
            if (event.key === "Enter" && commands[active]) {
              event.preventDefault();
              run(commands[active]);
            }
          }}
        >
          <DialogPrimitive.Title className="sr-only">Jump to</DialogPrimitive.Title>
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Jump to a destination"
              className="h-10 w-full bg-transparent text-sm outline-none"
              aria-label="Filter commands"
            />
            <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">
              Esc
            </kbd>
          </div>
          <ul className="max-h-72 overflow-auto py-1" role="listbox">
            {commands.length === 0 ? (
              <li className="px-3 py-3 text-sm text-muted-foreground">No matching destinations.</li>
            ) : (
              commands.map((command, index) => (
                <li key={command.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === active}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-[var(--radius-sm)] px-3 py-2.5 text-left text-sm",
                      index === active ? "bg-primary/10" : "hover:bg-muted",
                    )}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => run(command)}
                  >
                    <command.icon className="h-4 w-4 text-muted-foreground" aria-hidden />
                    <span className="font-medium">{command.label}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{command.hint}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </Dialog>
  );
}

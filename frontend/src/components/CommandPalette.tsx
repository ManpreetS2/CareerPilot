import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BriefcaseBusiness,
  FileText,
  LayoutDashboard,
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
  { id: "dashboard", label: "Dashboard", hint: "What to do next", to: "/dashboard", icon: LayoutDashboard },
  { id: "jobs", label: "Jobs", hint: "Find and review roles", to: "/jobs", icon: BriefcaseBusiness },
  { id: "profile", label: "Profile", hint: "Grounded candidate record", to: "/profile", icon: UserRound },
  { id: "resume", label: "Resume", hint: "Version library", to: "/resume", icon: FileText },
  { id: "settings", label: "Settings", hint: "Appearance and privacy", to: "/settings", icon: Settings },
  { id: "profile-upload", label: "Upload Resume", hint: "Profile workspace", to: "/profile", icon: Upload },
];

export function CommandPalette() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

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
      <DialogPrimitive.Portal container={typeof document !== "undefined" ? document.body : undefined}>
        <DialogPrimitive.Overlay className="command-tunnel" />
        <DialogPrimitive.Content
          aria-label="Command palette"
          data-testid="command-palette"
          className="command-palette glass-floating fixed rounded-[var(--radius-lg)] p-2"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
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
              ref={inputRef}
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
                      index === active ? "bg-[color-mix(in_srgb,var(--foreground)_8%,transparent)]" : "hover:bg-muted",
                    )}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => run(command)}
                  >
                    <command.icon className="h-4 w-4 text-muted-foreground" aria-hidden />
                    <span className="font-medium">{command.label}</span>
                    <span className="ml-auto hidden min-w-0 truncate text-xs text-muted-foreground sm:inline">{command.hint}</span>
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

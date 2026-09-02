import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Monitor, Moon, Sun } from "lucide-react";
import { ErrorBanner } from "../components/ErrorBanner";
import { Dialog, DialogContent } from "../components/ui/dialog";
import { PageHeader } from "../components/ui/page-header";
import { Surface } from "../components/ui/surface";
import { Switch } from "../components/ui/switch";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { queryKeys } from "../lib/query-keys";
import { useTheme, type ThemePreference } from "../lib/theme";

const THEMES: { id: ThemePreference; label: string; icon: typeof Sun }[] = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
];

export function SettingsPage() {
  const { user, deleteAccount } = useAuth();
  const navigate = useNavigate();
  const { preference, setPreference, appReducedMotion, setReducedMotion } = useTheme();
  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health({ signal }),
    retry: false,
  });
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);

  async function onConfirmDelete() {
    if (confirmation !== "DELETE") return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
      setDeleteOpen(false);
      navigate("/", { replace: true });
    } catch (err) {
      setDeleteError(err);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Appearance, account, privacy, and accessibility." />

      <Surface className="space-y-3 p-6">
        <h2 className="font-display text-xl font-semibold">Account</h2>
        {user ? (
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd className="wrap-anywhere font-medium">{user.email}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Signed in since</dt>
              <dd className="tabular">{new Date(user.created_at).toLocaleDateString()}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-muted-foreground">No account session.</p>
        )}
      </Surface>

      <Surface className="space-y-4 p-6">
        <h2 className="font-display text-xl font-semibold">Appearance</h2>
        <div className="grid gap-2 sm:grid-cols-3">
          {THEMES.map((theme) => (
            <button
              key={theme.id}
              type="button"
              className={`btn-secondary justify-start min-h-11 ${preference === theme.id ? "ring-2 ring-[var(--ring)]" : ""}`}
              aria-pressed={preference === theme.id}
              onClick={() => setPreference(theme.id)}
            >
              <theme.icon className="h-4 w-4" aria-hidden />
              {theme.label}
            </button>
          ))}
        </div>
      </Surface>

      <Surface className="space-y-3 p-6">
        <h2 className="font-display text-xl font-semibold">Privacy & Safety</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
          <li>Resumes are private to the signed-in user.</li>
          <li>Generated materials stay grounded in stored candidate evidence.</li>
          <li>Human approval is required before assisted apply unlocks.</li>
          <li>CareerPilot never automatically submits an application.</li>
        </ul>
        <p className="text-sm">
          <Link to="/privacy" className="font-semibold text-primary">
            Read the privacy page
          </Link>
        </p>
        <div className="border-t border-border pt-4">
          <h3 className="text-sm font-semibold text-danger">Delete account and data</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Permanently deletes your account, private records, and every sign-in session on this
            machine&apos;s database. Shared job listings are kept. This cannot be undone.
          </p>
          <button
            type="button"
            className="btn-secondary mt-3 min-h-11 border-danger/40 text-danger"
            onClick={() => {
              setConfirmation("");
              setDeleteError(null);
              setDeleteOpen(true);
            }}
          >
            Delete account and data
          </button>
        </div>
      </Surface>

      <Dialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (deleting) return;
          setDeleteOpen(open);
        }}
      >
        <DialogContent title="Delete account and data?">
          <p className="text-sm text-muted-foreground">
            Type <span className="font-mono font-semibold text-foreground">DELETE</span> to confirm.
            CareerPilot will remove your private data and revoke every session. You will be signed
            out.
          </p>
          <ErrorBanner error={deleteError} heading="Couldn't delete the account" />
          <label className="mt-4 block">
            <span className="label">Confirmation</span>
            <input
              className="input"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              aria-label="Type DELETE to confirm account deletion"
            />
          </label>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary min-h-11 bg-danger text-danger-foreground"
              disabled={confirmation !== "DELETE" || deleting}
              onClick={() => void onConfirmDelete()}
            >
              {deleting ? "Deleting…" : "Delete permanently"}
            </button>
            <button
              type="button"
              className="btn-secondary min-h-11"
              disabled={deleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </button>
          </div>
        </DialogContent>
      </Dialog>

      <Surface className="space-y-4 p-6">
        <h2 className="font-display text-xl font-semibold">Accessibility</h2>
        <label className="flex min-h-11 items-center justify-between gap-4 text-sm">
          <span>Reduce motion (also follows the operating system)</span>
          <Switch
            checked={appReducedMotion}
            onCheckedChange={setReducedMotion}
            aria-label="Reduce motion"
          />
        </label>
        <p className="text-sm text-muted-foreground">
          Focus remains visible, overlays close with Escape, and primary controls stay keyboard
          reachable. Reduced motion removes path drawing, pointer refraction, and score assembly.
        </p>
      </Surface>

      <Surface className="space-y-2 p-6">
        <h2 className="font-display text-xl font-semibold">Backend</h2>
        {healthQuery.isError ? (
          <p className="text-sm text-danger">API unreachable.</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Status: {healthQuery.data?.status ?? "checking…"} · Database:{" "}
            {healthQuery.data?.database ?? "—"}
          </p>
        )}
      </Surface>
    </div>
  );
}

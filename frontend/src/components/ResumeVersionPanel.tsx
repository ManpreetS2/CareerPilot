import { useCallback, useEffect, useState } from "react";
import { BookmarkPlus } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";
import { api, ApiClientError } from "../lib/api";
import type { ApplicationPackage, ResumeVersion } from "../lib/types";

function formatCreatedAt(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function ResumeVersionPanel({
  jobId,
  materials,
}: {
  jobId: string;
  materials: ApplicationPackage;
}) {
  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  const loadVersions = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConflict(null);
    try {
      setVersions(await api.listResumeVersions(jobId));
    } catch (err) {
      setError(err);
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  async function saveVersion() {
    if (saving || materials.approval_status !== "approved") return;
    setSaving(true);
    setError(null);
    setConflict(null);
    try {
      await api.createResumeVersion(jobId);
      await loadVersions();
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 409) {
        setConflict(err.message);
      } else {
        setError(err);
      }
    } finally {
      setSaving(false);
    }
  }

  const canSave = materials.approval_status === "approved" && !saving;

  return (
    <section
      className="card space-y-4 p-6"
      aria-labelledby="resume-versions-heading"
      aria-busy={loading || saving}
      data-testid="resume-version-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="resume-versions-heading" className="font-display text-2xl font-semibold">
            Resume versions
          </h2>
          <p className="mt-2 text-sm text-ink-600 dark:text-ink-300">
            Versions are immutable snapshots of tailored resume bullets. Saving a
            version does not generate new materials. A later export step can turn a
            selected version into PDF or DOCX; nothing is uploaded automatically.
          </p>
        </div>
        {materials.approval_status === "approved" ? (
          <button
            type="button"
            className="btn-primary"
            data-testid="save-resume-version"
            disabled={!canSave}
            aria-disabled={!canSave}
            onClick={() => void saveVersion()}
          >
            <BookmarkPlus className={`h-4 w-4 ${saving ? "animate-pulse" : ""}`} aria-hidden />
            {saving ? "Saving…" : "Save resume version"}
          </button>
        ) : (
          <p className="text-sm text-ink-500">Pass review on this package to save a resume version.</p>
        )}
      </div>

      <ErrorBanner error={error} />
      {conflict ? (
        <div role="alert" className="card border-accent-300/60 bg-accent-50/70 p-4 text-sm text-accent-900 dark:border-accent-800 dark:bg-accent-950/30 dark:text-accent-100">
          {conflict}
        </div>
      ) : null}

      {loading ? (
        <LoadingState label="Loading resume versions…" />
      ) : versions.length === 0 ? (
        <p className="text-sm text-ink-500" data-testid="resume-versions-empty">
          No resume versions saved yet.
        </p>
      ) : (
        <ol className="space-y-3" aria-label="Saved resume versions">
          {versions.map((version) => (
            <li
              key={version.id}
              className="rounded-xl border border-[var(--line)] p-4"
              data-testid={`resume-version-${version.version_number}`}
            >
              <p className="text-sm font-semibold">
                Version {version.version_number}
                <span className="ml-2 font-normal text-ink-500">
                  {formatCreatedAt(version.created_at)}
                </span>
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-700 dark:text-ink-200">
                {version.tailored_bullets.map((bullet, index) => (
                  <li key={`${version.id}:${index}`}>{bullet}</li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

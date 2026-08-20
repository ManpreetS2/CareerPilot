import { useMemo, useState, type DragEvent, type FormEvent } from "react";
import { FileUp, Upload } from "lucide-react";
import { CandidateSummary } from "../components/CandidateSummary";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { api } from "../lib/api";
import { useCandidateSession } from "../lib/session";
import type { TargetPreferences } from "../lib/types";

export function ProfilePage() {
  const { candidate, preferences, setSession } = useCandidateSession();
  const [file, setFile] = useState<File | null>(null);
  const [targetRoles, setTargetRoles] = useState(
    preferences?.target_roles?.join(", ") || "Software Engineer Intern, Backend Engineer Intern",
  );
  const [location, setLocation] = useState(preferences?.preferred_locations?.[0] || "San Francisco, CA");
  const [salaryMin, setSalaryMin] = useState(String(preferences?.salary_min ?? 35));
  const [workAuth, setWorkAuth] = useState(preferences?.work_authorization || "US Citizen");
  const [remotePreference, setRemotePreference] = useState(
    preferences?.remote_preference || "hybrid_or_remote",
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [dragActive, setDragActive] = useState(false);

  const canSubmit = useMemo(() => Boolean(file) && !loading, [file, loading]);

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    const next = event.dataTransfer.files?.[0];
    if (next && next.type === "application/pdf") setFile(next);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const parsed = await api.parseResume(file);
      const nextPreferences: TargetPreferences = {
        target_roles: targetRoles
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        preferred_locations: location ? [location] : [],
        remote_preference: remotePreference,
        salary_min: Number(salaryMin) || null,
        work_authorization: workAuth,
        sponsorship_required: workAuth === "Requires sponsorship",
        constraints: [],
      };
      const saved = await api.savePreferences(nextPreferences);
      setSession(parsed.candidate, saved);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-4xl font-semibold">Profile</h1>
        <p className="mt-2 max-w-2xl text-ink-600 dark:text-ink-300">
          Upload a resume and set preferences. The UI is ready for real CandidateProfile payloads;
          today the API may still return mock data until Developer A wires the profile agent.
        </p>
      </div>

      <ErrorBanner error={error} />

      <form onSubmit={onSubmit} className="card space-y-5 p-6">
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-10 text-center transition ${
            dragActive
              ? "border-accent-500 bg-accent-50/70 dark:bg-accent-950/20"
              : "border-[var(--line)] bg-sand-50/60 dark:bg-ink-950/40"
          }`}
        >
          <FileUp className="h-8 w-8 text-accent-700 dark:text-accent-300" aria-hidden />
          <span className="mt-3 font-semibold">Drag & drop a resume PDF</span>
          <span className="mt-1 text-sm text-ink-500">or click to choose a file</span>
          <span className="mt-3 text-xs text-ink-500">
            {file ? file.name : "PDF only · parsing agent arrives on Day 2"}
          </span>
          <input
            type="file"
            accept="application/pdf"
            className="sr-only"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>

        <div className="grid gap-4 md:grid-cols-2">
          <label>
            <span className="label">Target roles</span>
            <input
              className="input"
              value={targetRoles}
              onChange={(event) => setTargetRoles(event.target.value)}
              placeholder="Comma-separated roles"
            />
          </label>
          <label>
            <span className="label">Preferred location</span>
            <input
              className="input"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
            />
          </label>
          <label>
            <span className="label">Salary minimum (hourly USD)</span>
            <input
              className="input"
              type="number"
              min={0}
              value={salaryMin}
              onChange={(event) => setSalaryMin(event.target.value)}
            />
          </label>
          <label>
            <span className="label">Work authorization</span>
            <select
              className="input"
              value={workAuth}
              onChange={(event) => setWorkAuth(event.target.value)}
            >
              <option>US Citizen</option>
              <option>US Permanent Resident</option>
              <option>Requires sponsorship</option>
              <option>Other</option>
            </select>
          </label>
          <label className="md:col-span-2">
            <span className="label">Remote preference</span>
            <select
              className="input"
              value={remotePreference}
              onChange={(event) => setRemotePreference(event.target.value)}
            >
              <option value="remote">Remote</option>
              <option value="hybrid_or_remote">Hybrid or remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">Onsite</option>
            </select>
          </label>
        </div>

        <button type="submit" className="btn-primary" disabled={!canSubmit}>
          <Upload className="h-4 w-4" aria-hidden />
          {loading ? "Building profile…" : "Build candidate profile"}
        </button>
      </form>

      {loading ? <LoadingState label="Calling /api/parse-resume…" /> : null}

      {candidate ? (
        <CandidateSummary candidate={candidate} preferences={preferences} />
      ) : (
        !loading && (
          <p className="text-sm text-ink-500">
            No profile yet. Upload a PDF to load candidate data from the backend.
          </p>
        )
      )}
    </div>
  );
}

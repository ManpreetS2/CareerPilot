import { useMemo, useState, type DragEvent, type FormEvent } from "react";
import { FileUp, Save, Upload } from "lucide-react";
import { CandidateSummary } from "../components/CandidateSummary";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { api } from "../lib/api";
import {
  isLegacyHourlySalary,
  useCandidateSession,
} from "../lib/session";
import type { TargetPreferences } from "../lib/types";

const MAX_CLIENT_UPLOAD_BYTES = 10 * 1024 * 1024;
const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function sponsorshipFromWorkAuth(workAuth: string): boolean | null {
  if (workAuth === "Requires sponsorship") return true;

  if (
    workAuth === "US Citizen" ||
    workAuth === "US Permanent Resident"
  ) {
    return false;
  }

  return null;
}

export function ProfilePage() {
  const { candidate, preferences, setCandidateProfile, setJobPreferences } =
    useCandidateSession();

  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<unknown>(null);

  const [targetRoles, setTargetRoles] = useState(preferences?.target_roles?.join(", ") || "");
  const [location, setLocation] = useState(preferences?.preferred_locations?.[0] || "");
  const [salaryMin, setSalaryMin] = useState(() => {
    if (preferences?.salary_min == null) return "";
    if (isLegacyHourlySalary(preferences.salary_min)) return "";
    return String(preferences.salary_min);
  });
  const [workAuth, setWorkAuth] = useState(preferences?.work_authorization || "");
  const [remotePreference, setRemotePreference] = useState(
    preferences?.remote_preference || "",
  );
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsError, setPrefsError] = useState<unknown>(null);
  const [prefsSuccess, setPrefsSuccess] = useState<string | null>(null);

  const canBuildProfile = useMemo(
    () => Boolean(file) && !profileLoading,
    [file, profileLoading],
  );

  const salaryPreview = useMemo(() => {
    const value = Number(salaryMin);
    if (!salaryMin || Number.isNaN(value) || value < 10000) return null;
    return `${currency.format(value)}/year`;
  }, [salaryMin]);

  function selectFile(next: File | null) {
    setProfileError(null);
    if (!next) {
      setFile(null);
      return;
    }
    const looksPdf =
      next.type === "application/pdf" || next.name.toLowerCase().endsWith(".pdf");
    if (!looksPdf) {
      setFile(null);
      setProfileError(new Error("Please choose a valid PDF file."));
      return;
    }
    if (next.size > MAX_CLIENT_UPLOAD_BYTES) {
      setFile(null);
      setProfileError(new Error("Resume PDFs must be 10 MiB or smaller."));
      return;
    }
    setFile(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function onBuildProfile(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setProfileLoading(true);
    setProfileError(null);
    try {
      const parsed = await api.parseResume(file);
      setCandidateProfile(parsed.candidate);
    } catch (err) {
      setProfileError(err);
    } finally {
      setProfileLoading(false);
    }
  }

  async function onSavePreferences(event: FormEvent) {
    event.preventDefault();
    setPrefsLoading(true);
    setPrefsError(null);
    setPrefsSuccess(null);
    try {
      const roles = targetRoles
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      if (roles.length === 0) {
        throw new Error("Enter at least one target role before saving preferences.");
      }

      let annualSalary: number | null = null;
      if (salaryMin.trim()) {
        annualSalary = Number(salaryMin);
        if (
          Number.isNaN(annualSalary) ||
          annualSalary < 10000 ||
          annualSalary > 1000000
        ) {
          throw new Error(
            "Minimum base salary must be an annual USD amount between 10,000 and 1,000,000.",
          );
        }
      }

      const payload: TargetPreferences = {
        target_roles: roles,
        preferred_locations: location.trim() ? [location.trim()] : [],
        remote_preference: remotePreference || null,
        salary_min: annualSalary,
        work_authorization: workAuth || null,
        sponsorship_required: sponsorshipFromWorkAuth(workAuth),
        constraints: [],
      };
      const saved = await api.savePreferences(payload);
      setJobPreferences(saved);
      setPrefsSuccess("Job preferences saved.");
    } catch (err) {
      setPrefsError(err);
    } finally {
      setPrefsLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-4xl font-semibold">Profile</h1>
        <p className="mt-2 max-w-2xl text-ink-600 dark:text-ink-300">
          Upload your resume to build a structured candidate profile. Job preferences are saved
          separately and are never invented from the PDF.
        </p>
      </div>

      <section className="card space-y-5 p-6">
        <div>
          <h2 className="font-display text-2xl font-semibold">Candidate profile</h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
            This action only calls resume parsing. It does not save job preferences.
          </p>
        </div>

        <ErrorBanner error={profileError} />

        <form onSubmit={onBuildProfile} className="space-y-5">
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
              {file ? file.name : "PDF only · max 10 MiB"}
            </span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="sr-only"
              onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <button type="submit" className="btn-primary" disabled={!canBuildProfile}>
            <Upload className="h-4 w-4" aria-hidden />
            {profileLoading ? "Building profile…" : "Build candidate profile"}
          </button>
        </form>

        {profileLoading ? (
          <LoadingState label="Extracting and grounding your resume…" />
        ) : null}

        {candidate ? (
          <CandidateSummary candidate={candidate} preferences={preferences} />
        ) : (
          !profileLoading && (
            <p className="text-sm text-ink-500">
              No profile yet. Upload a PDF to extract a grounded candidate profile.
            </p>
          )
        )}
      </section>

      <section className="card space-y-5 p-6">
        <div>
          <h2 className="font-display text-2xl font-semibold">Job preferences</h2>
          <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
            Saved independently from resume parsing. Leave legal fields unanswered until you choose
            deliberately.
          </p>
        </div>

        <ErrorBanner error={prefsError} />
        {prefsSuccess ? (
          <div className="card border-accent-300/60 bg-accent-50/70 p-4 text-sm text-accent-900 dark:border-accent-800 dark:bg-accent-950/30 dark:text-accent-100">
            {prefsSuccess}
          </div>
        ) : null}

        <form onSubmit={onSavePreferences} className="space-y-4">
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
                placeholder="City, state, or Remote"
              />
            </label>
            <label>
              <span className="label">Minimum base salary (annual USD)</span>
              <input
                className="input"
                type="number"
                min={10000}
                max={1000000}
                step={5000}
                value={salaryMin}
                onChange={(event) => setSalaryMin(event.target.value)}
                placeholder="e.g. 100000"
              />
              {salaryPreview ? (
                <span className="mt-1 block text-xs text-ink-500">{salaryPreview}</span>
              ) : (
                <span className="mt-1 block text-xs text-ink-500">
                  Enter an annual amount (for example 100000). Hourly prototype values are ignored.
                </span>
              )}
            </label>
            <label>
              <span className="label">Work authorization</span>
              <select
                className="input"
                value={workAuth}
                onChange={(event) => setWorkAuth(event.target.value)}
              >
                <option value="">Select work authorization…</option>
                <option value="US Citizen">US Citizen</option>
                <option value="US Permanent Resident">US Permanent Resident</option>
                <option value="Requires sponsorship">Requires sponsorship</option>
                <option value="Other">Other</option>
              </select>
            </label>
            <label className="md:col-span-2">
              <span className="label">Remote preference</span>
              <select
                className="input"
                value={remotePreference}
                onChange={(event) => setRemotePreference(event.target.value)}
              >
                <option value="">No preference selected…</option>
                <option value="remote">Remote</option>
                <option value="hybrid_or_remote">Hybrid or remote</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">Onsite</option>
              </select>
            </label>
          </div>

          <button type="submit" className="btn-secondary" disabled={prefsLoading}>
            <Save className="h-4 w-4" aria-hidden />
            {prefsLoading ? "Saving…" : "Save job preferences"}
          </button>
        </form>
      </section>
    </div>
  );
}

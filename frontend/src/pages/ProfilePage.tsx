import { useEffect, useMemo, useState, type DragEvent, type FormEvent } from "react";
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
  const [legalName, setLegalName] = useState(preferences?.legal_name || "");
  const [linkedinUrl, setLinkedinUrl] = useState(preferences?.linkedin_url || "");
  const [githubUrl, setGithubUrl] = useState(preferences?.github_url || "");
  const [portfolioUrl, setPortfolioUrl] = useState(preferences?.portfolio_url || "");
  const [earliestStartDate, setEarliestStartDate] = useState(preferences?.earliest_start_date || "");
  const [currentlyEnrolled, setCurrentlyEnrolled] = useState(
    preferences?.currently_enrolled_in_program || "",
  );
  const [expectedGraduation, setExpectedGraduation] = useState(preferences?.expected_graduation || "");
  const [degreePursuing, setDegreePursuing] = useState(preferences?.degree_pursuing || "");
  const [gender, setGender] = useState(preferences?.gender || "");
  const [raceEthnicity, setRaceEthnicity] = useState(preferences?.race_ethnicity || "");
  const [veteranStatus, setVeteranStatus] = useState(preferences?.veteran_status || "");
  const [disabilityStatus, setDisabilityStatus] = useState(preferences?.disability_status || "");
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsError, setPrefsError] = useState<unknown>(null);
  const [prefsSuccess, setPrefsSuccess] = useState<string | null>(null);

  useEffect(() => {
    setTargetRoles(preferences?.target_roles?.join(", ") || "");
    setLocation(preferences?.preferred_locations?.[0] || "");
    setSalaryMin(
      preferences?.salary_min == null || isLegacyHourlySalary(preferences.salary_min)
        ? ""
        : String(preferences.salary_min),
    );
    setWorkAuth(preferences?.work_authorization || "");
    setRemotePreference(preferences?.remote_preference || "");
    setLegalName(preferences?.legal_name || "");
    setLinkedinUrl(preferences?.linkedin_url || "");
    setGithubUrl(preferences?.github_url || "");
    setPortfolioUrl(preferences?.portfolio_url || "");
    setEarliestStartDate(preferences?.earliest_start_date || "");
    setCurrentlyEnrolled(preferences?.currently_enrolled_in_program || "");
    setExpectedGraduation(preferences?.expected_graduation || "");
    setDegreePursuing(preferences?.degree_pursuing || "");
    setGender(preferences?.gender || "");
    setRaceEthnicity(preferences?.race_ethnicity || "");
    setVeteranStatus(preferences?.veteran_status || "");
    setDisabilityStatus(preferences?.disability_status || "");
  }, [preferences]);

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
        legal_name: legalName.trim() || null,
        linkedin_url: linkedinUrl.trim() || null,
        github_url: githubUrl.trim() || null,
        portfolio_url: portfolioUrl.trim() || null,
        earliest_start_date: earliestStartDate.trim() || null,
        currently_enrolled_in_program: currentlyEnrolled || null,
        expected_graduation: expectedGraduation.trim() || null,
        degree_pursuing: degreePursuing.trim() || null,
        gender: gender || null,
        race_ethnicity: raceEthnicity || null,
        veteran_status: veteranStatus || null,
        disability_status: disabilityStatus || null,
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
            <label>
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
            <label>
              <span className="label">Legal name (if different)</span>
              <input
                className="input"
                value={legalName}
                onChange={(event) => setLegalName(event.target.value)}
                placeholder="Only if it differs from your resume name"
              />
            </label>
            <label>
              <span className="label">LinkedIn URL</span>
              <input
                className="input"
                value={linkedinUrl}
                onChange={(event) => setLinkedinUrl(event.target.value)}
                placeholder="https://linkedin.com/in/…"
              />
            </label>
            <label>
              <span className="label">GitHub URL</span>
              <input
                className="input"
                value={githubUrl}
                onChange={(event) => setGithubUrl(event.target.value)}
                placeholder="https://github.com/…"
              />
            </label>
            <label>
              <span className="label">Portfolio / website URL</span>
              <input
                className="input"
                value={portfolioUrl}
                onChange={(event) => setPortfolioUrl(event.target.value)}
                placeholder="https://…"
              />
            </label>
            <label>
              <span className="label">Earliest start date</span>
              <input
                className="input"
                value={earliestStartDate}
                onChange={(event) => setEarliestStartDate(event.target.value)}
                placeholder="e.g. Immediately, or May 2027"
              />
            </label>
            <label>
              <span className="label">Currently enrolled in a program?</span>
              <select
                className="input"
                value={currentlyEnrolled}
                onChange={(event) => setCurrentlyEnrolled(event.target.value)}
              >
                <option value="">Select…</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
              </select>
            </label>
            <label>
              <span className="label">Expected graduation</span>
              <input
                className="input"
                value={expectedGraduation}
                onChange={(event) => setExpectedGraduation(event.target.value)}
                placeholder="e.g. May 2027"
              />
            </label>
            <label>
              <span className="label">Degree currently pursuing</span>
              <input
                className="input"
                value={degreePursuing}
                onChange={(event) => setDegreePursuing(event.target.value)}
                placeholder="e.g. Bachelor's in Computer Science"
              />
            </label>
          </div>

          <div className="border-t border-[var(--line)] pt-4">
            <h3 className="font-display text-lg font-semibold">Voluntary self-identification</h3>
            <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">
              Entirely optional. Leave any of these blank to keep answering them by hand on each
              application — saving an answer here only means autofill can use it, never that it's
              required.
            </p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label>
                <span className="label">Gender</span>
                <select className="input" value={gender} onChange={(event) => setGender(event.target.value)}>
                  <option value="">Prefer not to say</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Non-binary">Non-binary</option>
                </select>
              </label>
              <label>
                <span className="label">Hispanic or Latino</span>
                <select
                  className="input"
                  value={raceEthnicity}
                  onChange={(event) => setRaceEthnicity(event.target.value)}
                >
                  <option value="">Prefer not to say</option>
                  <option value="Yes">Yes</option>
                  <option value="No">No</option>
                </select>
              </label>
              <label>
                <span className="label">Veteran status</span>
                <select
                  className="input"
                  value={veteranStatus}
                  onChange={(event) => setVeteranStatus(event.target.value)}
                >
                  <option value="">I don&apos;t wish to answer</option>
                  <option value="I am not a protected veteran">I am not a protected veteran</option>
                  <option value="I identify as one or more of the classifications of a protected veteran">
                    I identify as a protected veteran
                  </option>
                </select>
              </label>
              <label>
                <span className="label">Disability status</span>
                <select
                  className="input"
                  value={disabilityStatus}
                  onChange={(event) => setDisabilityStatus(event.target.value)}
                >
                  <option value="">I do not want to answer</option>
                  <option value="Yes, I have a disability, or have had one in the past">
                    Yes, I have (or have had) a disability
                  </option>
                  <option value="No, I do not have a disability and have not had one in the past">
                    No, I do not have a disability
                  </option>
                </select>
              </label>
            </div>
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

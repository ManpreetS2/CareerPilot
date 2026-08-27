import { useState, type DragEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { CandidateSummary } from "../components/CandidateSummary";
import { ErrorBanner } from "../components/ErrorBanner";
import { ResumeParsingProgress } from "../components/ResumeParsingProgress";
import { ConstellationProgress } from "../components/signature/ConstellationProgress";
import { IntelligenceField } from "../components/signature/IntelligenceField";
import { WorkflowPath } from "../components/signature/WorkflowPath";
import { Glass } from "../components/ui/glass";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { APP_NAME } from "../lib/config";
import { CURATED_ROLES, readRoleType, writeRoleType, type RoleTypeFilter } from "../lib/job-role-type";
import { readOnboardingProgress, saveOnboardingProgress } from "../lib/onboarding";
import { resumeParseErrorHeading } from "../lib/resume-parse-error";
import { useCandidateSession } from "../lib/session";

const STEPS = [
  { id: 1, title: "Welcome" },
  { id: 2, title: "Target roles" },
  { id: 3, title: "Resume upload" },
  { id: 4, title: "Review parsed profile" },
  { id: 5, title: "Role type" },
  { id: 6, title: "Location and work mode" },
  { id: 7, title: "Review and complete" },
] as const;

const MAX_CLIENT_UPLOAD_BYTES = 10 * 1024 * 1024;

export function OnboardingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const reduce = useReducedMotion();
  const { candidate, preferences, setCandidateProfile, setJobPreferences } = useCandidateSession();
  const initial = user ? readOnboardingProgress(user.id) : { step: 1, skipped: false, completed: false };
  const [step, setStep] = useState(Math.min(Math.max(initial.step, 1), STEPS.length));
  const [roles, setRoles] = useState(preferences?.target_roles?.join(", ") || "");
  const [location, setLocation] = useState(preferences?.preferred_locations?.[0] || "");
  const [roleType, setRoleType] = useState<RoleTypeFilter>(readRoleType(preferences?.constraints));
  const [workMode, setWorkMode] = useState(preferences?.remote_preference || "");
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const title = STEPS[step - 1]?.title ?? "Welcome";

  function persist(nextStep: number, extra?: { skipped?: boolean; completed?: boolean }) {
    if (!user) return;
    saveOnboardingProgress(user.id, {
      step: nextStep,
      skipped: extra?.skipped ?? false,
      completed: extra?.completed ?? false,
    });
  }

  function enterApp(skipped: boolean, completed: boolean) {
    persist(step, { skipped, completed });
    navigate("/dashboard", { replace: true });
  }

  async function saveGoals() {
    const targetRoles = roles
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const saved = await api.savePreferences({
      ...(preferences ?? { target_roles: [], preferred_locations: [], constraints: [] }),
      target_roles: targetRoles,
      preferred_locations: location.trim() ? [location.trim()] : [],
      remote_preference: workMode || null,
      constraints: writeRoleType(preferences?.constraints, roleType),
    });
    setJobPreferences(saved);
  }

  async function onContinue() {
    setError(null);
    setBusy(true);
    try {
      if (step === 2 || step === 5 || step === 6 || step === 7) await saveGoals();
      if (step === 3 && file) {
        const parsed = await api.parseResume(file);
        setCandidateProfile(parsed.candidate);
      }
      if (step === 7) {
        persist(7, { skipped: false, completed: true });
        navigate("/dashboard", { replace: true });
        return;
      }
      const next = Math.min(step + 1, STEPS.length);
      setStep(next);
      persist(next);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function onBack() {
    const next = Math.max(step - 1, 1);
    setStep(next);
    persist(next);
  }

  function selectFile(next: File | null) {
    setError(null);
    if (!next) {
      setFile(null);
      return;
    }
    const looksPdf = next.type === "application/pdf" || next.name.toLowerCase().endsWith(".pdf");
    if (!looksPdf) {
      setError(new Error("Please choose a valid PDF file."));
      return;
    }
    if (next.size > MAX_CLIENT_UPLOAD_BYTES) {
      setError(new Error("Resume PDFs must be 10 MiB or smaller."));
      return;
    }
    setFile(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    selectFile(event.dataTransfer.files?.[0] ?? null);
  }

  async function onFinishEarly(event: FormEvent) {
    event.preventDefault();
    enterApp(true, false);
  }

  return (
    <div className="cp-atmosphere relative min-h-[100dvh] bg-background px-4 py-8">
      <IntelligenceField />
      <div className="relative z-10 mx-auto max-w-2xl space-y-6">
        <div>
          <p className="text-sm font-semibold text-primary">{APP_NAME}</p>
          <h1 className="title-fluid mt-1 font-display font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Step {step} of {STEPS.length}
          </p>
          <div className="mt-5">
            <ConstellationProgress step={step} />
          </div>
          <WorkflowPath
            className="mt-4"
            nodes={[
              { id: "profile", label: "Profile", state: step >= 4 ? "complete" : "current" },
              { id: "discover", label: "Discover", state: "upcoming" },
              { id: "analyze", label: "Analyze", state: "upcoming" },
              { id: "prepare", label: "Prepare", state: "upcoming" },
              { id: "track", label: "Track", state: "upcoming" },
            ]}
          />
        </div>

        <ErrorBanner error={error} heading={resumeParseErrorHeading(error)} />

        <AnimatePresence mode="wait">
          <motion.section
            key={step}
            className="p-0"
            data-testid={`onboarding-step-${step}`}
            initial={{ opacity: reduce ? 1 : 0, y: reduce ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: reduce ? 1 : 0, y: reduce ? 0 : -8 }}
            transition={{ duration: reduce ? 0 : 0.18 }}
          >
            <Glass variant="working" refract className="rounded-[var(--radius-lg)] p-6">
            {step === 1 ? (
              <p className="text-sm leading-relaxed text-muted-foreground">
                CareerPilot grounds every later recommendation in your real profile. You can skip
                any step and finish later — saved data stays, and the app remains usable.
              </p>
            ) : null}
            {step === 2 ? (
              <div className="space-y-4">
                <label>
                  <span className="label">Target roles</span>
                  <input
                    className="input"
                    value={roles}
                    onChange={(event) => setRoles(event.target.value)}
                    placeholder="Type a role or pick a suggestion"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  {CURATED_ROLES.map((role) => (
                    <button
                      key={role}
                      type="button"
                      className="rounded-full border border-border px-2.5 py-1 text-xs hover:bg-muted"
                      onClick={() => {
                        const parts = roles.split(",").map((item) => item.trim()).filter(Boolean);
                        if (!parts.some((item) => item.toLowerCase() === role.toLowerCase())) {
                          setRoles([...parts, role].join(", "));
                        }
                      }}
                    >
                      {role}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {step === 3 ? (
              <div className="space-y-3">
                {busy && file ? (
                  <ResumeParsingProgress active />
                ) : (
                  <>
                    <p className="text-sm text-muted-foreground">
                      Resume upload is recommended, not required. You can continue without a file.
                    </p>
                    <label
                      onDragOver={(event) => {
                        event.preventDefault();
                        setDragActive(true);
                      }}
                      onDragLeave={() => setDragActive(false)}
                      onDrop={onDrop}
                      className={`flex cursor-pointer flex-col items-center rounded-[var(--radius-md)] border border-dashed px-6 py-10 text-center ${
                        dragActive ? "border-primary bg-primary/5" : "border-border"
                      }`}
                    >
                      <span className="font-semibold">Drag & drop a resume PDF</span>
                      <span className="mt-1 text-sm text-muted-foreground">
                        {file ? file.name : "PDF only · max 10 MiB"}
                      </span>
                      <input
                        type="file"
                        accept="application/pdf,.pdf"
                        className="sr-only"
                        onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
                      />
                    </label>
                  </>
                )}
              </div>
            ) : null}
            {step === 4 ? (
              candidate ? (
                <CandidateSummary candidate={candidate} preferences={preferences} />
              ) : (
                <p className="text-sm text-muted-foreground">
                  No parsed profile yet. You can go back to upload a resume, or continue and add
                  one later from Profile.
                </p>
              )
            ) : null}
            {step === 5 ? (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Stored as a preference constraint (`role_type`). Job filters use posting titles — CareerPilot
                  does not invent a backend role-type field.
                </p>
                <div className="grid gap-2">
                  {(
                    [
                      ["internships", "Internships"],
                      ["full_time", "Full-time roles"],
                      ["both", "Both internships and full-time"],
                    ] as const
                  ).map(([value, label]) => (
                    <label key={value} className="flex items-center gap-2 rounded-[var(--radius-md)] border border-border px-3 py-2">
                      <input
                        type="radio"
                        name="role-type"
                        checked={roleType === value}
                        onChange={() => setRoleType(value)}
                      />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
            {step === 6 ? (
              <div className="space-y-4">
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
                  <span className="label">Work mode</span>
                  <select className="input" value={workMode} onChange={(event) => setWorkMode(event.target.value)}>
                    <option value="">No preference selected…</option>
                    <option value="remote">Remote</option>
                    <option value="hybrid_or_remote">Hybrid or remote</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">Onsite</option>
                  </select>
                </label>
              </div>
            ) : null}
            {step === 7 ? (
              <div className="space-y-3 text-sm">
                <p className="text-muted-foreground">
                  Application details such as work authorization stay on Profile. They are optional and
                  are not collected here.
                </p>
                <dl className="grid gap-2">
                  <div>
                    <dt className="text-muted-foreground">Roles</dt>
                    <dd>{roles.trim() || "Not set yet"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Role type</dt>
                    <dd>{roleType.replace("_", " ")}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Location</dt>
                    <dd>{location.trim() || "Not set yet"}</dd>
                  </div>
                </dl>
              </div>
            ) : null}
            </Glass>
          </motion.section>
        </AnimatePresence>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button type="button" className="btn-ghost" data-testid="onboarding-back" onClick={onBack} disabled={step === 1 || busy}>
            Back
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-secondary"
              data-testid="onboarding-skip"
              onClick={onFinishEarly}
            >
              Skip / End setup
            </button>
            <button
              type="button"
              className="btn-primary"
              data-testid="onboarding-continue"
              disabled={busy}
              onClick={() => void onContinue()}
            >
              {busy && step === 3 && file
                ? "Working…"
                : busy
                  ? "Saving…"
                  : error && step === 3 && file
                    ? "Retry"
                    : step === STEPS.length
                      ? "Finish"
                      : "Continue"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

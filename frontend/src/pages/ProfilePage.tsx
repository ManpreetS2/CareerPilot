import { useMemo, useState, type DragEvent, type FormEvent } from "react";
import { FileUp, Upload } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CandidateSummary } from "../components/CandidateSummary";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { PreferenceForm } from "../components/PreferenceForm";
import { PageHeader } from "../components/ui/page-header";
import { Surface } from "../components/ui/surface";
import { ReadinessPath } from "../components/signature/ReadinessPath";
import { api } from "../lib/api";
import { queryKeys } from "../lib/query-keys";
import { useCandidateSession } from "../lib/session";
import type { TargetPreferences } from "../lib/types";

const MAX_CLIENT_UPLOAD_BYTES = 10 * 1024 * 1024;

export function ProfilePage() {
  const queryClient = useQueryClient();
  const { candidate, preferences, setCandidateProfile, setJobPreferences } = useCandidateSession();
  const profileQuery = useQuery({
    queryKey: queryKeys.profile,
    queryFn: ({ signal }) => api.getProfile({ signal }),
  });

  const liveCandidate = profileQuery.data?.candidate ?? candidate;
  const livePreferences = profileQuery.data?.preferences ?? preferences;

  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<unknown>(null);
  const [prefsLoading, setPrefsLoading] = useState(false);
  const [prefsError, setPrefsError] = useState<unknown>(null);
  const [prefsSuccess, setPrefsSuccess] = useState<string | null>(null);

  const canBuildProfile = useMemo(() => Boolean(file) && !profileLoading, [file, profileLoading]);
  const readinessFlags = [
    Boolean(liveCandidate?.name),
    Boolean(liveCandidate?.skills.length),
    Boolean(liveCandidate?.experience.length),
    Boolean(liveCandidate?.projects.length),
    Boolean(livePreferences?.target_roles?.length),
  ];

  function selectFile(next: File | null) {
    setProfileError(null);
    if (!next) {
      setFile(null);
      return;
    }
    const looksPdf = next.type === "application/pdf" || next.name.toLowerCase().endsWith(".pdf");
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
      await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
    } catch (err) {
      setProfileError(err);
    } finally {
      setProfileLoading(false);
    }
  }

  async function onSavePreferences(next: TargetPreferences) {
    setPrefsLoading(true);
    setPrefsError(null);
    setPrefsSuccess(null);
    try {
      const saved = await api.savePreferences(next);
      setJobPreferences(saved);
      setPrefsSuccess("Job preferences saved.");
      await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
    } catch (err) {
      setPrefsError(err);
    } finally {
      setPrefsLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Profile"
        description="Resume-derived fields stay read-only. Upload a PDF to refresh them. Job preferences save through the real preferences API."
      />

      <Surface className="p-5">
        <h2 className="font-display text-lg font-semibold">Profile readiness</h2>
        <div className="mt-3">
          <ReadinessPath flags={readinessFlags} />
        </div>
      </Surface>

      <Surface className="space-y-5 p-6">
        <div>
          <h2 className="font-display text-2xl font-semibold">Upload / Replace Resume</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Parsing refreshes the grounded candidate profile. It does not invent job preferences.
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
            className={`flex cursor-pointer flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed px-6 py-10 text-center ${
              dragActive ? "border-primary bg-primary/5" : "border-border bg-surface-secondary"
            }`}
          >
            <FileUp className="h-8 w-8 text-primary" aria-hidden />
            <span className="mt-3 font-semibold">Drag & drop a resume PDF</span>
            <span className="mt-1 text-sm text-muted-foreground">or click to choose a file</span>
            <span className="mt-3 text-xs text-muted-foreground">
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
            {profileLoading ? "Refreshing profile…" : "Upload / Replace Resume"}
          </button>
        </form>
        {profileLoading ? <LoadingState label="Extracting and grounding your resume…" /> : null}
      </Surface>

      {liveCandidate ? (
        <CandidateSummary candidate={liveCandidate} preferences={livePreferences} />
      ) : (
        !profileLoading && (
          <p className="text-sm text-muted-foreground">
            No profile yet. Upload a PDF to extract a grounded candidate profile.
          </p>
        )
      )}

      <Surface className="space-y-5 p-6" id="job-preferences">
        <div>
          <h2 className="font-display text-2xl font-semibold">Job Preferences</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Saved independently from resume parsing. Leave legal fields unanswered until you choose
            deliberately.
          </p>
        </div>
        <PreferenceForm
          preferences={livePreferences}
          onSave={onSavePreferences}
          saving={prefsLoading}
          error={prefsError}
          success={prefsSuccess}
        />
      </Surface>
    </div>
  );
}

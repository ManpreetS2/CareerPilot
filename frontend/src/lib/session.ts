import { useEffect, useState } from "react";
import type { CandidateProfile, TargetPreferences } from "./types";

const CANDIDATE_KEY = "careerpilot.candidate";
const PREFERENCES_KEY = "careerpilot.preferences";
const SELECTED_JOB_KEY = "careerpilot.selectedJobId";

let activeUserId: number | null = null;

export function bindSessionUser(userId: number | null) {
  activeUserId = userId;
}

function scopedKey(base: string): string {
  return activeUserId == null ? base : `${base}.u${activeUserId}`;
}

/** Prototype hourly values were small positives (e.g. 35). Annual salaries are >= 10000. */
export const LEGACY_HOURLY_SALARY_CEILING = 9999;

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function isLegacyHourlySalary(value: number | null | undefined): boolean {
  return typeof value === "number" && value > 0 && value <= LEGACY_HOURLY_SALARY_CEILING;
}

export function sanitizeStoredPreferences(
  preferences: TargetPreferences | null,
): TargetPreferences | null {
  if (!preferences) return null;
  if (!isLegacyHourlySalary(preferences.salary_min)) return preferences;
  return { ...preferences, salary_min: null };
}

export function saveCandidate(candidate: CandidateProfile) {
  localStorage.setItem(scopedKey(CANDIDATE_KEY), JSON.stringify(candidate));
}

export function savePreferences(preferences: TargetPreferences) {
  localStorage.setItem(scopedKey(PREFERENCES_KEY), JSON.stringify(preferences));
}

/** @deprecated Prefer saveCandidate / savePreferences independently. */
export function saveCandidateSession(
  candidate: CandidateProfile,
  preferences: TargetPreferences | null,
) {
  saveCandidate(candidate);
  if (preferences) savePreferences(preferences);
}

export function saveSelectedJobId(jobId: string) {
  localStorage.setItem(scopedKey(SELECTED_JOB_KEY), jobId);
}

export function clearCandidateSession() {
  const prefixes = [CANDIDATE_KEY, PREFERENCES_KEY, SELECTED_JOB_KEY];
  for (const key of Object.keys(localStorage)) {
    if (prefixes.some((prefix) => key === prefix || key.startsWith(`${prefix}.u`))) {
      localStorage.removeItem(key);
    }
  }
}

export function getSelectedJobId(): string | null {
  return localStorage.getItem(scopedKey(SELECTED_JOB_KEY));
}

export function useCandidateSession() {
  const [candidate, setCandidate] = useState<CandidateProfile | null>(() =>
    readJson<CandidateProfile>(scopedKey(CANDIDATE_KEY)),
  );
  const [preferences, setPreferences] = useState<TargetPreferences | null>(() =>
    sanitizeStoredPreferences(readJson<TargetPreferences>(scopedKey(PREFERENCES_KEY))),
  );

  useEffect(() => {
    const onStorage = () => {
      setCandidate(readJson<CandidateProfile>(scopedKey(CANDIDATE_KEY)));
      setPreferences(sanitizeStoredPreferences(readJson<TargetPreferences>(scopedKey(PREFERENCES_KEY))));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return {
    candidate,
    preferences,
    setCandidateProfile: (next: CandidateProfile) => {
      saveCandidate(next);
      setCandidate(next);
    },
    setJobPreferences: (next: TargetPreferences) => {
      const cleaned = sanitizeStoredPreferences(next) ?? next;
      savePreferences(cleaned);
      setPreferences(cleaned);
    },
    setSession: (nextCandidate: CandidateProfile, nextPreferences: TargetPreferences | null) => {
      saveCandidate(nextCandidate);
      setCandidate(nextCandidate);
      if (nextPreferences) {
        const cleaned = sanitizeStoredPreferences(nextPreferences) ?? nextPreferences;
        savePreferences(cleaned);
        setPreferences(cleaned);
      }
    },
  };
}

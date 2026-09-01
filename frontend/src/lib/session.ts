import { useEffect, useState } from "react";
import type { CandidateProfile, TargetPreferences } from "./types";

const CANDIDATE_KEY = "careerpilot.candidate";
const PREFERENCES_KEY = "careerpilot.preferences";
const SELECTED_JOB_KEY = "careerpilot.selectedJobId";
const SESSION_EVENT = "careerpilot-session-changed";

let activeUserId: number | null = null;

function emitSessionChange() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SESSION_EVENT));
  }
}

export function bindSessionUser(userId: number | null) {
  activeUserId = userId;
  emitSessionChange();
}

export function getActiveSessionUserId(): number | null {
  return activeUserId;
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
  emitSessionChange();
}

export function savePreferences(preferences: TargetPreferences) {
  localStorage.setItem(scopedKey(PREFERENCES_KEY), JSON.stringify(preferences));
  emitSessionChange();
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

export function applyServerProfile(
  candidate: CandidateProfile | null,
  preferences: TargetPreferences | null,
) {
  if (candidate) {
    localStorage.setItem(scopedKey(CANDIDATE_KEY), JSON.stringify(candidate));
  } else {
    localStorage.removeItem(scopedKey(CANDIDATE_KEY));
  }
  if (preferences) {
    const cleaned = sanitizeStoredPreferences(preferences) ?? preferences;
    localStorage.setItem(scopedKey(PREFERENCES_KEY), JSON.stringify(cleaned));
  } else {
    localStorage.removeItem(scopedKey(PREFERENCES_KEY));
  }
  emitSessionChange();
}

export function clearCurrentUserSensitiveCache() {
  localStorage.removeItem(scopedKey(CANDIDATE_KEY));
  localStorage.removeItem(scopedKey(PREFERENCES_KEY));
  localStorage.removeItem(scopedKey(SELECTED_JOB_KEY));
  emitSessionChange();
}

/** Clears only the current user's sensitive cache. Other users' keys stay. */
export function clearCandidateSession() {
  clearCurrentUserSensitiveCache();
}

export function getSelectedJobId(): string | null {
  return localStorage.getItem(scopedKey(SELECTED_JOB_KEY));
}

export function useCandidateSession() {
  const [sessionUserId, setSessionUserId] = useState<number | null>(() => getActiveSessionUserId());
  const [candidate, setCandidate] = useState<CandidateProfile | null>(() =>
    readJson<CandidateProfile>(scopedKey(CANDIDATE_KEY)),
  );
  const [preferences, setPreferences] = useState<TargetPreferences | null>(() =>
    sanitizeStoredPreferences(readJson<TargetPreferences>(scopedKey(PREFERENCES_KEY))),
  );

  useEffect(() => {
    const onChange = () => {
      setSessionUserId(getActiveSessionUserId());
      setCandidate(readJson<CandidateProfile>(scopedKey(CANDIDATE_KEY)));
      setPreferences(
        sanitizeStoredPreferences(readJson<TargetPreferences>(scopedKey(PREFERENCES_KEY))),
      );
    };
    window.addEventListener("storage", onChange);
    window.addEventListener(SESSION_EVENT, onChange);
    return () => {
      window.removeEventListener("storage", onChange);
      window.removeEventListener(SESSION_EVENT, onChange);
    };
  }, []);

  return {
    sessionUserId,
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

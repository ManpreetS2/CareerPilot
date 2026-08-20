import { useEffect, useState } from "react";
import type { CandidateProfile, TargetPreferences } from "./types";

const CANDIDATE_KEY = "careerpilot.candidate";
const PREFERENCES_KEY = "careerpilot.preferences";
const SELECTED_JOB_KEY = "careerpilot.selectedJobId";

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function saveCandidateSession(
  candidate: CandidateProfile,
  preferences: TargetPreferences | null,
) {
  localStorage.setItem(CANDIDATE_KEY, JSON.stringify(candidate));
  if (preferences) {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  }
}

export function saveSelectedJobId(jobId: string) {
  localStorage.setItem(SELECTED_JOB_KEY, jobId);
}

export function getSelectedJobId(): string | null {
  return localStorage.getItem(SELECTED_JOB_KEY);
}

export function useCandidateSession() {
  const [candidate, setCandidate] = useState<CandidateProfile | null>(() =>
    readJson<CandidateProfile>(CANDIDATE_KEY),
  );
  const [preferences, setPreferences] = useState<TargetPreferences | null>(() =>
    readJson<TargetPreferences>(PREFERENCES_KEY),
  );

  useEffect(() => {
    const onStorage = () => {
      setCandidate(readJson<CandidateProfile>(CANDIDATE_KEY));
      setPreferences(readJson<TargetPreferences>(PREFERENCES_KEY));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  return {
    candidate,
    preferences,
    setSession: (nextCandidate: CandidateProfile, nextPreferences: TargetPreferences | null) => {
      saveCandidateSession(nextCandidate, nextPreferences);
      setCandidate(nextCandidate);
      setPreferences(nextPreferences);
    },
  };
}

/** Isolated demo metrics for dashboard cards until Day 2+ agents persist real aggregates. */
export const DEMO_DASHBOARD_METRICS = {
  source: "demo" as const,
  profileCompletion: 72,
  jobsDiscovered: 3,
  jobsVerified: 1,
  highMatches: 1,
  readyToApply: 1,
  applicationsSaved: 0,
  applicationsReady: 1,
  applicationsApplied: 0,
  interviews: 0,
};

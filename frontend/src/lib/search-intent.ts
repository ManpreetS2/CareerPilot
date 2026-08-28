import type { SearchIntent } from "./types";

export type { SearchIntent };

export function parseSearchIntent(raw: string): SearchIntent {
  return {
    rawQuery: raw.trim() || undefined,
    roles: [],
    locations: [],
    employmentTypes: [],
    experienceLevels: [],
    workModes: [],
    industries: [],
    skills: [],
    parserReady: false,
  };
}

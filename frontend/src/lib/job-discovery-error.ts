import { ApiClientError } from "./api";

export function jobDiscoveryErrorHeading(error: unknown): string | undefined {
  const message = error instanceof Error ? error.message : "";
  const status = error instanceof ApiClientError ? error.status : null;
  const lower = message.toLowerCase();
  if (status === 504 || lower.includes("timed out")) return "Job discovery timed out";
  if (status === 0) return "Job search temporarily unavailable";
  if (
    status === 502 ||
    status === 503 ||
    lower.includes("could not reach") ||
    lower.includes("enough job sources")
  ) {
    return "We couldn't reach enough job sources";
  }
  if (status && status >= 500) return "Job search temporarily unavailable";
  return undefined;
}

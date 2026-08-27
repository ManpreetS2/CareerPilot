import { ApiClientError } from "./api";

export function resumeParseErrorHeading(error: unknown): string | undefined {
  const message = error instanceof Error ? error.message : "";
  const status = error instanceof ApiClientError ? error.status : null;
  const lower = message.toLowerCase();
  if (status === 504 || lower.includes("timed out")) return "Resume analysis timed out";
  if (lower.includes("too little readable")) return "Resume contained too little readable text";
  if (lower.includes("could not be read")) return "Resume could not be read";
  if (
    status === 502 ||
    status === 503 ||
    lower.includes("temporarily unavailable") ||
    lower.includes("ai service")
  ) {
    return "AI service temporarily unavailable";
  }
  return undefined;
}

// Text-only ports of frontend/src/components/{StatusBadge,SourceBadge,MatchBadge}.tsx
// — same tone logic and Tailwind classes so the panel matches the main web
// app's look, minus the lucide-react icons (not worth a whole icon-library
// dependency for a handful of small badges in a narrow panel).
import type { JobStatus, MaterialsStatus } from "./api";

function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

export function statusBadge(status: JobStatus | string): string {
  const normalized = status.toLowerCase();
  const tone =
    normalized === "verified"
      ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
      : normalized === "flagged"
        ? "bg-rose-100 text-danger-600 dark:bg-rose-950/40 dark:text-rose-200"
        : normalized === "discovered"
          ? "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200"
          : normalized === "stale"
            ? "bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-300"
            : "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-100";
  return `<span class="status-pill capitalize ${tone}">${escapeHtml(status.replaceAll("_", " "))}</span>`;
}

const SOURCE_LABELS: Record<string, string> = {
  adzuna: "Adzuna",
  remoteok: "RemoteOK",
  greenhouse: "Greenhouse",
  lever: "Lever",
  remotive: "Remotive",
  manual: "Manual",
};
const ATS_SOURCES = new Set(["greenhouse", "lever"]);
const AGGREGATOR_SOURCES = new Set(["adzuna", "remoteok", "remotive"]);

export function sourceBadge(source: string): string {
  const normalized = source.toLowerCase();
  const label = SOURCE_LABELS[normalized] ?? source;
  const tone = ATS_SOURCES.has(normalized)
    ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
    : AGGREGATOR_SOURCES.has(normalized)
      ? "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-100"
      : "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200";
  return `<span class="status-pill ${tone}">${escapeHtml(label)}</span>`;
}

export function scoutedTimeAgo(dateScraped?: string | null): string | null {
  if (!dateScraped) return null;
  const scraped = new Date(dateScraped).getTime();
  if (Number.isNaN(scraped)) return null;
  const days = Math.floor((Date.now() - scraped) / (1000 * 60 * 60 * 24));
  if (days <= 0) return "Seen today";
  if (days === 1) return "Seen 1 day ago";
  return `Seen ${days} days ago`;
}

export function matchBadge(score?: number | null, recommendation?: string | null): string {
  if (score == null) {
    return `<span class="status-pill bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-200">Not scored</span>`;
  }
  const tone =
    score >= 80
      ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
      : score >= 65
        ? "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200"
        : "bg-rose-100 text-danger-600 dark:bg-rose-950/40 dark:text-rose-200";
  const rec = recommendation ? ` · ${escapeHtml(recommendation)}` : "";
  return `<span class="status-pill ${tone}">${Math.round(score)}% MATCH${rec}</span>`;
}

const MATERIALS_LABELS: Record<NonNullable<MaterialsStatus>, string> = {
  missing: "No materials yet",
  current: "Materials ready",
  stale_pending: "Materials need regenerating",
  stale_reviewed: "Reviewed materials need regenerating",
};

export function materialsBadge(status: MaterialsStatus): string {
  if (!status) {
    return `<span class="status-pill bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-200">${MATERIALS_LABELS.missing}</span>`;
  }
  const tone =
    status === "current"
      ? "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200"
      : status === "missing"
        ? "bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-200"
        : "bg-amber-100 text-warn-600 dark:bg-amber-950/40 dark:text-amber-200";
  return `<span class="status-pill ${tone}">${MATERIALS_LABELS[status]}</span>`;
}

export { escapeHtml };

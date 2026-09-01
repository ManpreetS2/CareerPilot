import { Building2, Globe2, Link2 } from "lucide-react";

const LABELS: Record<string, string> = {
  adzuna: "Adzuna",
  remoteok: "RemoteOK",
  greenhouse: "Greenhouse",
  lever: "Lever",
  remotive: "Remotive",
  jobicy: "Jobicy",
  himalayas: "Himalayas",
  manual: "Manual",
};

// Direct-employer ATS postings (Greenhouse/Lever) get their own tone —
// they're first-party data, not an aggregator's copy of a listing.
const ATS_SOURCES = new Set(["greenhouse", "lever"]);
const AGGREGATOR_SOURCES = new Set(["adzuna", "remoteok", "remotive", "jobicy", "himalayas"]);

export function SourceBadge({ source }: { source: string }) {
  const normalized = source.toLowerCase();
  const label = LABELS[normalized] ?? source;

  const tone = ATS_SOURCES.has(normalized)
    ? "bg-muted text-primary"
    : AGGREGATOR_SOURCES.has(normalized)
      ? "bg-muted text-muted-foreground"
      : "bg-muted text-warning";

  const Icon = ATS_SOURCES.has(normalized) ? Building2 : AGGREGATOR_SOURCES.has(normalized) ? Globe2 : Link2;

  return (
    <span className={`status-pill ${tone}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  );
}

/** date_scraped arrives as a naive UTC timestamp (SQLite drops tzinfo), and
 * JavaScript parses an offset-less date-time as LOCAL time — shifting it by
 * the viewer's UTC offset and pushing the day count across a boundary.
 * Appending the offset the value actually carries keeps the math right. */
function parseUtcTimestamp(value: string): number {
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasOffset ? value : `${value}Z`).getTime();
}

export function scoutedTimeAgo(dateScraped?: string | null): string | null {
  if (!dateScraped) return null;
  const scraped = parseUtcTimestamp(dateScraped);
  if (Number.isNaN(scraped)) return null;
  const days = Math.floor((Date.now() - scraped) / (1000 * 60 * 60 * 24));
  if (days <= 0) return "Seen today";
  if (days === 1) return "Seen 1 day ago";
  return `Seen ${days} days ago`;
}

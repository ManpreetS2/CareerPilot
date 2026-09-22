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

export function SourceBadge({
  source,
  url,
  sourceUrl,
}: {
  source: string;
  /** The job's own url — for most aggregators this already points at
   * their own site, so it's the fallback attribution link. */
  url?: string | null;
  /** An aggregator's own listing page, when that differs from `url`
   * (Himalayas' url is a direct employer application link that bypasses
   * himalayas.app entirely). Takes priority over `url` when present. */
  sourceUrl?: string | null;
}) {
  const normalized = source.toLowerCase();
  const label = LABELS[normalized] ?? source;

  const tone = ATS_SOURCES.has(normalized)
    ? "border border-primary/25 bg-primary/10 text-primary"
    : AGGREGATOR_SOURCES.has(normalized)
      ? "border border-border/70 bg-muted/80 text-muted-foreground"
      : "border border-warning/25 bg-warning/10 text-warning";

  const Icon = ATS_SOURCES.has(normalized) ? Building2 : AGGREGATOR_SOURCES.has(normalized) ? Globe2 : Link2;

  const content = (
    <>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </>
  );

  // Attribution link only for aggregators — an ATS badge (Greenhouse/Lever)
  // or "Manual" linking to itself would be redundant with the existing
  // "Open posting" action, which already points at the real posting.
  const href = AGGREGATOR_SOURCES.has(normalized) ? sourceUrl || url || null : null;
  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className={`status-pill ${tone} hover:opacity-80`}
        aria-label={`${label} — open original listing`}
      >
        {content}
      </a>
    );
  }

  return <span className={`status-pill ${tone}`}>{content}</span>;
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

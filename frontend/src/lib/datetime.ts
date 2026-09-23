const ISO_DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T/;
const HAS_OFFSET = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/**
 * API date-times are naive UTC (SQLite drops tzinfo), and JavaScript reads an
 * offset-less ISO date-time as local time, shifting it by the viewer's UTC
 * offset. A calendar date ("2026-08-21") is the opposite trap: JavaScript
 * reads it as UTC midnight, which is the previous day anywhere west of UTC.
 */
export function parseApiTimestamp(value: string): Date {
  const trimmed = value.trim();
  const dateOnly = ISO_DATE_ONLY.exec(trimmed);
  if (dateOnly) {
    return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
  }
  if (ISO_DATE_TIME.test(trimmed) && !HAS_OFFSET.test(trimmed)) {
    return new Date(`${trimmed}Z`);
  }
  return new Date(trimmed);
}

export function formatApiTimestamp(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const parsed = parseApiTimestamp(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed.toLocaleString();
}

export function formatApiDate(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const parsed = parseApiTimestamp(value);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed.toLocaleDateString();
}

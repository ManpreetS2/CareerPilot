/**
 * "Add to Google Calendar" is a plain URL — Google's own create-event UI
 * reads these query params and pre-fills the form. No OAuth, no API key,
 * no backend call: this is computed entirely client-side from data already
 * on the page.
 */

function formatDateForGoogle(isoDate: string): string {
  return isoDate.replaceAll("-", "");
}

function addOneDay(isoDate: string): string {
  const parts = isoDate.split("-").map(Number);
  const year = parts[0] ?? 0;
  const month = parts[1] ?? 1;
  const day = parts[2] ?? 1;
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + 1);
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

export function googleCalendarUrl(jobTitle: string, company: string, reminderDate: string): string {
  const start = formatDateForGoogle(reminderDate);
  // Google's all-day "dates" range is exclusive at the end, same convention
  // as the .ics DTEND this button sits next to.
  const end = addOneDay(reminderDate);
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: `Follow up: ${jobTitle} @ ${company}`,
    dates: `${start}/${end}`,
    details: "CareerPilot follow-up reminder for your application.",
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

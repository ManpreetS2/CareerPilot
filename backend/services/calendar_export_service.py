"""Render a tracker follow-up reminder to a standard RFC 5545 .ics file.

No account connection, no OAuth, no external calendar API — this is a plain
generated file the user downloads and imports themselves into whatever
calendar app they already use. Purely a read of the existing, already-set
ApplicationTrackerRecord.reminder_date; never writes it or infers one.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.services.safe_filename import safe_filename_stem

_FOLD_LIMIT = 75  # RFC 5545 §3.1: content lines SHOULD NOT exceed 75 octets


def reminder_ics_filename(job_title: str, company: str) -> str:
    """A safe, human-readable download filename for one reminder."""
    stem = safe_filename_stem([job_title, company], default="follow-up-reminder")
    return f"{stem}.ics"


def _escape_ics_text(value: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping, applied before folding.

    Normalizes all three line-ending styles (CRLF, lone CR, lone LF) to a
    single "\n" before escaping it to the RFC's literal "\\n" — a lone "\r"
    (an old Mac-style ending, or a malformed scrape) has no adjacent "\n" to
    pair with and previously just got deleted, silently concatenating the
    text on either side of it instead of preserving the line break.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\n", "\\n")
    value = value.replace(";", "\\;").replace(",", "\\,")
    return value


def _fold_line(line: str) -> str:
    """Fold a content line over 75 octets: CRLF + one leading space per
    continuation. Splits on UTF-8 byte boundaries, not characters, since the
    75-octet limit in the RFC is a byte count."""
    encoded = line.encode("utf-8")
    if len(encoded) <= _FOLD_LIMIT:
        return line
    parts: list[bytes] = []
    remaining = encoded
    limit = _FOLD_LIMIT
    while len(remaining) > limit:
        cut = limit
        # Never split in the middle of a multi-byte UTF-8 sequence.
        while cut > 0 and (remaining[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
        limit = _FOLD_LIMIT - 1  # continuation lines start with one space
    parts.append(remaining)
    return "\r\n ".join(part.decode("utf-8") for part in parts)


def build_reminder_ics(*, job_public_id: str, job_title: str, company: str, reminder_date: date) -> bytes:
    """One VEVENT, all-day, for the given follow-up date."""
    start = reminder_date.strftime("%Y%m%d")
    end = (reminder_date + timedelta(days=1)).strftime("%Y%m%d")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = f"reminder-{job_public_id}-{reminder_date.isoformat()}@careerpilot.app"
    summary = _escape_ics_text(f"Follow up: {job_title} @ {company}")
    description = _escape_ics_text(
        "CareerPilot follow-up reminder for your application. This event was created "
        "from a date you set yourself; CareerPilot never schedules or infers reminders."
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CareerPilot//Application Tracker//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{start}",
        f"DTEND;VALUE=DATE:{end}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    folded = [_fold_line(line) for line in lines]
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")

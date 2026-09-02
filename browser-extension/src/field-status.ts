export type FieldUserStatus = "Ready" | "Needs review" | "Manual" | "Unsupported";

export type FieldStatusRow = {
  key: string;
  label: string;
  status: FieldUserStatus;
};

const READY_FIELDS: { key: string; label: string }[] = [
  { key: "full_name", label: "Name" },
  { key: "first_name", label: "First name" },
  { key: "last_name", label: "Last name" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "location", label: "Location" },
  { key: "linkedin_url", label: "LinkedIn" },
  { key: "github_url", label: "GitHub" },
  { key: "portfolio_url", label: "Portfolio" },
  { key: "current_company", label: "Current company" },
];

const REVIEW_FIELDS: { key: string; label: string }[] = [
  { key: "legal_name", label: "Legal name" },
  { key: "work_authorization", label: "Work authorization" },
  { key: "sponsorship_required", label: "Sponsorship" },
  { key: "earliest_start_date", label: "Start date" },
  { key: "currently_enrolled_in_program", label: "Enrollment" },
  { key: "expected_graduation", label: "Graduation" },
  { key: "degree_pursuing", label: "Degree" },
  { key: "cover_letter", label: "Cover letter" },
];

const MANUAL_FIELDS: { key: string; label: string }[] = [
  { key: "gender", label: "EEO question — gender" },
  { key: "race_ethnicity", label: "EEO question — race/ethnicity" },
  { key: "veteran_status", label: "EEO question — veteran status" },
  { key: "disability_status", label: "EEO question — disability" },
];

function hasValue(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === "boolean") return true;
  return String(value).trim().length > 0;
}

/** User-safe field statuses for the autofill preview. Never exposes probabilities. */
export function classifyAutofillFields(fields: Record<string, unknown> | null | undefined): FieldStatusRow[] {
  const source = fields ?? {};
  const rows: FieldStatusRow[] = [];
  const seen = new Set<string>();

  for (const field of READY_FIELDS) {
    if (!hasValue(source[field.key])) continue;
    rows.push({ ...field, status: "Ready" });
    seen.add(field.key);
  }
  for (const field of REVIEW_FIELDS) {
    if (!hasValue(source[field.key])) continue;
    rows.push({ ...field, status: "Needs review" });
    seen.add(field.key);
  }
  for (const field of MANUAL_FIELDS) {
    rows.push({ ...field, status: "Manual" });
    seen.add(field.key);
  }
  // Resume attachment is a separate owned-file workflow, not an autofill field.
  // Do not label it Unsupported — Fill can attach an approved resume version.
  void seen;
  return rows;
}

export const SENSITIVE_EEO_KEYS = MANUAL_FIELDS.map((field) => field.key);

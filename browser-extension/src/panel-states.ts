export const EXTENSION_PANEL_STATES = [
  "signed_out",
  "backend_unavailable",
  "unsupported_site",
  "supported_greenhouse",
  "supported_lever",
  "stale_job",
  "requirements_loading",
  "potential_match",
  "verified_fit_ready",
  "eligibility_review_required",
  "resume_file_unavailable",
  "resume_attached",
  "manual_field_required",
  "review_required",
  "no_submit",
] as const;

export type ExtensionPanelState = (typeof EXTENSION_PANEL_STATES)[number];

import type { PanelData } from "./api";
import { recognizeJobPage, type JobRecognition } from "./job-recognition";

export const EXTENSION_PANEL_STATES = [
  "loading",
  "signed_out",
  "backend_unavailable",
  "unsupported_site",
  "supported_greenhouse",
  "supported_lever",
  "job_recognized",
  "ingesting",
  "stale_job",
  "requirements_loading",
  "potential_match",
  "verification_running",
  "verified_fit_ready",
  "likely_ineligible",
  "eligibility_review_required",
  "materials_unavailable",
  "ready_to_prepare",
  "autofill_preview",
  "resume_file_unavailable",
  "resume_attached",
  "manual_field_required",
  "review_required",
  "error",
  "retry",
  "no_submit",
] as const;

export type ExtensionPanelState = (typeof EXTENSION_PANEL_STATES)[number];

export type PanelStateInput = {
  loading?: boolean;
  signedOut?: boolean;
  backendUnavailable?: boolean;
  error?: boolean;
  retry?: boolean;
  ingesting?: boolean;
  verifying?: boolean;
  autofillPreview?: boolean;
  url?: string | null;
  data?: PanelData | null;
};

export function eligibilityLabel(status: string | null | undefined): string {
  if (status === "likely_eligible") return "Eligible based on stated requirements";
  if (status === "likely_ineligible") return "Likely ineligible";
  if (status === "eligibility_uncertain") return "Uncertain";
  return "Uncertain";
}

export function materialsActionLabel(status: PanelData["materials_status"], approvalStatus?: string | null): string {
  if (status === "missing" || !status) return "Not prepared";
  if (status === "stale_pending" || status === "stale_reviewed") return "Needs changes";
  if (approvalStatus === "pending_review") return "Review required";
  if (approvalStatus === "approved") return "Approved";
  if (approvalStatus === "edit_requested") return "Needs changes";
  return "Generating";
}

export function isVerifiedScore(data: PanelData | null | undefined): boolean {
  return data?.score?.score_kind === "verified";
}

export function resolvePanelState(input: PanelStateInput): ExtensionPanelState {
  if (input.signedOut) return "signed_out";
  if (input.backendUnavailable) return "backend_unavailable";
  if (input.retry) return "retry";
  if (input.error) return "error";
  if (input.loading) return "loading";

  const url = input.url ?? "";
  const recognition: JobRecognition = url ? recognizeJobPage(url) : recognizeJobPage("https://example.invalid/");
  const data = input.data;

  if (!url || recognition.platform === "unsupported") {
    if (data?.tracked) {
      if (data.job?.status === "stale") return "stale_job";
      return "unsupported_site";
    }
    return "unsupported_site";
  }

  if (recognition.platform === "greenhouse" && !data?.tracked) {
    return input.ingesting ? "ingesting" : "supported_greenhouse";
  }
  if (recognition.platform === "lever" && !data?.tracked) {
    return input.ingesting ? "ingesting" : "supported_lever";
  }
  if (input.ingesting) return "ingesting";
  if (!data?.tracked) return "job_recognized";

  if (data.job?.status === "stale") return "stale_job";
  if (input.verifying) return "verification_running";
  if (input.autofillPreview) return "autofill_preview";

  if (data.score?.eligibility_status === "likely_ineligible") return "likely_ineligible";
  if (data.review_required || data.score?.eligibility_status === "eligibility_uncertain") {
    return "eligibility_review_required";
  }
  if (isVerifiedScore(data)) return "verified_fit_ready";
  if (data.score) return "potential_match";
  if (!data.materials_status || data.materials_status === "missing") return "materials_unavailable";
  if (data.apply_ready) return "ready_to_prepare";
  return "job_recognized";
}

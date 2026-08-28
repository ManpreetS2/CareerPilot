import { describe, expect, it } from "vitest";
import { API_BASE_URL } from "./config";
import { resumeVersionFileUrl } from "./api";

describe("resumeVersionFileUrl", () => {
  it("builds cookie-authenticated PDF and DOCX download URLs", () => {
    expect(resumeVersionFileUrl("rv-1", "pdf")).toBe(
      `${API_BASE_URL}/api/resume-versions/rv-1/file?format=pdf`,
    );
    expect(resumeVersionFileUrl("rv-1", "docx")).toBe(
      `${API_BASE_URL}/api/resume-versions/rv-1/file?format=docx`,
    );
  });

  it("encodes the version identifier", () => {
    expect(resumeVersionFileUrl("rv/1", "pdf")).toBe(
      `${API_BASE_URL}/api/resume-versions/rv%2F1/file?format=pdf`,
    );
  });
});

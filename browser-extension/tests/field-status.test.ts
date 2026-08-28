import { describe, expect, it } from "vitest";
import { classifyAutofillFields, SENSITIVE_EEO_KEYS } from "../src/field-status";

describe("autofill field status", () => {
  it("marks identity and profile links Ready, essays Needs review, EEO Manual, resume Unsupported", () => {
    const rows = classifyAutofillFields({
      full_name: "Ada Lovelace",
      email: "ada@example.com",
      linkedin_url: "https://linkedin.com/in/ada",
      work_authorization: "Authorized",
      cover_letter: "Dear team,",
      gender: "decline",
    });
    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.full_name.status).toBe("Ready");
    expect(byKey.email.status).toBe("Ready");
    expect(byKey.linkedin_url.status).toBe("Ready");
    expect(byKey.work_authorization.status).toBe("Needs review");
    expect(byKey.cover_letter.status).toBe("Needs review");
    expect(byKey.gender.status).toBe("Manual");
    expect(byKey.gender.label).toContain("EEO");
    expect(byKey.resume.status).toBe("Unsupported");
  });

  it("always lists sensitive EEO keys as Manual even when values exist", () => {
    expect(SENSITIVE_EEO_KEYS).toEqual(["gender", "race_ethnicity", "veteran_status", "disability_status"]);
    const rows = classifyAutofillFields({
      gender: "Female",
      race_ethnicity: "Prefer not to say",
      veteran_status: "No",
      disability_status: "No",
    });
    for (const key of SENSITIVE_EEO_KEYS) {
      expect(rows.find((row) => row.key === key)?.status).toBe("Manual");
    }
  });
});

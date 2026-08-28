// fillFormInPage is self-contained DOM manipulation (see the comment at the
// top of fillForm.ts) — no chrome.* calls inside it — so it can be driven
// directly against a jsdom document without mocking the extension runtime.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fillFormInPage } from "../src/fillForm";

const here = dirname(fileURLToPath(import.meta.url));

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

describe("fillForm safety", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("never calls form.submit or Enter in source", () => {
    const source = readFileSync(join(here, "../src/fillForm.ts"), "utf8");
    const code = stripComments(source);
    expect(code).not.toMatch(/\.submit\s*\(/);
    expect(code).not.toMatch(/press\s*\(\s*["']Enter["']\s*\)/);
    expect(code).not.toMatch(/type\s*=\s*["']submit["']/);
  });

  it("fills safe fields, leaves EEO manual, and never submits", async () => {
    document.body.innerHTML = `
      <form id="application_form">
        <label for="email">Email</label>
        <input id="email" name="job_application[email]" />
        <label for="gender">Gender</label>
        <select id="gender">
          <option value="">Select...</option>
          <option value="Female">Female</option>
          <option value="Male">Male</option>
        </select>
        <button type="submit" id="submit_app">Submit Application</button>
      </form>`;
    const form = document.getElementById("application_form") as HTMLFormElement;
    const submitSpy = vi.spyOn(form, "submit").mockImplementation(() => undefined);
    const clickSpy = vi.fn();
    document.getElementById("submit_app")!.addEventListener("click", clickSpy);

    const result = await fillFormInPage({
      platform: "greenhouse",
      fields: {
        email: "ada@example.com",
        gender: "Female",
        race_ethnicity: "Decline",
        veteran_status: "No",
        disability_status: "No",
      },
    });

    expect((document.getElementById("email") as HTMLInputElement).value).toBe("ada@example.com");
    expect((document.getElementById("gender") as HTMLSelectElement).value).toBe("");
    expect(result.filled.some((row) => row.name === "email")).toBe(true);
    expect(result.filled.some((row) => String(row.name).toLowerCase().includes("gender"))).toBe(false);
    expect(result.flagged.some((row) => row.name === "gender")).toBe(true);
    expect(submitSpy).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });
});

describe("fillFormInPage — EEO questions", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("never auto-answers gender, race/ethnicity, veteran, or disability questions", async () => {
    document.body.innerHTML = `
      <form>
        <label for="gender">Gender</label>
        <select id="gender">
          <option value="">Select...</option>
          <option value="Male">Male</option>
          <option value="Female">Female</option>
        </select>
        <label for="veteran">Veteran Status</label>
        <select id="veteran">
          <option value="">Select...</option>
          <option value="I am not a protected veteran">I am not a protected veteran</option>
        </select>
      </form>
    `;

    const { filled, flagged } = await fillFormInPage({
      platform: "greenhouse",
      fields: {
        gender: "Female",
        veteran_status: "I am not a protected veteran",
      },
    });

    expect((document.getElementById("gender") as HTMLSelectElement).value).toBe("");
    expect((document.getElementById("veteran") as HTMLSelectElement).value).toBe("");
    expect(filled.some((f) => f.name === "gender")).toBe(false);
    expect(filled.some((f) => f.name === "veteran status")).toBe(false);
    expect(flagged.some((f) => f.name === "gender")).toBe(true);
    expect(flagged.some((f) => f.name === "veteran status")).toBe(true);
  });

  it("does not flag an EEO question that isn't present on the page", async () => {
    document.body.innerHTML = `
      <form>
        <label for="first_name">First Name</label>
        <input id="first_name" name="first_name" />
      </form>
    `;

    const { flagged } = await fillFormInPage({
      platform: "greenhouse",
      fields: { gender: "Female" },
    });

    expect(flagged.some((f) => f.name === "gender")).toBe(false);
  });
});

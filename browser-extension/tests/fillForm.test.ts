// fillFormInPage is self-contained DOM manipulation (see the comment at the
// top of fillForm.ts) — no chrome.* calls inside it — so it can be driven
// directly against a jsdom document without mocking the extension runtime.
import { afterEach, describe, expect, it } from "vitest";
import { fillFormInPage } from "../src/fillForm";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("fillFormInPage — EEO questions", () => {
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

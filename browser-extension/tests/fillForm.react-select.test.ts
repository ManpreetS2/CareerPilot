import { afterEach, describe, expect, it, vi } from "vitest";
import { fillFormInPage } from "../src/fillForm";

/**
 * Realistic Greenhouse Job Board react-select markup:
 * combobox input id `react-select-N-input`, options `react-select-N-option-i`.
 * The old bug built `react-select-react-select-N-input-option-*` and found nothing.
 */
function mountReactSelectField(opts: {
  instance: number;
  label: string;
  labelFor?: string;
  options: string[];
  includeAriaControls?: boolean;
}): { getDisplayed: () => string; getSelected: () => string | null } {
  const inputId = `react-select-${opts.instance}-input`;
  const listboxId = `react-select-${opts.instance}-listbox`;
  const labelFor = opts.labelFor ?? inputId;
  const aria = opts.includeAriaControls === false ? "" : ` aria-controls="${listboxId}"`;

  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="select__container" data-field="${opts.label}">
      <label for="${labelFor}">${opts.label}</label>
      <div class="select__control">
        <div class="select__value-container">
          <div class="select__placeholder">Select...</div>
          <div class="select__single-value" hidden></div>
          <input id="${inputId}" role="combobox" aria-autocomplete="list"${aria} aria-expanded="false" />
        </div>
      </div>
      <div id="${listboxId}" class="select__menu" role="listbox" hidden>
        ${opts.options
          .map(
            (text, i) =>
              `<div class="select__option" role="option" id="react-select-${opts.instance}-option-${i}" aria-selected="false">${text}</div>`,
          )
          .join("")}
      </div>
    </div>`;
  document.body.appendChild(wrap);

  const input = document.getElementById(inputId) as HTMLInputElement;
  const menu = document.getElementById(listboxId) as HTMLElement;
  const single = wrap.querySelector(".select__single-value") as HTMLElement;
  const placeholder = wrap.querySelector(".select__placeholder") as HTMLElement;
  const control = wrap.querySelector(".select__control") as HTMLElement;

  const open = () => {
    menu.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };
  control.addEventListener("mousedown", open);
  control.addEventListener("click", open);
  input.addEventListener("focus", open);

  for (const option of menu.querySelectorAll<HTMLElement>(".select__option")) {
    option.addEventListener("click", () => {
      for (const other of menu.querySelectorAll<HTMLElement>(".select__option")) {
        other.setAttribute("aria-selected", "false");
      }
      option.setAttribute("aria-selected", "true");
      single.textContent = option.textContent;
      single.hidden = false;
      placeholder.hidden = true;
      menu.hidden = true;
      input.setAttribute("aria-expanded", "false");
    });
  }

  return {
    getDisplayed: () => single.textContent || "",
    getSelected: () => menu.querySelector('[aria-selected="true"]')?.textContent ?? null,
  };
}

describe("Greenhouse react-select autofill", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  // jsdom lacks PointerEvent; Greenhouse open sequence uses it.
  if (typeof window.PointerEvent === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).PointerEvent = class PointerEvent extends MouseEvent {
      constructor(type: string, init?: MouseEventInit) {
        super(type, init);
      }
    };
  }

  it("fills graduation, enrollment, degree, and sponsorship via correct option ids", async () => {
    const graduation = mountReactSelectField({
      instance: 2,
      label: "Expected graduation date",
      options: ["Select...", "May 2026", "December 2026", "May 2027"],
    });
    // Drop the placeholder-looking first option from the live menu for realism —
    // Greenhouse options are real answers only.
    document.getElementById("react-select-2-option-0")?.remove();

    const enrollment = mountReactSelectField({
      instance: 3,
      label: "Are you currently enrolled in a university or program?",
      options: ["Yes", "No"],
    });
    const degree = mountReactSelectField({
      instance: 4,
      label: "What degree are you pursuing?",
      options: ["Bachelor's", "Master's", "PhD"],
    });
    const sponsorship = mountReactSelectField({
      instance: 5,
      label: "Will you now or in the future require sponsorship?",
      options: ["Yes", "No"],
    });
    // EEO must stay manual even when present as react-select.
    mountReactSelectField({
      instance: 6,
      label: "Gender",
      options: ["Male", "Female", "Decline to self-identify"],
    });

    // Prove the buggy selector would find nothing for instance 2.
    const input = document.getElementById("react-select-2-input")!;
    const buggy = document.querySelectorAll(`[id^="react-select-${input.id}-option-"]`);
    expect(buggy.length).toBe(0);
    const fixedPrefix = input.id.replace(/-input$/, "");
    expect(document.querySelectorAll(`[id^="${fixedPrefix}-option-"]`).length).toBeGreaterThan(0);

    const result = await fillFormInPage({
      platform: "greenhouse",
      fields: {
        email: "ada@example.com",
        expected_graduation: "May 2027",
        currently_enrolled_in_program: "Yes",
        degree_pursuing: "Bachelor's",
        sponsorship_required: false,
        gender: "Female",
      },
    });

    expect(graduation.getDisplayed()).toBe("May 2027");
    expect(enrollment.getDisplayed()).toBe("Yes");
    expect(degree.getDisplayed()).toBe("Bachelor's");
    expect(sponsorship.getDisplayed()).toBe("No");
    expect(result.filled.map((f) => f.name)).toEqual(
      expect.arrayContaining([
        "expected graduation",
        "currently enrolled in program",
        "degree pursuing",
        "sponsorship required",
      ]),
    );
    expect(result.filled.some((f) => String(f.name).toLowerCase().includes("gender"))).toBe(false);
    expect(result.flagged.some((f) => f.name === "gender")).toBe(true);
    expect(document.querySelector('[data-field="Gender"] .select__single-value')?.textContent || "").toBe("");
  });

  it("refuses ambiguous substring matches instead of guessing", async () => {
    mountReactSelectField({
      instance: 7,
      label: "What degree are you pursuing?",
      options: ["Bachelor's Degree", "Bachelor of Science", "Master's"],
    });

    const result = await fillFormInPage({
      platform: "greenhouse",
      fields: { degree_pursuing: "Bachelor" },
    });

    expect(result.filled.some((f) => f.name === "degree pursuing")).toBe(false);
    expect(document.querySelector('[data-field="What degree are you pursuing?"] .select__single-value')?.textContent || "").toBe(
      "",
    );
  });

  it("still resolves options when aria-controls is missing, using the -input suffix strip", async () => {
    const degree = mountReactSelectField({
      instance: 8,
      label: "Degree",
      options: ["Associate's", "Bachelor's", "Master's"],
      includeAriaControls: false,
    });

    const result = await fillFormInPage({
      platform: "greenhouse",
      fields: { degree_pursuing: "Master's" },
    });

    expect(degree.getDisplayed()).toBe("Master's");
    expect(result.filled.some((f) => f.name === "degree pursuing")).toBe(true);
  });

  it("never submits from a react-select Greenhouse form", async () => {
    document.body.innerHTML = `<form id="app"><button type="submit" id="submit_app">Submit Application</button></form>`;
    const form = document.getElementById("app") as HTMLFormElement;
    const submitSpy = vi.spyOn(form, "submit").mockImplementation(() => undefined);
    mountReactSelectField({
      instance: 9,
      label: "Will you require sponsorship?",
      options: ["Yes", "No"],
    });

    await fillFormInPage({
      platform: "greenhouse",
      fields: { sponsorship_required: true },
    });

    expect(submitSpy).not.toHaveBeenCalled();
  });
});

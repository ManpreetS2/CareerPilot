// Ported from the original browser-extension/popup.js (now retired in favor
// of the side panel) with no behavioral changes — see git history for that
// file if a byte-for-byte diff is ever needed. This function's contract is
// safety-critical: it is passed by reference to
// chrome.scripting.executeScript({ func: fillFormInPage, args: [data] }),
// which serializes and re-runs it inside the real page's own isolated
// context. That means it MUST stay fully self-contained — no reference to
// anything outside its own parameter and its own nested helpers, since
// Chrome does not carry this module's closure/imports along with it.
//
// Field-detection logic mirrors backend/services/form_fill_service.py:
// known selectors per platform first, falling back to matching an input by
// its associated label text, then flagging anything still required and
// unfilled. Never calls .submit() or simulates a keypress. The one
// exception to "no clicks" is Greenhouse's scoped "Enter manually" toggle
// for Cover Letter, which only reveals a text field — nothing that submits
// or navigates is ever clicked.

export async function fillFormInPage(data: {
  platform: string;
  fields: Record<string, unknown>;
}): Promise<{ filled: { name: string; value: unknown }[]; flagged: { name: string; reason: string }[] }> {
  // jsdom (and a few older engines) lack CSS.escape; ids we generate are
  // already react-select-safe, but escape before interpolating into selectors.
  function cssEscape(value: string): string {
    if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
      return CSS.escape(value);
    }
    return value.replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`);
  }

  function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
    const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) {
      setter.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function tryFillBySelectors(selectors: string[], value: string): boolean {
    for (const selector of selectors) {
      const el = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
      if (el) {
        setNativeValue(el, value);
        return true;
      }
    }
    return false;
  }

  function tryFillByLabel(patterns: string[], value: string): boolean {
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      let input: HTMLInputElement | HTMLTextAreaElement | null = null;
      if (label.htmlFor) input = document.getElementById(label.htmlFor) as HTMLInputElement | null;
      if (!input) input = label.querySelector("input, textarea");
      if (input) {
        setNativeValue(input, value);
        return true;
      }
    }
    return false;
  }

  // Pick exactly one confident option. Exact text wins; a single bidirectional
  // substring match is allowed; zero or multiple substring hits refuse rather
  // than guess (e.g. "Bachelor" must not pick between Bachelor's / Master's).
  function findUniqueOptionMatch<T extends { text: string; node: Element }>(
    candidates: T[],
    value: string,
  ): T | null {
    const needle = value.trim().toLowerCase();
    if (!needle) return null;
    const exact = candidates.filter((c) => c.text === needle);
    if (exact.length === 1) return exact[0];
    if (exact.length > 1) return null;
    const partial = candidates.filter((c) => c.text.includes(needle) || needle.includes(c.text));
    if (partial.length === 1) return partial[0];
    return null;
  }

  // <select> counterpart to tryFillByLabel. Tries an exact option match
  // first, then a case-insensitive substring match against the select's
  // option text (a saved answer like "May 2027" won't always match a
  // posting's exact option wording) — returns false rather than picking an
  // unconfident option when nothing matches closely enough.
  function trySelectByLabel(patterns: string[], value: string): boolean {
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      let select: HTMLSelectElement | null = null;
      if (label.htmlFor) select = document.getElementById(label.htmlFor) as HTMLSelectElement | null;
      if (!select) select = label.querySelector("select");
      if (!select || select.tagName !== "SELECT") continue;
      const options = [...select.options].map((o) => ({
        text: (o.textContent || "").trim().toLowerCase(),
        node: o as Element,
        value: o.value,
      }));
      const match = findUniqueOptionMatch(options, value);
      if (!match) continue;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")?.set;
      if (setter) {
        setter.call(select, match.value);
      } else {
        select.value = match.value;
      }
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    return false;
  }

  // Modern Greenhouse's "Select..." dropdowns (sponsorship, enrolled,
  // graduation, degree, and the EEO questions) are NOT native <select>
  // elements — confirmed live against a real posting that the page has
  // zero <select> tags at all. They're react-select widgets: a hidden
  // role="combobox" <input> the <label>'s "for" points to, opened by a
  // mousedown/mouseup/click on its "__control" ancestor, which renders a
  // menu of div.select__option elements (ids literally containing
  // "-option-", which is how react-select's own instance-scoped ids are
  // built, more stable to match on than Greenhouse's CSS class names).
  // trySelectByLabel (native <select>) is tried first since it's cheap and
  // correct for platforms/fixtures that do use real selects; this is the
  // Greenhouse-specific fallback for when that finds nothing. Selecting an
  // option here is a data-entry action exactly like setting a native
  // select's value or filling a text field — it never touches submit or
  // the privacy-policy checkbox, same boundary as revealAndFillCoverLetter.
  async function tryReactSelectByLabel(patterns: string[], value: string): Promise<boolean> {
    // Confirmed live: opening reliably needs the input actually focused
    // first, plus both pointer and mouse events — mousedown/mouseup/click
    // alone opened most instances but silently failed on some (e.g. the
    // Gender field) despite working on others (Sponsorship, Enrolled,
    // Degree) on the very same page.
    function fire(el: Element, type: string, Ctor?: typeof MouseEvent | typeof PointerEvent) {
      const EventCtor = Ctor || MouseEvent;
      // Omit `view: window` — jsdom rejects it, and Chrome accepts these
      // synthetic pointer/mouse events without an explicit view.
      try {
        el.dispatchEvent(new EventCtor(type, { bubbles: true, cancelable: true, button: 0 }));
      } catch {
        el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, button: 0 }));
      }
    }
    function openAndClick(el: Element) {
      fire(el, "pointerdown", window.PointerEvent);
      fire(el, "mousedown");
      fire(el, "pointerup", window.PointerEvent);
      fire(el, "mouseup");
      fire(el, "click");
    }
    // react-select ids are `react-select-<instance>-input` for the combobox
    // and `react-select-<instance>-option-<n>` for options — NOT
    // `react-select-<full-input-id>-option-*` (that produced the broken
    // selector react-select-react-select-2-input-option-0). Prefer the
    // combobox's aria-controls listbox when present; fall back to stripping
    // a trailing "-input" from the input id.
    function optionNodesForCombobox(input: Element): Element[] {
      const listboxId = input.getAttribute("aria-controls");
      if (listboxId) {
        const listbox = document.getElementById(listboxId);
        if (listbox) {
          const fromListbox = [...listbox.querySelectorAll('[role="option"]')];
          if (fromListbox.length > 0) return fromListbox;
        }
      }
      const inputId = input.id || "";
      const instancePrefix = inputId.endsWith("-input") ? inputId.slice(0, -"-input".length) : inputId;
      if (!instancePrefix) return [];
      return [...document.querySelectorAll(`[id^="${cssEscape(instancePrefix)}-option-"]`)];
    }
    function reactSelectDisplays(input: Element, expected: string): boolean {
      const needle = expected.trim().toLowerCase();
      if (!needle) return false;
      const root = input.closest('[class*="select"]') || input.parentElement;
      const shown =
        root?.querySelector('[class*="single-value"]')?.textContent ||
        root?.querySelector('[class*="__value-container"]')?.textContent ||
        "";
      const text = shown.trim().toLowerCase();
      if (!text || text === "select..." || text === "select") return false;
      return text === needle || text.includes(needle) || needle.includes(text);
    }
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      const input = label.htmlFor ? document.getElementById(label.htmlFor) : null;
      if (!input || input.getAttribute("role") !== "combobox") continue;
      const control = input.closest('[class*="__control"]') || input.parentElement;
      (input as HTMLElement).focus();
      if (control) openAndClick(control);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const options = optionNodesForCombobox(input).map((o) => ({
        text: (o.textContent || "").trim().toLowerCase(),
        node: o,
      }));
      if (options.length === 0) {
        (input as HTMLElement).blur();
        continue;
      }
      const match = findUniqueOptionMatch(options, value);
      if (!match) {
        (input as HTMLElement).blur();
        continue;
      }
      openAndClick(match.node);
      await new Promise((resolve) => setTimeout(resolve, 30));
      // Only report success when the widget actually reflects the choice —
      // a click that missed (or hit the wrong menu) must not count as filled.
      // Greenhouse may keep aria-selected on the option and/or paint the
      // single-value label; either verified signal is enough.
      if (reactSelectDisplays(input, value) || match.node.getAttribute("aria-selected") === "true") {
        return true;
      }
      (input as HTMLElement).blur();
    }
    return false;
  }

  async function trySelectOrReactSelectByLabel(patterns: string[], value: string): Promise<boolean> {
    if (trySelectByLabel(patterns, value)) return true;
    if (platform === "greenhouse") return tryReactSelectByLabel(patterns, value);
    return false;
  }

  // Fields with no stable per-platform selector on either ATS — label-text
  // matching is the only approach that works across postings, same as
  // location/linkedin/github above. Deliberately excludes: Country,
  // "how did you hear about this job", essay questions, area-of-interest
  // choices, date-range-specific internship availability (would go stale),
  // and any policy/terms acknowledgment checkbox — accepting an agreement
  // stays a deliberate human click on every application, never something
  // this extension answers on the candidate's behalf.
  async function fillSharedReusableFields() {
    if (fields.legal_name && tryFillByLabel(["legal\\s*name"], fields.legal_name as string)) {
      filled.push({ name: "legal name", value: fields.legal_name });
    }
    if (
      fields.earliest_start_date &&
      tryFillByLabel(["start\\s*date", "available.*start", "earliest.*start"], fields.earliest_start_date as string)
    ) {
      filled.push({ name: "earliest start date", value: fields.earliest_start_date });
    }
    if (
      fields.expected_graduation &&
      (await trySelectOrReactSelectByLabel(["graduat"], fields.expected_graduation as string))
    ) {
      filled.push({ name: "expected graduation", value: fields.expected_graduation });
    }
    if (fields.degree_pursuing && (await trySelectOrReactSelectByLabel(["degree"], fields.degree_pursuing as string))) {
      filled.push({ name: "degree pursuing", value: fields.degree_pursuing });
    }
    if (
      fields.currently_enrolled_in_program &&
      (await trySelectOrReactSelectByLabel(["currently\\s*enrolled"], fields.currently_enrolled_in_program as string))
    ) {
      filled.push({ name: "currently enrolled in program", value: fields.currently_enrolled_in_program });
    }
    if (fields.sponsorship_required !== null && fields.sponsorship_required !== undefined) {
      const answer = fields.sponsorship_required ? "Yes" : "No";
      if (await trySelectOrReactSelectByLabel(["sponsorship"], answer)) {
        filled.push({ name: "sponsorship required", value: answer });
      }
    }
    // Gender, race/ethnicity, veteran, and disability status are never
    // auto-answered, regardless of whether a value is on file: label-text
    // matching here is a loose heuristic (e.g. "veteran" or "hispanic" as a
    // bare substring), not a verified mapping to this posting's exact
    // options, and these are protected-class questions where a wrong or
    // unconfirmed answer carries real consequences. Always flag for the
    // candidate to answer themselves rather than infer or guess.
    const eeoFields: [string, string, string[]][] = [
      ["gender", "Gender", ["^gender$"]],
      ["race_ethnicity", "Race/ethnicity", ["hispanic", "latino", "ethnicity"]],
      ["veteran_status", "Veteran status", ["veteran"]],
      ["disability_status", "Disability status", ["disability"]],
    ];
    const labelTexts = [...document.querySelectorAll("label")].map((l) => l.textContent || "");
    for (const [key, label, patterns] of eeoFields) {
      const present = patterns.some((pattern) => {
        const re = new RegExp(pattern, "i");
        return labelTexts.some((text) => re.test(text));
      });
      if (present) {
        flagged.push({
          name: key.replace(/_/g, " "),
          reason: `${label} is a sensitive question — answer it yourself rather than have it auto-filled.`,
        });
      }
    }
  }

  function nearestLabelText(el: Element): string | null {
    let node: Element | null = el;
    for (let i = 0; i < 6 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const label = node.querySelector("label");
      if (label && label.textContent!.trim()) {
        return label.textContent!.trim().replace(/\*$/, "").trim();
      }
    }
    return null;
  }

  // Greenhouse's Cover Letter section offers "Attach" or "Enter manually" —
  // the text field doesn't exist in the DOM until "Enter manually" is
  // clicked (confirmed live: the textarea is absent before, present after).
  // The Resume section has an identically-labeled button, so this only
  // clicks the one whose nearest ancestor text starts with "Cover Letter".
  // Excludes the page's unrelated reCAPTCHA textarea rather than filling
  // "any textarea" once one is revealed.
  async function revealAndFillCoverLetter(value: string): Promise<boolean> {
    const buttons = [...document.querySelectorAll("button")].filter((b) => (b.textContent || "").trim() === "Enter manually");
    for (const button of buttons) {
      let node: Element | null = button;
      let inCoverLetterSection = false;
      for (let i = 0; i < 8 && node; i++) {
        if ((node.textContent || "").trim().startsWith("Cover Letter")) {
          inCoverLetterSection = true;
          break;
        }
        node = node.parentElement;
      }
      if (!inCoverLetterSection) continue;
      button.click();
      await new Promise((resolve) => setTimeout(resolve, 50));
      const textareas = [...document.querySelectorAll("textarea")].filter(
        (t) => t.getAttribute("name") !== "g-recaptcha-response",
      );
      const textarea = textareas[textareas.length - 1];
      if (!textarea) return false;
      setNativeValue(textarea, value);
      return true;
    }
    return false;
  }

  const filled: { name: string; value: unknown }[] = [];
  const flagged: { name: string; reason: string }[] = [];
  const fields = data.fields || {};
  const platform = data.platform;

  const selectorSets =
    platform === "greenhouse"
      ? {
          fullName: ["#full_name", "input[name='job_application[full_name]']"],
          firstName: ["#first_name", "input[name='job_application[first_name]']"],
          lastName: ["#last_name", "input[name='job_application[last_name]']"],
          email: ["#email", "input[name='job_application[email]']"],
          phone: ["#phone", "input[name='job_application[phone]']"],
          company: ["#company", "input[name='job_application[company]']"],
          location: [] as string[],
          linkedin: [] as string[],
          github: [] as string[],
          portfolio: [] as string[],
          coverLetter: ["#cover_letter_text", "textarea[name*='cover_letter']"],
          resume: ["#resume", "input[name='job_application[resume]']", "input[name='resume']"],
        }
      : {
          fullName: ["input[name='name']"],
          firstName: [] as string[],
          lastName: [] as string[],
          email: ["input[name='email']"],
          phone: ["input[name='phone']"],
          company: ["input[name='org']"],
          location: ["input[name='location']"],
          linkedin: ["input[name='urls[LinkedIn]']"],
          github: ["input[name='urls[GitHub]']"],
          portfolio: ["input[name='urls[Portfolio]']"],
          coverLetter: ["textarea[name='comments']"],
          resume: ["input[name='resume']", "#resume"],
        };

  const fullName = fields.full_name as string | undefined;
  const firstName = fields.first_name as string | undefined;
  const lastName = fields.last_name as string | undefined;

  if (fullName && tryFillBySelectors(selectorSets.fullName, fullName)) {
    filled.push({ name: "full name", value: fullName });
  } else {
    const firstOk = firstName && tryFillBySelectors(selectorSets.firstName, firstName);
    const lastOk = lastName && tryFillBySelectors(selectorSets.lastName, lastName);
    if (firstOk || (firstName && tryFillByLabel(["first\\s*name"], firstName))) {
      filled.push({ name: "first name", value: firstName });
    } else if (firstName) {
      flagged.push({ name: "first name", reason: "no matching field found" });
    }
    if (lastOk || (lastName && tryFillByLabel(["last\\s*name"], lastName))) {
      filled.push({ name: "last name", value: lastName });
    } else if (lastName) {
      flagged.push({ name: "last name", reason: "no matching field found" });
    }
  }

  const email = fields.email as string | undefined;
  if (email) {
    if (tryFillBySelectors(selectorSets.email, email) || tryFillByLabel(["email"], email)) {
      filled.push({ name: "email", value: email });
    } else {
      flagged.push({ name: "email", reason: "no matching field found" });
    }
  } else {
    flagged.push({ name: "email", reason: "candidate profile has no email on file" });
  }

  const phone = fields.phone as string | undefined;
  if (phone) {
    if (tryFillBySelectors(selectorSets.phone, phone) || tryFillByLabel(["phone"], phone)) {
      filled.push({ name: "phone", value: phone });
    } else {
      flagged.push({ name: "phone", reason: "no matching field found" });
    }
  }

  const currentCompany = fields.current_company as string | undefined;
  if (currentCompany) {
    const ok =
      tryFillBySelectors(selectorSets.company, currentCompany) ||
      tryFillByLabel(["current\\s*company", "^company$"], currentCompany);
    if (ok) filled.push({ name: "current company", value: currentCompany });
  }

  const location = fields.location as string | undefined;
  if (location) {
    const ok = tryFillBySelectors(selectorSets.location, location) || tryFillByLabel(["location.*city", "^location$"], location);
    if (ok) filled.push({ name: "location", value: location });
  }

  const linkedinUrl = fields.linkedin_url as string | undefined;
  if (linkedinUrl) {
    const ok = tryFillBySelectors(selectorSets.linkedin, linkedinUrl) || tryFillByLabel(["linkedin"], linkedinUrl);
    if (ok) filled.push({ name: "LinkedIn profile", value: linkedinUrl });
  }

  const githubUrl = fields.github_url as string | undefined;
  if (githubUrl) {
    const ok = tryFillBySelectors(selectorSets.github, githubUrl) || tryFillByLabel(["github"], githubUrl);
    if (ok) filled.push({ name: "GitHub profile", value: githubUrl });
  }

  const portfolioUrl = fields.portfolio_url as string | undefined;
  if (portfolioUrl) {
    const ok = tryFillBySelectors(selectorSets.portfolio, portfolioUrl) || tryFillByLabel(["portfolio", "website"], portfolioUrl);
    if (ok) filled.push({ name: "portfolio URL", value: portfolioUrl });
  }

  const coverLetter = fields.cover_letter as string | undefined;
  if (coverLetter) {
    if (tryFillBySelectors(selectorSets.coverLetter, coverLetter)) {
      filled.push({ name: "cover letter", value: coverLetter });
    } else if (platform === "greenhouse" && (await revealAndFillCoverLetter(coverLetter))) {
      filled.push({ name: "cover letter", value: coverLetter });
    } else {
      flagged.push({ name: "cover letter", reason: "no text field found — this posting may require a file upload instead" });
    }
  }

  const resumeInput = document.querySelector<HTMLInputElement>(selectorSets.resume.join(", "));
  if (resumeInput) {
    const attached = resumeInput.files?.[0];
    if (attached) {
      filled.push({ name: "resume", value: attached.name });
    } else {
      flagged.push({ name: "resume", reason: "attach your resume manually (no stored file to upload)" });
    }
  }

  await fillSharedReusableFields();

  const requiredEls = [...document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
    "input[required], textarea[required], select[required]",
  )].slice(0, 50);
  const alreadyLower = new Set([...filled, ...flagged].map((f) => f.name.toLowerCase()));
  for (const el of requiredEls) {
    if ((el.value || "").trim()) continue;
    const name =
      el.getAttribute("name") || el.getAttribute("id") || el.getAttribute("aria-label") || nearestLabelText(el) || "an unlabeled required field";
    if (alreadyLower.has(name.toLowerCase())) continue;
    flagged.push({ name, reason: "required field with no confident mapping" });
    alreadyLower.add(name.toLowerCase());
  }

  return { filled, flagged };
}

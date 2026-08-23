const BACKEND_URL = "http://localhost:8000";
// Must match backend/core/config.py's session_cookie_name / session_header_name.
const SESSION_COOKIE_NAME = "careerpilot_session";
const SESSION_HEADER_NAME = "X-CareerPilot-Session";

const button = document.getElementById("fill-btn");
const statusEl = document.getElementById("status");

button.addEventListener("click", () => {
  void runFill();
});

async function runFill() {
  button.disabled = true;
  statusEl.innerHTML = "Looking up this job…";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id || !tab.url) {
      throw new Error("Could not read the current tab.");
    }

    // The extension has no login UI of its own — it rides on whatever
    // session you already have from logging in at the CareerPilot web app
    // in a regular tab. It CANNOT get there via `credentials: "include"`
    // the way the web app does: this fetch is chrome-extension://<id> to
    // http://localhost:8000, a cross-site request from the browser's point
    // of view, and the session cookie is SameSite=Lax — Lax cookies only
    // ride along on top-level navigations, never on a subresource fetch
    // from a different site, so the browser would silently omit it here.
    // Instead, the privileged chrome.cookies API (not subject to that
    // restriction) reads the cookie's value directly, and it's sent back as
    // a header the backend also accepts (see get_current_user).
    const sessionCookie = await chrome.cookies.get({ url: BACKEND_URL, name: SESSION_COOKIE_NAME });
    if (!sessionCookie) {
      throw new Error("Log in to CareerPilot in your browser first, then try again.");
    }

    const response = await fetch(`${BACKEND_URL}/api/extension/autofill?url=${encodeURIComponent(tab.url)}`, {
      headers: { [SESSION_HEADER_NAME]: sessionCookie.value },
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      throw new Error("Log in to CareerPilot in your browser first, then try again.");
    }
    if (!response.ok) {
      throw new Error(body.detail || `Request failed (${response.status})`);
    }

    statusEl.innerHTML = "Filling the form…";

    const injection = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillFormInPage,
      args: [body],
    }); // executeScript awaits fillFormInPage's returned promise before resolving `result`

    renderResult(injection?.[0]?.result);
  } catch (err) {
    statusEl.innerHTML = `<span class="error">${escapeHtml(err instanceof Error ? err.message : String(err))}</span>`;
  } finally {
    button.disabled = false;
  }
}

function renderResult(result) {
  if (!result) {
    statusEl.innerHTML = '<span class="error">No result returned from the page.</span>';
    return;
  }
  const parts = [];
  if (result.filled.length > 0) {
    parts.push(
      '<div class="section-title">Filled automatically</div><ul>' +
        result.filled.map((f) => `<li class="filled-item">${escapeHtml(f.name)}</li>`).join("") +
        "</ul>",
    );
  }
  if (result.flagged.length > 0) {
    parts.push(
      '<div class="section-title">Needs your input</div><ul>' +
        result.flagged
          .map((f) => `<li class="flagged-item">${escapeHtml(f.name)} — ${escapeHtml(f.reason)}</li>`)
          .join("") +
        "</ul>",
    );
  }
  statusEl.innerHTML = parts.join("") || "Nothing on this page matched.";
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

/**
 * Runs inside the real page via chrome.scripting.executeScript — cannot
 * reference anything from popup.js's own scope, only browser DOM APIs and
 * whatever's passed in `data`. Never calls .submit() or simulates a
 * keypress. The one exception to "no clicks" is Greenhouse's scoped
 * "Enter manually" toggle for Cover Letter, which only reveals a text
 * field — nothing that submits or navigates is ever clicked. Declared
 * async because that click needs a tick for the revealed textarea to
 * exist; chrome.scripting.executeScript awaits the returned promise
 * before resolving `result`, so the caller needs no change.
 *
 * Field-detection logic mirrors backend/services/form_fill_service.py:
 * known selectors per platform first, falling back to matching an input
 * by its associated label text, then flagging anything still required and
 * unfilled (using the nearest ancestor <label> as a human-readable name
 * when the field has no name/id/aria-label at all — needed for modern
 * Greenhouse's hidden validation-proxy inputs on custom questions).
 *
 * `filled`/`flagged` hold {name, value}/{name, reason} objects, not
 * pre-joined display strings — deduping against a joined "name — reason"
 * string would silently miss a match whenever the reason text differs
 * (e.g. a field already flagged for one reason, then found again by the
 * required-field sweep with a different generic reason, would otherwise
 * show up twice for the same field).
 */
async function fillFormInPage(data) {
  function setNativeValue(el, value) {
    const proto =
      el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) {
      setter.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function tryFillBySelectors(selectors, value) {
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) {
        setNativeValue(el, value);
        return true;
      }
    }
    return false;
  }

  function tryFillByLabel(patterns, value) {
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      let input = null;
      if (label.htmlFor) input = document.getElementById(label.htmlFor);
      if (!input) input = label.querySelector("input, textarea");
      if (input) {
        setNativeValue(input, value);
        return true;
      }
    }
    return false;
  }

  // <select> counterpart to tryFillByLabel. Tries an exact option match
  // first, then a case-insensitive substring match against the select's
  // option text (a saved answer like "May 2027" won't always match a
  // posting's exact option wording) — returns false rather than picking an
  // unconfident option when nothing matches closely enough.
  function trySelectByLabel(patterns, value) {
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      let select = null;
      if (label.htmlFor) select = document.getElementById(label.htmlFor);
      if (!select) select = label.querySelector("select");
      if (!select || select.tagName !== "SELECT") continue;
      const options = [...select.options];
      const needle = value.trim().toLowerCase();
      let match = options.find((o) => o.textContent.trim().toLowerCase() === needle);
      if (!match) {
        // Bidirectional: a saved value can be the more specific side ("Bachelor's
        // in Computer Science" vs. a plain option "Bachelor's") or the option can
        // be more specific ("Yes" vs. an option worded "Yes, I will need sponsorship").
        match = options.find((o) => {
          const text = o.textContent.trim().toLowerCase();
          return text.includes(needle) || needle.includes(text);
        });
      }
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
  async function tryReactSelectByLabel(patterns, value) {
    // Confirmed live: opening reliably needs the input actually focused
    // first, plus both pointer and mouse events — mousedown/mouseup/click
    // alone opened most instances but silently failed on some (e.g. the
    // Gender field) despite working on others (Sponsorship, Enrolled,
    // Degree) on the very same page.
    function fire(el, type, Ctor) {
      el.dispatchEvent(new (Ctor || MouseEvent)(type, { bubbles: true, cancelable: true, view: window, button: 0 }));
    }
    function openAndClick(el) {
      fire(el, "pointerdown", window.PointerEvent);
      fire(el, "mousedown");
      fire(el, "pointerup", window.PointerEvent);
      fire(el, "mouseup");
      fire(el, "click");
    }
    const labels = [...document.querySelectorAll("label")];
    for (const pattern of patterns) {
      const re = new RegExp(pattern, "i");
      const label = labels.find((l) => re.test(l.textContent || ""));
      if (!label) continue;
      const input = label.htmlFor ? document.getElementById(label.htmlFor) : null;
      if (!input || input.getAttribute("role") !== "combobox") continue;
      const control = input.closest('[class*="__control"]') || input.parentElement;
      input.focus();
      openAndClick(control);
      await new Promise((resolve) => setTimeout(resolve, 80));
      // Scoped to this specific combobox instance — react-select's option
      // ids embed the input's own id ("react-select-<input-id>-option-0"),
      // so this can't pick up a stale option from a different, still-open
      // menu (closing a menu via a synthetic "click outside" proved
      // unreliable, so instead of depending on that, every read is scoped
      // to only the menu that belongs to the field being filled right now).
      const options = [...document.querySelectorAll(`[id^="react-select-${CSS.escape(input.id)}-option-"]`)];
      if (options.length === 0) {
        input.blur();
        continue;
      }
      const needle = value.trim().toLowerCase();
      let match = options.find((o) => o.textContent.trim().toLowerCase() === needle);
      if (!match) {
        match = options.find((o) => {
          const text = o.textContent.trim().toLowerCase();
          return text.includes(needle) || needle.includes(text);
        });
      }
      if (!match) {
        input.blur();
        continue;
      }
      openAndClick(match);
      await new Promise((resolve) => setTimeout(resolve, 30));
      return true;
    }
    return false;
  }

  async function trySelectOrReactSelectByLabel(patterns, value) {
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
    if (fields.legal_name && tryFillByLabel(["legal\\s*name"], fields.legal_name)) {
      filled.push({ name: "legal name", value: fields.legal_name });
    }
    if (
      fields.earliest_start_date &&
      tryFillByLabel(["start\\s*date", "available.*start", "earliest.*start"], fields.earliest_start_date)
    ) {
      filled.push({ name: "earliest start date", value: fields.earliest_start_date });
    }
    if (fields.expected_graduation && (await trySelectOrReactSelectByLabel(["graduat"], fields.expected_graduation))) {
      filled.push({ name: "expected graduation", value: fields.expected_graduation });
    }
    if (fields.degree_pursuing && (await trySelectOrReactSelectByLabel(["degree"], fields.degree_pursuing))) {
      filled.push({ name: "degree pursuing", value: fields.degree_pursuing });
    }
    if (
      fields.currently_enrolled_in_program &&
      (await trySelectOrReactSelectByLabel(["currently\\s*enrolled"], fields.currently_enrolled_in_program))
    ) {
      filled.push({ name: "currently enrolled in program", value: fields.currently_enrolled_in_program });
    }
    if (fields.sponsorship_required !== null && fields.sponsorship_required !== undefined) {
      const answer = fields.sponsorship_required ? "Yes" : "No";
      if (await trySelectOrReactSelectByLabel(["sponsorship"], answer)) {
        filled.push({ name: "sponsorship required", value: answer });
      }
    }
    const eeoFields = [
      ["gender", ["^gender$"]],
      ["race_ethnicity", ["hispanic", "latino"]],
      ["veteran_status", ["veteran"]],
      ["disability_status", ["disability"]],
    ];
    for (const [key, patterns] of eeoFields) {
      const value = fields[key];
      if (value && (await trySelectOrReactSelectByLabel(patterns, value))) {
        filled.push({ name: key.replace(/_/g, " "), value });
      }
    }
  }

  function nearestLabelText(el) {
    let node = el;
    for (let i = 0; i < 6 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const label = node.querySelector("label");
      if (label && label.textContent.trim()) {
        return label.textContent.trim().replace(/\*$/, "").trim();
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
  async function revealAndFillCoverLetter(value) {
    const buttons = [...document.querySelectorAll("button")].filter(
      (b) => (b.textContent || "").trim() === "Enter manually",
    );
    for (const button of buttons) {
      let node = button;
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

  const filled = [];
  const flagged = [];
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
          location: [],
          linkedin: [],
          github: [],
          portfolio: [],
          coverLetter: ["#cover_letter_text", "textarea[name*='cover_letter']"],
          resume: ["#resume", "input[type='file']"],
        }
      : {
          fullName: ["input[name='name']"],
          firstName: [],
          lastName: [],
          email: ["input[name='email']"],
          phone: ["input[name='phone']"],
          company: ["input[name='org']"],
          location: ["input[name='location']"],
          linkedin: ["input[name='urls[LinkedIn]']"],
          github: ["input[name='urls[GitHub]']"],
          portfolio: ["input[name='urls[Portfolio]']"],
          coverLetter: ["textarea[name='comments']"],
          resume: ["input[name='resume']"],
        };

  if (fields.full_name && tryFillBySelectors(selectorSets.fullName, fields.full_name)) {
    filled.push({ name: "full name", value: fields.full_name });
  } else {
    const firstOk = fields.first_name && tryFillBySelectors(selectorSets.firstName, fields.first_name);
    const lastOk = fields.last_name && tryFillBySelectors(selectorSets.lastName, fields.last_name);
    if (firstOk || (fields.first_name && tryFillByLabel(["first\\s*name"], fields.first_name))) {
      filled.push({ name: "first name", value: fields.first_name });
    } else if (fields.first_name) {
      flagged.push({ name: "first name", reason: "no matching field found" });
    }
    if (lastOk || (fields.last_name && tryFillByLabel(["last\\s*name"], fields.last_name))) {
      filled.push({ name: "last name", value: fields.last_name });
    } else if (fields.last_name) {
      flagged.push({ name: "last name", reason: "no matching field found" });
    }
  }

  if (fields.email) {
    if (tryFillBySelectors(selectorSets.email, fields.email) || tryFillByLabel(["email"], fields.email)) {
      filled.push({ name: "email", value: fields.email });
    } else {
      flagged.push({ name: "email", reason: "no matching field found" });
    }
  } else {
    flagged.push({ name: "email", reason: "candidate profile has no email on file" });
  }

  if (fields.phone) {
    if (tryFillBySelectors(selectorSets.phone, fields.phone) || tryFillByLabel(["phone"], fields.phone)) {
      filled.push({ name: "phone", value: fields.phone });
    } else {
      flagged.push({ name: "phone", reason: "no matching field found" });
    }
  }

  if (fields.current_company) {
    const ok =
      tryFillBySelectors(selectorSets.company, fields.current_company) ||
      tryFillByLabel(["current\\s*company", "^company$"], fields.current_company);
    if (ok) filled.push({ name: "current company", value: fields.current_company });
  }

  if (fields.location) {
    const ok =
      tryFillBySelectors(selectorSets.location, fields.location) ||
      tryFillByLabel(["location.*city", "^location$"], fields.location);
    if (ok) filled.push({ name: "location", value: fields.location });
  }

  if (fields.linkedin_url) {
    const ok =
      tryFillBySelectors(selectorSets.linkedin, fields.linkedin_url) || tryFillByLabel(["linkedin"], fields.linkedin_url);
    if (ok) filled.push({ name: "LinkedIn profile", value: fields.linkedin_url });
  }

  if (fields.github_url) {
    const ok =
      tryFillBySelectors(selectorSets.github, fields.github_url) || tryFillByLabel(["github"], fields.github_url);
    if (ok) filled.push({ name: "GitHub profile", value: fields.github_url });
  }

  if (fields.portfolio_url) {
    const ok =
      tryFillBySelectors(selectorSets.portfolio, fields.portfolio_url) ||
      tryFillByLabel(["portfolio", "website"], fields.portfolio_url);
    if (ok) filled.push({ name: "portfolio URL", value: fields.portfolio_url });
  }

  if (fields.cover_letter) {
    if (tryFillBySelectors(selectorSets.coverLetter, fields.cover_letter)) {
      filled.push({ name: "cover letter", value: fields.cover_letter });
    } else if (platform === "greenhouse" && (await revealAndFillCoverLetter(fields.cover_letter))) {
      filled.push({ name: "cover letter", value: fields.cover_letter });
    } else {
      flagged.push({
        name: "cover letter",
        reason: "no text field found — this posting may require a file upload instead",
      });
    }
  }

  if (document.querySelector(selectorSets.resume.join(", "))) {
    flagged.push({ name: "resume", reason: "attach your resume manually (no stored file to upload)" });
  }

  await fillSharedReusableFields();

  const requiredEls = [
    ...document.querySelectorAll("input[required], textarea[required], select[required]"),
  ].slice(0, 50);
  const alreadyLower = new Set([...filled, ...flagged].map((f) => f.name.toLowerCase()));
  for (const el of requiredEls) {
    if ((el.value || "").trim()) continue;
    const name =
      el.getAttribute("name") ||
      el.getAttribute("id") ||
      el.getAttribute("aria-label") ||
      nearestLabelText(el) ||
      "an unlabeled required field";
    if (alreadyLower.has(name.toLowerCase())) continue;
    flagged.push({ name, reason: "required field with no confident mapping" });
    alreadyLower.add(name.toLowerCase());
  }

  return { filled, flagged };
}

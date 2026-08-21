const BACKEND_URL = "http://localhost:8000";

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

    const response = await fetch(`${BACKEND_URL}/api/extension/autofill?url=${encodeURIComponent(tab.url)}`);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || `Request failed (${response.status})`);
    }

    statusEl.innerHTML = "Filling the form…";

    const injection = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: fillFormInPage,
      args: [body],
    });

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
 * whatever's passed in `data`. Never calls .click(), .submit(), or
 * simulates a keypress — this fills fields and stops there.
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
function fillFormInPage(data) {
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

  if (fields.portfolio_url) {
    const ok = tryFillBySelectors(
      ["input[name='urls[Portfolio]']", "input[name='urls[LinkedIn]']", "input[name='urls[GitHub]']"],
      fields.portfolio_url,
    );
    if (ok) filled.push({ name: "portfolio URL", value: fields.portfolio_url });
  }

  if (fields.cover_letter) {
    if (tryFillBySelectors(selectorSets.coverLetter, fields.cover_letter)) {
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

export type FileFieldKind = "resume" | "cover_letter" | "unsupported";

export type AttachDocumentPayload = {
  kind: "resume";
  filename: string;
  mimeType: string;
  bytesBase64: string;
};

export type AttachDocumentResult = {
  status: "attached" | "manual" | "failed" | "ambiguous" | "unsupported_field";
  fieldKind: FileFieldKind | null;
  verifiedName: string | null;
  reason: string | null;
};

const RESUME_NAME_RE = /(resume|curriculum vitae|\bcv\b)/i;
const COVER_LETTER_NAME_RE = /cover[\s_-]*letter/i;

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function nearestLabel(el: Element): string {
  if (el instanceof HTMLInputElement && el.labels && el.labels[0]?.textContent) {
    return el.labels[0].textContent;
  }
  const id = el.getAttribute("id");
  if (id) {
    const byFor = document.querySelector(`label[for="${cssEscape(id)}"]`);
    if (byFor?.textContent) return byFor.textContent;
  }
  const wrapped = el.closest("label");
  if (wrapped?.textContent) return wrapped.textContent;
  let sibling = el.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === "LABEL" && sibling.textContent) return sibling.textContent;
    sibling = sibling.previousElementSibling;
  }
  const parent = el.parentElement;
  if (parent) {
    for (const child of [...parent.children]) {
      if (child.tagName !== "LABEL") continue;
      const htmlFor = child.getAttribute("for");
      if (htmlFor && htmlFor !== id) continue;
      if (child.textContent) return child.textContent;
    }
  }
  return `${el.getAttribute("name") || ""} ${el.getAttribute("id") || ""} ${el.getAttribute("aria-label") || ""}`;
}

/** Test helper. The injected attach function inlines the same rules. */
export function classifyFileInput(input: HTMLInputElement): FileFieldKind {
  const self = `${input.name} ${input.id} ${input.getAttribute("aria-label") || ""}`;
  if (COVER_LETTER_NAME_RE.test(self) && !RESUME_NAME_RE.test(self)) return "cover_letter";
  if (
    RESUME_NAME_RE.test(self) ||
    input.id === "resume" ||
    input.name === "resume" ||
    (input.name || "").includes("job_application[resume]")
  ) {
    return "resume";
  }
  const label = nearestLabel(input);
  if (COVER_LETTER_NAME_RE.test(label) && !RESUME_NAME_RE.test(label)) return "cover_letter";
  if (RESUME_NAME_RE.test(label)) return "resume";
  return "unsupported";
}

export function classifyFileInputs(root: ParentNode = document): {
  resume: HTMLInputElement[];
  coverLetter: HTMLInputElement[];
  unsupported: HTMLInputElement[];
} {
  const resume: HTMLInputElement[] = [];
  const coverLetter: HTMLInputElement[] = [];
  const unsupported: HTMLInputElement[] = [];
  for (const input of [...root.querySelectorAll<HTMLInputElement>("input[type='file']")]) {
    const kind = classifyFileInput(input);
    if (kind === "resume") resume.push(input);
    else if (kind === "cover_letter") coverLetter.push(input);
    else unsupported.push(input);
  }
  return { resume, coverLetter, unsupported };
}

/**
 * Injected into the job page. Must stay self-contained — Chrome does not
 * serialize this module's other exports with the function.
 */
export async function attachDocumentInPage(payload: AttachDocumentPayload): Promise<AttachDocumentResult> {
  const resumeNameRe = /(resume|curriculum vitae|\bcv\b)/i;
  const coverLetterNameRe = /cover[\s_-]*letter/i;

  function fieldLabel(el: Element): string {
    if (el instanceof HTMLInputElement && el.labels && el.labels[0]?.textContent) {
      return el.labels[0].textContent;
    }
    const id = el.getAttribute("id");
    if (id) {
      const css =
        typeof CSS !== "undefined" && typeof CSS.escape === "function"
          ? CSS.escape(id)
          : id.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      const byFor = document.querySelector(`label[for="${css}"]`);
      if (byFor?.textContent) return byFor.textContent;
    }
    const wrapped = el.closest("label");
    if (wrapped?.textContent) return wrapped.textContent;
    let sibling = el.previousElementSibling;
    while (sibling) {
      if (sibling.tagName === "LABEL" && sibling.textContent) return sibling.textContent;
      sibling = sibling.previousElementSibling;
    }
    const parent = el.parentElement;
    if (parent) {
      for (const child of [...parent.children]) {
        if (child.tagName !== "LABEL") continue;
        const htmlFor = child.getAttribute("for");
        if (htmlFor && htmlFor !== id) continue;
        if (child.textContent) return child.textContent;
      }
    }
    return `${el.getAttribute("name") || ""} ${el.getAttribute("id") || ""}`;
  }

  function classify(input: HTMLInputElement): "resume" | "cover_letter" | "unsupported" {
    const self = `${input.name} ${input.id} ${input.getAttribute("aria-label") || ""}`;
    if (coverLetterNameRe.test(self) && !resumeNameRe.test(self)) return "cover_letter";
    if (
      resumeNameRe.test(self) ||
      input.id === "resume" ||
      input.name === "resume" ||
      (input.name || "").includes("job_application[resume]")
    ) {
      return "resume";
    }
    const label = fieldLabel(input);
    if (coverLetterNameRe.test(label) && !resumeNameRe.test(label)) return "cover_letter";
    if (resumeNameRe.test(label)) return "resume";
    return "unsupported";
  }

  function acceptAllows(input: HTMLInputElement, mimeType: string, filename: string): boolean {
    const accept = (input.getAttribute("accept") || "").trim();
    if (!accept) return true;
    const tokens = accept.split(",").map((token) => token.trim().toLowerCase());
    const ext = filename.includes(".") ? `.${filename.split(".").pop()!.toLowerCase()}` : "";
    if (tokens.includes(mimeType.toLowerCase())) return true;
    if (ext && tokens.includes(ext)) return true;
    if (mimeType === "application/pdf" && tokens.some((token) => token.includes("pdf"))) return true;
    if (
      mimeType.includes("wordprocessingml") &&
      tokens.some((token) => token.includes("docx") || token.includes("word"))
    ) {
      return true;
    }
    return false;
  }

  function decodeFile(): File {
    const binary = atob(payload.bytesBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new File([bytes], payload.filename, { type: payload.mimeType });
  }

  function assignFiles(input: HTMLInputElement, file: File): boolean {
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    } catch {
      return false;
    }
  }

  function hasName(input: HTMLInputElement, filename: string): boolean {
    const list = input.files;
    const first = list && list.length > 0 ? list[0] : null;
    return Boolean(first && first.name === filename);
  }

  function isResumeHeadingText(text: string, filename: string): boolean {
    const t = (text || "").replace(/\s+/g, " ").trim();
    if (!t || t === filename || t.length > 64) return false;
    if (coverLetterNameRe.test(t)) return false;
    return resumeNameRe.test(t);
  }

  function isCoverLetterHeadingText(text: string): boolean {
    const t = (text || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 64) return false;
    return coverLetterNameRe.test(t) && !resumeNameRe.test(t);
  }

  function resumeGroupShowsFilename(filename: string): boolean {
    const filenameNodes = [...document.querySelectorAll("*")].filter((el) => {
      if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return false;
      const ownText = [...el.childNodes]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => (node.textContent || "").trim())
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (ownText === filename) return true;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      return el.children.length === 0 && text === filename;
    });
    for (const node of filenameNodes) {
      let ancestor: Element | null = node;
      for (let i = 0; i < 8 && ancestor; i += 1) {
        const labelledBy = ancestor.getAttribute("aria-labelledby");
        const labelled = labelledBy ? document.getElementById(labelledBy)?.textContent || "" : "";
        const ariaLabel = ancestor.getAttribute("aria-label") || "";
        if (isCoverLetterHeadingText(labelled) || isCoverLetterHeadingText(ariaLabel)) break;
        if (isResumeHeadingText(labelled, filename) || isResumeHeadingText(ariaLabel, filename)) {
          return true;
        }
        let sibling = ancestor.previousElementSibling;
        let coverLetterSibling = false;
        while (sibling) {
          const siblingText = (sibling.textContent || "").replace(/\s+/g, " ").trim();
          if (isCoverLetterHeadingText(siblingText)) {
            coverLetterSibling = true;
            break;
          }
          if (isResumeHeadingText(siblingText, filename)) return true;
          sibling = sibling.previousElementSibling;
        }
        if (coverLetterSibling) break;
        if (ancestor.matches(".file-upload, [role='group']")) {
          const headingEl =
            ancestor.querySelector("label, legend, [id*='upload-label']") ||
            [...ancestor.querySelectorAll("span, p")].find((el) => {
              const text = (el.textContent || "").replace(/\s+/g, " ").trim();
              return Boolean(text) && text !== filename && !text.includes(filename);
            });
          const heading = (headingEl?.textContent || ancestor.getAttribute("aria-label") || "").trim();
          if (isCoverLetterHeadingText(heading)) break;
          if (isResumeHeadingText(heading, filename)) return true;
        }
        ancestor = ancestor.parentElement;
      }
    }
    return false;
  }

  function highlight(input: HTMLInputElement) {
    input.style.outline = "2px solid #7c3aed";
    try {
      input.focus();
      input.scrollIntoView({ block: "center", inline: "nearest" });
    } catch {
      // Focusing is best-effort.
    }
  }

  const resumeInputs = [...document.querySelectorAll<HTMLInputElement>("input[type='file']")].filter(
    (input) => classify(input) === "resume",
  );
  if (resumeInputs.length === 0) {
    return {
      status: "unsupported_field",
      fieldKind: null,
      verifiedName: null,
      reason: "No resume file field was recognized on this page.",
    };
  }
  if (resumeInputs.length > 1) {
    highlight(resumeInputs[0]);
    return {
      status: "ambiguous",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Multiple resume file fields were found. Attach manually.",
    };
  }

  const input = resumeInputs[0];
  if (!acceptAllows(input, payload.mimeType, payload.filename)) {
    highlight(input);
    return {
      status: "manual",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Attach manually — this field does not accept the selected format.",
    };
  }

  let file: File;
  try {
    file = decodeFile();
  } catch {
    return {
      status: "failed",
      fieldKind: "resume",
      verifiedName: null,
      reason: "The resume file could not be decoded.",
    };
  }

  if (!assignFiles(input, file)) {
    highlight(input);
    return {
      status: "manual",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Attach manually — this site blocked programmatic file attachment.",
    };
  }

  const confirmedOnInput = hasName(input, payload.filename);
  if (!confirmedOnInput) {
    // Greenhouse may replace the input synchronously in the change handler.
    // Only treat the Resume/CV filename widget as confirmation when THIS
    // attempt assigned a File and the original input is gone — a leftover
    // same-named display is not proof.
    if (!input.isConnected && resumeGroupShowsFilename(payload.filename)) {
      return {
        status: "attached",
        fieldKind: "resume",
        verifiedName: payload.filename,
        reason: null,
      };
    }
    highlight(input);
    return {
      status: "failed",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Attachment could not be verified.",
    };
  }

  await new Promise((resolve) => setTimeout(resolve, 150));
  if (hasName(input, payload.filename)) {
    return {
      status: "attached",
      fieldKind: "resume",
      verifiedName: payload.filename,
      reason: null,
    };
  }
  if (resumeGroupShowsFilename(payload.filename)) {
    return {
      status: "attached",
      fieldKind: "resume",
      verifiedName: payload.filename,
      reason: null,
    };
  }
  highlight(input);
  return {
    status: "failed",
    fieldKind: "resume",
    verifiedName: null,
    reason: "Resume needs re-attachment.",
  };
}

export function verifyResumeAttachmentInPage(filename: string): { attached: boolean } {
  // Injected into the job page. Must stay self-contained — Chrome does not
  // serialize this module's other exports with the function.
  const resumeNameRe = /(resume|curriculum vitae|\bcv\b)/i;
  const coverLetterNameRe = /cover[\s_-]*letter/i;

  function isResumeHeading(text: string): boolean {
    const t = (text || "").replace(/\s+/g, " ").trim();
    if (!t || t === filename || t.length > 64) return false;
    if (coverLetterNameRe.test(t)) return false;
    return resumeNameRe.test(t);
  }

  function isCoverLetterHeading(text: string): boolean {
    const t = (text || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 64) return false;
    return coverLetterNameRe.test(t) && !resumeNameRe.test(t);
  }

  function resumeGroupShowsFilename(): boolean {
    const filenameNodes = [...document.querySelectorAll("*")].filter((el) => {
      if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return false;
      const ownText = [...el.childNodes]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => (node.textContent || "").trim())
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (ownText === filename) return true;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      return el.children.length === 0 && text === filename;
    });
    for (const node of filenameNodes) {
      let ancestor: Element | null = node;
      for (let i = 0; i < 8 && ancestor; i += 1) {
        const labelledBy = ancestor.getAttribute("aria-labelledby");
        const labelled = labelledBy ? document.getElementById(labelledBy)?.textContent || "" : "";
        const ariaLabel = ancestor.getAttribute("aria-label") || "";
        if (isCoverLetterHeading(labelled) || isCoverLetterHeading(ariaLabel)) break;
        if (isResumeHeading(labelled) || isResumeHeading(ariaLabel)) return true;
        let sibling = ancestor.previousElementSibling;
        let coverLetterSibling = false;
        while (sibling) {
          const siblingText = (sibling.textContent || "").replace(/\s+/g, " ").trim();
          if (isCoverLetterHeading(siblingText)) {
            coverLetterSibling = true;
            break;
          }
          if (isResumeHeading(siblingText)) return true;
          sibling = sibling.previousElementSibling;
        }
        if (coverLetterSibling) break;
        if (ancestor.matches(".file-upload, [role='group']")) {
          const headingEl =
            ancestor.querySelector("label, legend, [id*='upload-label']") ||
            [...ancestor.querySelectorAll("span, p, div")].find((el) => {
              const text = (el.textContent || "").replace(/\s+/g, " ").trim();
              return Boolean(text) && text !== filename && !text.includes(filename);
            });
          const heading = (headingEl?.textContent || ancestor.getAttribute("aria-label") || "").trim();
          if (isCoverLetterHeading(heading)) break;
          if (isResumeHeading(heading)) return true;
        }
        ancestor = ancestor.parentElement;
      }
    }
    return false;
  }

  const inputs = [...document.querySelectorAll<HTMLInputElement>("input[type='file']")];
  for (const input of inputs) {
    const self = `${input.name} ${input.id} ${input.getAttribute("aria-label") || ""}`;
    if (coverLetterNameRe.test(self) && !resumeNameRe.test(self)) continue;
    const label = input.labels?.[0]?.textContent || "";
    const isResume =
      resumeNameRe.test(self) ||
      input.id === "resume" ||
      input.name === "resume" ||
      (input.name || "").includes("job_application[resume]") ||
      (resumeNameRe.test(label) && !coverLetterNameRe.test(label));
    if (!isResume) continue;
    if (input.files?.[0]?.name === filename) return { attached: true };
  }

  // Some ATS widgets (confirmed live on Greenhouse job-boards) remove the
  // raw file input after a successful attach and show the filename next to
  // a Resume/CV heading. Filename equality alone is not proof: the display
  // must sit in that Resume/CV group, not under Cover Letter, and not as
  // unrelated page copy. Session ownership of the attach is enforced by
  // the caller (this attempt assigned File/DataTransfer, or this
  // side-panel session last attached this resume version).
  return { attached: resumeGroupShowsFilename() };
}

function isResumeHeadingText(text: string, filename: string): boolean {
  const t = (text || "").replace(/\s+/g, " ").trim();
  if (!t || t === filename || t.length > 64) return false;
  if (COVER_LETTER_NAME_RE.test(t)) return false;
  return RESUME_NAME_RE.test(t);
}

function isCoverLetterHeadingText(text: string): boolean {
  const t = (text || "").replace(/\s+/g, " ").trim();
  if (!t || t.length > 64) return false;
  return COVER_LETTER_NAME_RE.test(t) && !RESUME_NAME_RE.test(t);
}

/** True when `filename` is the exact visible text of a Resume/CV widget. */
export function resumeGroupShowsExactFilename(filename: string): boolean {
  const filenameNodes = [...document.querySelectorAll("*")].filter((el) => {
    if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return false;
    const ownText = [...el.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => (node.textContent || "").trim())
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    if (ownText === filename) return true;
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    return el.children.length === 0 && text === filename;
  });
  for (const node of filenameNodes) {
    let ancestor: Element | null = node;
    for (let i = 0; i < 8 && ancestor; i += 1) {
      const labelledBy = ancestor.getAttribute("aria-labelledby");
      const labelled = labelledBy ? document.getElementById(labelledBy)?.textContent || "" : "";
      const ariaLabel = ancestor.getAttribute("aria-label") || "";
      if (isCoverLetterHeadingText(labelled) || isCoverLetterHeadingText(ariaLabel)) break;
      if (isResumeHeadingText(labelled, filename) || isResumeHeadingText(ariaLabel, filename)) {
        return true;
      }
      let sibling = ancestor.previousElementSibling;
      let coverLetterSibling = false;
      while (sibling) {
        const siblingText = (sibling.textContent || "").replace(/\s+/g, " ").trim();
        if (isCoverLetterHeadingText(siblingText)) {
          coverLetterSibling = true;
          break;
        }
        if (isResumeHeadingText(siblingText, filename)) return true;
        sibling = sibling.previousElementSibling;
      }
      if (coverLetterSibling) break;
      if (ancestor.matches(".file-upload, [role='group']")) {
        const headingEl =
          ancestor.querySelector("label, legend, [id*='upload-label']") ||
          [...ancestor.querySelectorAll("span, p")].find((el) => {
            const text = (el.textContent || "").replace(/\s+/g, " ").trim();
            return Boolean(text) && text !== filename && !text.includes(filename);
          });
        const heading = (headingEl?.textContent || ancestor.getAttribute("aria-label") || "").trim();
        if (isCoverLetterHeadingText(heading)) break;
        if (isResumeHeadingText(heading, filename)) return true;
      }
      ancestor = ancestor.parentElement;
    }
  }
  return false;
}

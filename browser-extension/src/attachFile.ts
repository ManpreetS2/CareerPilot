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

  function highlight(input: HTMLInputElement) {
    input.style.outline = "2px solid #4f46e5";
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

  if (!hasName(input, payload.filename)) {
    highlight(input);
    return {
      status: "failed",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Attachment could not be verified.",
    };
  }

  await new Promise((resolve) => setTimeout(resolve, 150));
  if (!hasName(input, payload.filename)) {
    highlight(input);
    return {
      status: "failed",
      fieldKind: "resume",
      verifiedName: null,
      reason: "Resume needs re-attachment.",
    };
  }

  return {
    status: "attached",
    fieldKind: "resume",
    verifiedName: payload.filename,
    reason: null,
  };
}

export function verifyResumeAttachmentInPage(filename: string): { attached: boolean } {
  const resumeNameRe = /(resume|curriculum vitae|\bcv\b)/i;
  const coverLetterNameRe = /cover[\s_-]*letter/i;
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
  return { attached: false };
}

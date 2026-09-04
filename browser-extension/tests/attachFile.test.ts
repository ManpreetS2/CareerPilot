import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachDocumentInPage,
  classifyFileInput,
  classifyFileInputs,
  verifyResumeAttachmentInPage,
} from "../src/attachFile";
import { COVER_LETTER_FILE_SUPPORT } from "../src/cover-letter-file";

const fixtures = join(dirname(fileURLToPath(import.meta.url)), "../../tests/fixtures/ats_forms");

function loadFixture(name: string) {
  document.body.innerHTML = readFileSync(join(fixtures, name), "utf8");
  for (const input of document.querySelectorAll<HTMLInputElement>("input[type='file']")) {
    let files: FileList | null = null;
    Object.defineProperty(input, "files", {
      configurable: true,
      get: () => files,
      set: (value: FileList | null) => {
        files = value;
      },
    });
  }
}

function payload(overrides: Partial<{ filename: string; mimeType: string; bytesBase64: string }> = {}) {
  return {
    kind: "resume" as const,
    filename: "resume-v1.pdf",
    mimeType: "application/pdf",
    bytesBase64: btoa("%PDF-1.4"),
    ...overrides,
  };
}

describe("file field classification", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("recognizes Greenhouse and Lever resume fields and ignores generic files", () => {
    loadFixture("greenhouse_resume_file.html");
    expect(classifyFileInputs().resume).toHaveLength(1);
    expect(classifyFileInput(document.querySelector("input[type='file']")!)).toBe("resume");

    loadFixture("lever_resume_and_cover_file.html");
    const lever = classifyFileInputs();
    expect(lever.resume).toHaveLength(1);
    expect(lever.coverLetter).toHaveLength(1);

    loadFixture("generic_unsupported_file.html");
    expect(classifyFileInputs().unsupported).toHaveLength(1);
    expect(classifyFileInputs().resume).toHaveLength(0);
  });

  it("does not treat a cover-letter file input as a resume", () => {
    loadFixture("greenhouse_cover_letter_file.html");
    const classified = classifyFileInputs();
    expect(classified.resume.map((input) => input.id)).toEqual(["resume"]);
    expect(classified.coverLetter.map((input) => input.id)).toEqual(["cover_letter"]);
  });
});

describe("resume attachment", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "DataTransfer",
      class {
        files: File[] = [];
        items = {
          add: (file: File) => {
            this.files = [file];
          },
        };
      },
    );
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("attaches a PDF on Greenhouse and verifies the filename", async () => {
    loadFixture("greenhouse_resume_file.html");
    const submit = vi.fn();
    document.getElementById("submit_app")?.addEventListener("click", submit);
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("attached");
    expect(result.verifiedName).toBe("resume-v1.pdf");
    expect(verifyResumeAttachmentInPage("resume-v1.pdf").attached).toBe(true);
    expect(submit).not.toHaveBeenCalled();
  });

  it("attaches on Lever without touching a cover-letter file input", async () => {
    loadFixture("lever_resume_and_cover_file.html");
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("attached");
    const cover = document.getElementById("cover_letter_file") as HTMLInputElement;
    expect(cover.files?.length ?? 0).toBe(0);
  });

  it("falls back to manual when multiple resume fields are present", async () => {
    loadFixture("greenhouse_multiple_resume_files.html");
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("ambiguous");
    expect(result.reason).toMatch(/manually/i);
  });

  it("does not attach to an unsupported generic file input", async () => {
    loadFixture("generic_unsupported_file.html");
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("unsupported_field");
    expect((document.getElementById("portfolio") as HTMLInputElement).files?.length ?? 0).toBe(0);
  });

  it("attaches a DOCX on Lever when the field accepts Word documents", async () => {
    loadFixture("lever_accept_docx.html");
    const result = await attachDocumentInPage(
      payload({
        filename: "resume-v1.docx",
        mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        bytesBase64: btoa("PK"),
      }),
    );
    expect(result.status).toBe("attached");
    expect(result.verifiedName).toBe("resume-v1.docx");
  });

  it("falls back to manual when programmatic attachment is blocked", async () => {
    vi.stubGlobal(
      "DataTransfer",
      class {
        constructor() {
          throw new Error("blocked");
        }
      },
    );
    loadFixture("greenhouse_resume_file.html");
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("manual");
    expect(result.reason).toMatch(/manually/i);
  });

  it("rejects a DOCX when the field only accepts PDF", async () => {
    loadFixture("greenhouse_accept_pdf.html");
    const result = await attachDocumentInPage(
      payload({
        filename: "resume-v1.docx",
        mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        bytesBase64: btoa("PK"),
      }),
    );
    expect(result.status).toBe("manual");
    expect(result.reason).toMatch(/format/i);
  });

  it("treats a disappearing file after rerender as a failed attachment", async () => {
    loadFixture("greenhouse_resume_file.html");
    const input = document.getElementById("resume") as HTMLInputElement;
    let files: FileList | File[] | null = null;
    let attachedAt = 0;
    Object.defineProperty(input, "files", {
      configurable: true,
      get: () => {
        if (attachedAt && Date.now() - attachedAt >= 100) return null;
        return files;
      },
      set: (value: FileList | File[] | null) => {
        files = value;
        attachedAt = Date.now();
      },
    });
    const result = await attachDocumentInPage(payload());
    expect(result.status).toBe("failed");
    expect(result.reason).toMatch(/re-attachment/i);
  });

  it("verifies attachment when the ATS removed the input and shows a filename display instead", () => {
    // Confirmed live on Greenhouse: once attached, the raw file input is
    // removed from the DOM and replaced by a text display of the filename.
    // A verify call that only looks for a live <input> would wrongly report
    // the resume as lost even though it genuinely attached and is holding.
    loadFixture("greenhouse_resume_uploaded_display.html");
    expect(verifyResumeAttachmentInPage("resume-v1.pdf").attached).toBe(true);
  });

  it("verifies attachment when Resume/CV is a sibling heading rather than aria-labelledby", () => {
    loadFixture("greenhouse_resume_uploaded_sibling_label.html");
    expect(verifyResumeAttachmentInPage("resume-v1.pdf").attached).toBe(true);
  });

  it("does not treat a same-named file under the cover letter group as the resume", () => {
    loadFixture("greenhouse_cover_letter_uploaded_display.html");
    expect(verifyResumeAttachmentInPage("resume-v1.pdf").attached).toBe(false);
  });

  it("never submits", async () => {
    loadFixture("greenhouse_resume_file.html");
    const form = document.querySelector("form") as HTMLFormElement;
    const spy = vi.spyOn(form, "submit").mockImplementation(() => undefined);
    await attachDocumentInPage(payload());
    expect(spy).not.toHaveBeenCalled();
  });

  it("source never calls submit helpers", () => {
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../src/attachFile.ts"), "utf8").replace(
      /\/\*[\s\S]*?\*\//g,
      "",
    );
    expect(source).not.toMatch(/\.submit\s*\(/);
    expect(source).not.toMatch(/requestSubmit/);
    expect(source).not.toMatch(/console\.(log|debug|info)\([^)]*bytes/);
    expect(source).not.toMatch(/console\.(log|debug|info)\([^)]*bytesBase64/);
  });
});

describe("cover letter file support", () => {
  it("is deferred because there is no document export contract", () => {
    expect(COVER_LETTER_FILE_SUPPORT.available).toBe(false);
    expect(COVER_LETTER_FILE_SUPPORT.reason).toMatch(/text only/i);
  });
});

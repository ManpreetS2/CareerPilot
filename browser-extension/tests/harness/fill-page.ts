import { attachDocumentInPage, verifyResumeAttachmentInPage } from "../../src/attachFile";
import { fillFormInPage } from "../../src/fillForm";

declare global {
  interface Window {
    fillFormInPage: typeof fillFormInPage;
    attachDocumentInPage: typeof attachDocumentInPage;
    verifyResumeAttachmentInPage: typeof verifyResumeAttachmentInPage;
  }
}

window.fillFormInPage = fillFormInPage;
window.attachDocumentInPage = attachDocumentInPage;
window.verifyResumeAttachmentInPage = verifyResumeAttachmentInPage;

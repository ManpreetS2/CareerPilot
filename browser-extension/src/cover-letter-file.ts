/** Cover-letter *file* attachment is deferred.

The application package stores an approved cover letter as text
(`cover_letter_draft`) and the existing fill engine maps that text into
Greenhouse/Lever textareas. There is no ownership-checked document export
for a cover-letter PDF/DOCX, so this PR does not invent a file upload path
for it. ResumeVersion upload is the P0.
*/
export const COVER_LETTER_FILE_SUPPORT = {
  available: false as const,
  reason: "Cover letter is approved text only; there is no ownership-checked document export.",
};

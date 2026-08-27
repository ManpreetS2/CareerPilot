import { describe, expect, it } from "vitest";
import { ApiClientError } from "./api";
import { resumeParseErrorHeading } from "./resume-parse-error";

describe("resumeParseErrorHeading", () => {
  it("maps safe user-facing categories", () => {
    expect(
      resumeParseErrorHeading(new ApiClientError(502, "AI service temporarily unavailable. Please try again.")),
    ).toBe("AI service temporarily unavailable");
    expect(
      resumeParseErrorHeading(new ApiClientError(504, "Resume analysis timed out. Please try again.")),
    ).toBe("Resume analysis timed out");
    expect(
      resumeParseErrorHeading(new ApiClientError(422, "Resume contained too little readable text.")),
    ).toBe("Resume contained too little readable text");
    expect(resumeParseErrorHeading(new ApiClientError(400, "Resume could not be read."))).toBe(
      "Resume could not be read",
    );
  });
});

import { describe, expect, it } from "vitest";
import { API_BASE_URL, sessionCookieUrls, WEB_APP_URL } from "../src/config";

describe("extension environment configuration", () => {
  it("defaults to loopback CareerPilot origins rather than a production hostname", () => {
    expect(API_BASE_URL).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8000$/);
    expect(WEB_APP_URL).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):5173$/);
    expect(API_BASE_URL).not.toContain("careerpilot.app");
    expect(WEB_APP_URL).not.toContain("careerpilot.app");
  });

  it("probes localhost and 127.0.0.1 for the session cookie", () => {
    expect(sessionCookieUrls("http://127.0.0.1:8000")).toEqual(["http://127.0.0.1:8000", "http://localhost:8000"]);
    expect(sessionCookieUrls("http://localhost:8000")).toEqual(["http://localhost:8000", "http://127.0.0.1:8000"]);
  });
});

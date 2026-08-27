import { describe, expect, it } from "vitest";
import { resolveApiBaseUrl } from "./config";

describe("resolveApiBaseUrl", () => {
  it("resolves a localhost page to a localhost local API", () => {
    expect(resolveApiBaseUrl(undefined, "localhost")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("http://localhost:8000", "localhost")).toBe("http://localhost:8000");
  });

  it("resolves a 127.0.0.1 page to a 127.0.0.1 local API", () => {
    expect(resolveApiBaseUrl(undefined, "127.0.0.1")).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "127.0.0.1")).toBe("http://127.0.0.1:8000");
  });

  it("does not let a copied or default local config create a localhost/127 mismatch", () => {
    expect(resolveApiBaseUrl("http://localhost:8000", "127.0.0.1")).toBe("http://127.0.0.1:8000");
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "localhost")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("http://localhost:8000/", "127.0.0.1")).toBe("http://127.0.0.1:8000");
  });

  it("leaves an explicit non-local VITE_API_BASE_URL unchanged", () => {
    expect(resolveApiBaseUrl("https://api.careerpilot.example", "localhost")).toBe(
      "https://api.careerpilot.example",
    );
    expect(resolveApiBaseUrl("https://api.careerpilot.example", "127.0.0.1")).toBe(
      "https://api.careerpilot.example",
    );
    expect(resolveApiBaseUrl("https://api.careerpilot.example:8443/v1", "localhost")).toBe(
      "https://api.careerpilot.example:8443/v1",
    );
  });

  it("normalizes trailing slashes on the API base", () => {
    expect(resolveApiBaseUrl("http://localhost:8000/", "localhost")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("https://api.careerpilot.example/", "example.com")).toBe(
      "https://api.careerpilot.example",
    );
  });

  it("preserves the configured local scheme and port when rewriting the hostname", () => {
    expect(resolveApiBaseUrl("https://localhost:9000", "127.0.0.1")).toBe("https://127.0.0.1:9000");
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "localhost")).toBe("http://localhost:8000");
  });
});

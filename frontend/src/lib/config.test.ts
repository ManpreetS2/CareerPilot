import { describe, expect, it } from "vitest";
import { resolveApiBaseUrl, unreachableApiMessage } from "./config";

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

  it("serializes an unset IPv6 loopback page as a bracketed URL", () => {
    expect(resolveApiBaseUrl(undefined, "[::1]")).toBe("http://[::1]:8000");
  });

  it("rewrites a localhost API onto a bracketed IPv6 loopback page", () => {
    expect(resolveApiBaseUrl("http://localhost:8000", "[::1]")).toBe("http://[::1]:8000");
  });

  it("rewrites a 127.0.0.1 API onto a bracketed IPv6 loopback page", () => {
    expect(resolveApiBaseUrl("http://127.0.0.1:8000", "[::1]")).toBe("http://[::1]:8000");
  });

  it("rewrites a bracketed IPv6 API onto localhost while keeping the port", () => {
    expect(resolveApiBaseUrl("http://[::1]:9000", "localhost")).toBe("http://localhost:9000");
  });

  it("rewrites a bracketed IPv6 API onto 127.0.0.1 while keeping the port", () => {
    expect(resolveApiBaseUrl("http://[::1]:9000", "127.0.0.1")).toBe("http://127.0.0.1:9000");
  });
});

describe("unreachableApiMessage", () => {
  it("keeps the operator hint for a local API", () => {
    expect(unreachableApiMessage("http://127.0.0.1:8000")).toContain("uvicorn");
  });

  it("never shows operator instructions to users of a hosted API", () => {
    const message = unreachableApiMessage("https://api.careerpilot.example");
    expect(message).toBe("Can't reach CareerPilot right now. Check your connection and try again.");
    expect(message).not.toMatch(/uvicorn|backend/i);
  });
});

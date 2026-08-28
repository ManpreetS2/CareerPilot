/// <reference types="vite/client" />

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_WEB_APP_URL = "http://127.0.0.1:5173";

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function fromEnv(value: string | undefined, fallback: string): string {
  const trimmed = (value ?? "").trim();
  return stripTrailingSlash(trimmed || fallback);
}

/** CareerPilot API origin. Overridable at build time; never a production hostname. */
export const API_BASE_URL = fromEnv(import.meta.env.VITE_API_BASE_URL, DEFAULT_API_BASE_URL);

/** CareerPilot web app origin used for Sign in / Open analysis / Prepare links. */
export const WEB_APP_URL = fromEnv(import.meta.env.VITE_WEB_APP_URL, DEFAULT_WEB_APP_URL);

/** Origins to probe for the session cookie (localhost vs 127.0.0.1 splits cookies). */
export function sessionCookieUrls(apiBaseUrl: string = API_BASE_URL): string[] {
  const urls = [apiBaseUrl];
  try {
    const parsed = new URL(apiBaseUrl);
    const altHost = parsed.hostname === "localhost" ? "127.0.0.1" : parsed.hostname === "127.0.0.1" ? "localhost" : null;
    if (altHost) {
      const port = parsed.port ? `:${parsed.port}` : "";
      urls.push(`${parsed.protocol}//${altHost}${port}`);
    }
  } catch {
    // Invalid override — still try the configured string.
  }
  return [...new Set(urls)];
}

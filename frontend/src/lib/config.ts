const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "::1"]);
const DEFAULT_LOCAL_API_PORT = "8000";
const DEFAULT_LOCAL_API_SCHEME = "http";

function stripTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

function canonicalHostname(hostname: string): string {
  return hostname.replace(/^\[|\]$/g, "").toLowerCase();
}

function isLocalHostname(hostname: string): boolean {
  return LOCAL_HOSTNAMES.has(canonicalHostname(hostname));
}

function isIpv6Hostname(hostname: string): boolean {
  return canonicalHostname(hostname).includes(":");
}

function hostnameForUrl(hostname: string): string {
  const host = canonicalHostname(hostname);
  return isIpv6Hostname(host) ? `[${host}]` : host;
}

function defaultLocalApiBase(pageHostname: string): string {
  const host = isLocalHostname(pageHostname) ? hostnameForUrl(pageHostname) : "localhost";
  return `${DEFAULT_LOCAL_API_SCHEME}://${host}:${DEFAULT_LOCAL_API_PORT}`;
}

/** Align a local API origin with the page hostname so SameSite=Lax cookies stay first-party. */
export function resolveApiBaseUrl(
  configured: string | undefined | null,
  pageHostname: string,
): string {
  const trimmed = stripTrailingSlashes((configured ?? "").trim());
  const fallback = defaultLocalApiBase(pageHostname);
  const candidate = trimmed || fallback;

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return fallback;
  }

  if (isLocalHostname(parsed.hostname) && isLocalHostname(pageHostname)) {
    parsed.hostname = hostnameForUrl(pageHostname);
  }

  const normalized = parsed.pathname === "/" ? `${parsed.origin}` : `${parsed.origin}${parsed.pathname}`;
  return stripTrailingSlashes(normalized);
}

export const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  typeof window === "undefined" ? "localhost" : window.location.hostname,
);

export const APP_NAME = "CareerPilot";
export const APP_TAGLINE = "Grounded job search. Human-approved applications.";

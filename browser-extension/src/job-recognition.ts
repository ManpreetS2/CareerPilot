export type AtsPlatform = "greenhouse" | "lever" | "unsupported";

export type JobRecognition = {
  platform: AtsPlatform;
  supported: boolean;
  jobUrl: string;
  sourceJobId: string | null;
  companyHint: string | null;
};

function hostname(url: string): string | null {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
}

/** Mirrors backend detect_ats_platform: host suffix only, no page scrape. */
export function detectAtsPlatform(url: string): AtsPlatform {
  const host = hostname(url);
  if (!host) return "unsupported";
  if (host === "greenhouse.io" || host.endsWith(".greenhouse.io")) return "greenhouse";
  if (host === "lever.co" || host.endsWith(".lever.co")) return "lever";
  return "unsupported";
}

function greenhouseSourceJobId(url: string): { sourceJobId: string; companyHint: string | null } | null {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname || "";
    const pathMatch = path.match(/^\/([^/]+)\/jobs\/(\d+)\/?$/);
    if (pathMatch) {
      return { companyHint: pathMatch[1], sourceJobId: pathMatch[2] };
    }
    if (/^\/embed\/job_app\/?$/.test(path)) {
      const token = parsed.searchParams.get("token");
      const board = parsed.searchParams.get("for");
      if (token && /^\d+$/.test(token)) {
        return { companyHint: board, sourceJobId: token };
      }
    }
  } catch {
    return null;
  }
  return null;
}

function leverSourceJobId(url: string): { sourceJobId: string; companyHint: string | null } | null {
  try {
    const parsed = new URL(url);
    const match = (parsed.pathname || "").match(
      /^\/([^/]+)\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:\/apply)?\/?$/,
    );
    if (!match) return null;
    return { companyHint: match[1], sourceJobId: match[2] };
  } catch {
    return null;
  }
}

export function recognizeJobPage(url: string): JobRecognition {
  const platform = detectAtsPlatform(url);
  if (platform === "greenhouse") {
    const ids = greenhouseSourceJobId(url);
    return {
      platform,
      supported: true,
      jobUrl: url,
      sourceJobId: ids?.sourceJobId ?? null,
      companyHint: ids?.companyHint ?? null,
    };
  }
  if (platform === "lever") {
    const ids = leverSourceJobId(url);
    return {
      platform,
      supported: true,
      jobUrl: url,
      sourceJobId: ids?.sourceJobId ?? null,
      companyHint: ids?.companyHint ?? null,
    };
  }
  return {
    platform: "unsupported",
    supported: false,
    jobUrl: url,
    sourceJobId: null,
    companyHint: null,
  };
}

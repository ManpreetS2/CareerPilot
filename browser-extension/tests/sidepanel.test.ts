// Behavioral tests for the side panel itself. sidepanel.ts has no exports —
// it wires itself to the DOM and the chrome.* APIs on import — so each test
// installs fresh fakes, imports the module, and then drives it the way the
// browser would: by firing the background worker's TAB_CHANGED message and
// by clicking the rendered buttons.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type TabChangedListener = (message: { type?: string; url?: string }) => void;

const JOB_URL = "https://boards.greenhouse.io/acme/jobs/1";
const LEVER_URL = "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const OTHER_URL = "https://boards.greenhouse.io/other-co/jobs/9";

function resumeVersion(overrides: Record<string, unknown> = {}) {
  return {
    id: "rv-1",
    job_id: "greenhouse-abc123",
    job_title: "Backend Engineer",
    company: "Acme",
    version_number: 1,
    created_at: "2026-08-27T12:00:00Z",
    bullet_count: 2,
    provenance_status: "approved_snapshot",
    matches_current_profile: true,
    formats: ["pdf", "docx"],
    ...overrides,
  };
}

function panelData(overrides: Record<string, unknown> = {}) {
  return {
    tracked: true,
    job: {
      id: "greenhouse-abc123",
      title: "Backend Engineer",
      company: "Acme",
      location: "Remote",
      salary: null,
      url: JOB_URL,
      source: "greenhouse",
      status: "discovered",
      date_scraped: "2026-08-26T06:00:00",
    },
    score: null,
    materials_status: "current",
    platform: "greenhouse",
    apply_ready: true,
    apply_blocked_reason: null,
    materials_unverified: false,
    ...overrides,
  };
}

let listeners: TabChangedListener[];
let activeTab: { id: number; url: string };
let fetchMock: ReturnType<typeof vi.fn>;
let executeScript: ReturnType<typeof vi.fn>;
let permissionsContains: ReturnType<typeof vi.fn>;
let permissionsRequest: ReturnType<typeof vi.fn>;
let responders: Record<string, () => unknown>;

/** Lets queued promise callbacks run to completion. The panel chains a long
 * series of awaits (cookie read, permission check, fetch, json, tab query,
 * script injection), so this drains the macrotask queue between microtask
 * batches rather than counting ticks and hoping. */
async function flush(rounds = 6) {
  for (let i = 0; i < rounds; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function panelHtml() {
  return document.getElementById("app")!.innerHTML;
}

async function loadPanel() {
  vi.resetModules();
  await import("../src/sidepanel");
  await flush();
}

function fireTabChanged(url: string) {
  for (const listener of listeners) listener({ type: "TAB_CHANGED", url });
}

beforeEach(() => {
  document.body.innerHTML = '<div id="app"></div>';
  listeners = [];
  activeTab = { id: 42, url: JOB_URL };
  executeScript = vi.fn(async () => [{ result: { filled: [{ name: "email", value: "a@b.c" }], flagged: [] } }]);
  permissionsContains = vi.fn(async () => true);
  permissionsRequest = vi.fn(async () => true);
  responders = {
    "panel-data": () => panelData(),
    autofill: () => ({ job_id: "greenhouse-abc123", platform: "greenhouse", fields: { email: "a@b.c" } }),
  };

  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    const method = (init?.method || "GET").toUpperCase();
    if (href.includes("panel-data")) {
      return { ok: true, status: 200, json: async () => responders["panel-data"]() } as unknown as Response;
    }
    if (href.includes("autofill")) {
      return { ok: true, status: 200, json: async () => responders["autofill"]() } as unknown as Response;
    }
    if (href.includes("ingest-url")) {
      return { ok: true, status: 201, json: async () => responders["ingest-url"]() } as unknown as Response;
    }
    if (href.includes("/save")) {
      if (method === "DELETE") {
        return { ok: true, status: 204, json: async () => ({}) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => responders["save"]?.() ?? panelData({ saved: true }) } as unknown as Response;
    }
    if (href.includes("verified-fit")) {
      return { ok: true, status: 200, json: async () => responders["verified-fit"]() } as unknown as Response;
    }
    if (href.includes("resume-versions") && href.includes("/file")) {
      return (responders["resume-file"]?.() ?? {
        ok: true,
        status: 200,
        headers: {
          get: (name: string) =>
            name.toLowerCase() === "content-type"
              ? "application/pdf"
              : name.toLowerCase() === "content-disposition"
                ? 'attachment; filename="resume-v1.pdf"'
                : null,
        },
        arrayBuffer: async () => new Uint8Array([0x25, 0x50, 0x44, 0x46]).buffer,
      }) as unknown as Response;
    }
    if (href.includes("resume-versions")) {
      return {
        ok: true,
        status: 200,
        json: async () => responders["resume-versions"]?.() ?? { versions: [], current_job_id: null },
      } as unknown as Response;
    }
    return { ok: false, status: 404, json: async () => ({ detail: "missing mock" }) } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("chrome", {
    cookies: { get: vi.fn(async () => ({ value: "session-token" })) },
    tabs: { query: vi.fn(async () => [activeTab]) },
    permissions: { contains: permissionsContains, request: permissionsRequest },
    scripting: { executeScript },
    runtime: { onMessage: { addListener: (fn: TabChangedListener) => listeners.push(fn) } },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("first load", () => {
  it("reads the active tab and renders the tracked job", async () => {
    await loadPanel();
    expect(panelHtml()).toContain("Backend Engineer");
    expect(panelHtml()).toContain("Acme");
  });

  it("sends the session header rather than relying on a cookie", async () => {
    await loadPanel();
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-CareerPilot-Session"]).toBe("session-token");
    expect(init.credentials).toBeUndefined();
  });

  it("prompts for login instead of erroring when no session cookie exists", async () => {
    (globalThis as any).chrome.cookies.get = vi.fn(async () => null);
    await loadPanel();
    expect(panelHtml()).toContain("Log in to CareerPilot");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("pages that can never be job postings", () => {
  it.each(["chrome://extensions/", "about:blank", "file:///tmp/x.pdf"])(
    "shows an idle state for %s and never sends the URL to the backend",
    async (url) => {
      activeTab = { id: 42, url };
      await loadPanel();
      expect(panelHtml()).toContain("No job page open");
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("does not mislabel them as untracked jobs", async () => {
    activeTab = { id: 42, url: "chrome://newtab/" };
    await loadPanel();
    expect(panelHtml()).not.toContain("isn't tracked");
  });
});

describe("following the active tab", () => {
  it("re-fetches when returning to the same tab, so freshly stored data appears", async () => {
    // The staleness bug this guards: score the job in the web app, come
    // back to the tab, and the panel must stop saying "Not scored yet".
    responders["panel-data"] = () => panelData({ score: null });
    await loadPanel();
    expect(panelHtml()).toContain("Not scored yet");

    responders["panel-data"] = () =>
      panelData({
        score: { overall_score: 91, matched_skills: ["Python"], partial_matches: [], missing_skills: ["Go"], recommendation: "apply", rationale: "" },
      });
    fireTabChanged(JOB_URL); // same URL — an unchanged-URL revisit
    await flush();

    expect(panelHtml()).toContain("Potential Match");
    expect(panelHtml()).not.toContain("Not scored yet");
  });

  it("drops a slow response that a newer tab switch has already superseded", async () => {
    let releaseFirst: (v: unknown) => void = () => {};
    const firstInFlight = new Promise((resolve) => {
      releaseFirst = resolve;
    });
    responders["panel-data"] = () => panelData({ job: { ...panelData().job, title: "STALE ROLE" } });
    fetchMock.mockImplementationOnce(async () => {
      await firstInFlight;
      return { ok: true, status: 200, json: async () => responders["panel-data"]() } as unknown as Response;
    });

    await loadPanel();
    responders["panel-data"] = () => panelData({ job: { ...panelData().job, title: "CURRENT ROLE" } });
    fireTabChanged(OTHER_URL);
    await flush();
    releaseFirst(null); // the first request finally lands, out of order
    await flush();

    expect(panelHtml()).toContain("CURRENT ROLE");
    expect(panelHtml()).not.toContain("STALE ROLE");
  });
});

describe("assisted apply", () => {
  it("is offered on a supported ATS page", async () => {
    await loadPanel();
    expect(document.getElementById("fill-btn")).not.toBeNull();
  });

  it("is explained rather than offered on a posting it could never fill", async () => {
    responders["panel-data"] = () => panelData({ platform: "unsupported", job: { ...panelData().job, source: "remotive" } });
    await loadPanel();
    expect(document.getElementById("fill-btn")).toBeNull();
    expect(panelHtml()).toContain("Only Greenhouse and Lever");
  });

  it("states what is blocking instead of offering a button that would fail", async () => {
    responders["panel-data"] = () =>
      panelData({
        apply_ready: false,
        apply_blocked_reason: "This application must be approved before assisted apply can run.",
      });
    await loadPanel();

    expect(document.getElementById("fill-btn")).toBeNull();
    expect(panelHtml()).toContain("must be approved");
    expect(panelHtml()).toContain("Prepare it in CareerPilot");
  });

  it("falls back to a readable message if the backend gives no reason", async () => {
    responders["panel-data"] = () => panelData({ apply_ready: false, apply_blocked_reason: null });
    await loadPanel();
    expect(panelHtml()).toContain("isn't ready to fill yet");
  });

  it("escapes a blocked reason rather than trusting it as markup", async () => {
    responders["panel-data"] = () =>
      panelData({ apply_ready: false, apply_blocked_reason: "<img src=x onerror=alert(1)>" });
    await loadPanel();
    expect(panelHtml()).toContain("onerror");
    expect(document.getElementById("app")!.querySelector("img")).toBeNull();
  });

  it("warns before filling a form with unverified materials", async () => {
    responders["panel-data"] = () => panelData({ materials_unverified: true });
    await loadPanel();
    expect(panelHtml()).toContain("without evidence checks");
    // Still fillable — the override was a deliberate choice, not a block.
    expect(document.getElementById("fill-btn")).not.toBeNull();
  });

  it("shows no such warning for evidence-backed materials", async () => {
    await loadPanel();
    expect(panelHtml()).not.toContain("without evidence checks");
    expect(document.getElementById("fill-btn")).not.toBeNull();
  });

  it("requests access to just this origin before touching the page", async () => {
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await flush();

    expect(permissionsRequest).toHaveBeenCalledWith({ origins: ["https://boards.greenhouse.io/*"] });
    expect(executeScript).toHaveBeenCalled();
  });

  it("reaches the permission request without awaiting anything first", async () => {
    // chrome.permissions.request only works while the click's user gesture
    // is live, and any await ahead of it can consume that gesture. Asserting
    // it has already fired on the first microtask after the click is how
    // that ordering rule stays enforced rather than just commented.
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await Promise.resolve();

    expect(permissionsRequest).toHaveBeenCalled();
    expect(permissionsContains).not.toHaveBeenCalled();
  });

  it("does not fill when the user declines the permission", async () => {
    (globalThis as any).chrome.permissions.request = vi.fn(async () => false);
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await flush();

    expect(executeScript).not.toHaveBeenCalled();
    expect(document.getElementById("fill-status")!.textContent).toContain("needs permission");
  });

  it("refuses to fill when the active tab has drifted from the rendered job", async () => {
    // The highest-stakes guard in the panel: filling here would type this
    // job's answers into a different company's application form.
    await loadPanel();
    activeTab = { id: 99, url: OTHER_URL };
    document.getElementById("fill-btn")!.click();
    await flush();

    expect(executeScript).not.toHaveBeenCalled();
  });

  it("states that Submit was not pressed after a fill", async () => {
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await flush();
    expect(document.getElementById("fill-status")!.textContent).toContain("Submit was not pressed");
  });

  it("reports what was filled and what still needs the user", async () => {
    executeScript = vi.fn(async () => [
      {
        result: {
          filled: [{ name: "email", value: "a@b.c" }],
          flagged: [{ name: "resume", reason: "attach manually" }],
        },
      },
    ]);
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await flush();

    const status = document.getElementById("fill-status")!.innerHTML;
    expect(status).toContain("email");
    expect(status).toContain("resume");
    expect(status).toContain("attach manually");
  });

  it("escapes field names taken from the visited page", async () => {
    executeScript = vi.fn(async () => [
      { result: { filled: [], flagged: [{ name: "<img src=x onerror=alert(1)>", reason: "x" }] } },
    ]);
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    document.getElementById("fill-btn")!.click();
    await flush();

    const status = document.getElementById("fill-status")!;
    // Assert the name actually rendered before asserting it rendered inert,
    // so this can't pass by the panel simply not having got there yet.
    expect(status.textContent).toContain("onerror");
    expect(status.querySelector("img")).toBeNull();
    expect(status.innerHTML).not.toContain("<img");
  });
});

describe("failure states", () => {
  it("explains an unreachable backend instead of surfacing 'Failed to fetch'", async () => {
    fetchMock.mockImplementation(async () => {
      throw new TypeError("Failed to fetch");
    });
    await loadPanel();
    expect(panelHtml()).toContain("Can't reach CareerPilot");
    expect(panelHtml()).not.toContain("Failed to fetch");
  });

  it("offers a retry that re-reads the tab and recovers", async () => {
    fetchMock.mockImplementationOnce(async () => {
      throw new TypeError("Failed to fetch");
    });
    await loadPanel();
    expect(document.getElementById("retry-btn")).not.toBeNull();

    document.getElementById("retry-btn")!.click();
    await flush();
    expect(panelHtml()).toContain("Backend Engineer");
  });

  it("surfaces the backend's own message for a real API error", async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Something specific broke" }),
    }) as unknown as Response);
    await loadPanel();
    expect(panelHtml()).toContain("Something specific broke");
  });

  it("shows an honest unsupported state for a page CareerPilot does not recognize", async () => {
    activeTab = { id: 42, url: "https://remotive.com/remote-jobs/software-dev/x-1" };
    responders["panel-data"] = () => ({
      tracked: false, job: null, score: null, materials_status: null,
      platform: "unsupported", apply_ready: false, apply_blocked_reason: null,
      materials_unverified: false,
    });
    await loadPanel();
    expect(panelHtml()).toContain("isn't supported");
    expect(document.getElementById("fill-btn")).toBeNull();
  });
});

describe("supported vs unsupported recognition", () => {
  it("offers ingest on an untracked Greenhouse posting instead of applying a dead query", async () => {
    responders["panel-data"] = () => ({
      tracked: false, job: null, score: null, materials_status: null,
      platform: "greenhouse", apply_ready: false, apply_blocked_reason: null,
      materials_unverified: false,
    });
    await loadPanel();
    expect(panelHtml()).toContain("Supported Greenhouse job recognized");
    expect(document.getElementById("ingest-btn")).not.toBeNull();
    expect(document.getElementById("fill-btn")).toBeNull();
  });

  it("recognizes a Lever posting", async () => {
    activeTab = { id: 42, url: LEVER_URL };
    responders["panel-data"] = () =>
      panelData({
        platform: "lever",
        job: { ...panelData().job, url: LEVER_URL, source: "lever", company: "LeverCo", title: "Platform Engineer" },
      });
    await loadPanel();
    expect(panelHtml()).toContain("Platform Engineer");
    expect(panelHtml()).toContain("LeverCo");
    expect(document.getElementById("fill-btn")).not.toBeNull();
  });

  it("does not keep the previous job when the tab becomes unsupported", async () => {
    await loadPanel();
    expect(panelHtml()).toContain("Backend Engineer");
    responders["panel-data"] = () => ({
      tracked: false, job: null, score: null, materials_status: null,
      platform: "unsupported", apply_ready: false, apply_blocked_reason: null,
      materials_unverified: false,
    });
    fireTabChanged("https://example.com/careers/not-a-job");
    await flush();
    expect(panelHtml()).toContain("isn't supported");
    expect(panelHtml()).not.toContain("Backend Engineer");
  });
});

describe("Potential vs Verified Match", () => {
  it("hides a fake percentage for a Potential Match", async () => {
    responders["panel-data"] = () =>
      panelData({
        score: {
          overall_score: 91,
          matched_skills: ["Python"],
          partial_matches: [],
          missing_skills: ["Go"],
          recommendation: "apply",
          rationale: "",
          score_kind: "preliminary",
          match_reasons: ["Python in production"],
        },
      });
    await loadPanel();
    expect(panelHtml()).toContain("Potential Match");
    expect(panelHtml()).not.toContain("91%");
    expect(panelHtml()).toContain("Verify Match");
  });

  it("shows Verified Match details when full-job fit exists", async () => {
    responders["panel-data"] = () =>
      panelData({
        score: {
          overall_score: 88,
          matched_skills: ["Python"],
          partial_matches: [],
          missing_skills: [],
          recommendation: "apply",
          rationale: "",
          score_kind: "verified",
          eligibility_status: "likely_eligible",
          qualification_score: 84,
          preference_score: 72,
          confidence_level: "high",
          match_reasons: ["Shipped Python APIs"],
          watchouts: ["On-site days in SF"],
        },
        must_have: ["Work authorization in the US"],
      });
    await loadPanel();
    expect(panelHtml()).toContain("Verified Match 88%");
    expect(panelHtml()).toContain("Qualification");
    expect(panelHtml()).toContain("Preference");
    expect(panelHtml()).toContain("Eligible based on stated requirements");
    expect(panelHtml()).toContain("high");
    expect(panelHtml()).toContain("Work authorization in the US");
    expect(panelHtml()).toContain("Shipped Python APIs");
    expect(panelHtml()).toContain("On-site days in SF");
    expect(document.getElementById("verify-btn")).toBeNull();
  });

  it("warns on likely ineligible instead of treating the job as a strong target", async () => {
    responders["panel-data"] = () =>
      panelData({
        apply_ready: false,
        apply_blocked_reason: "Eligibility is unresolved or the posting's stated requirements are not met. Review before autofill.",
        review_required: true,
        score: {
          overall_score: 40,
          matched_skills: [],
          partial_matches: [],
          missing_skills: ["US work authorization"],
          recommendation: "skip",
          rationale: "",
          score_kind: "verified",
          eligibility_status: "likely_ineligible",
        },
      });
    await loadPanel();
    expect(panelHtml()).toContain("Likely ineligible");
    expect(panelHtml()).toContain("poor target");
    expect(document.getElementById("fill-btn")).toBeNull();
  });

  it("keeps Potential Match when verification fails", async () => {
    responders["panel-data"] = () =>
      panelData({
        apply_ready: false,
        score: {
          overall_score: 70,
          matched_skills: ["Python"],
          partial_matches: [],
          missing_skills: [],
          recommendation: "consider",
          rationale: "",
          score_kind: "preliminary",
        },
      });
    responders["verified-fit"] = () => {
      throw new Error("should use HTTP error");
    };
    fetchMock.mockImplementation(async (url: string) => {
      const href = String(url);
      if (href.includes("verified-fit")) {
        return { ok: false, status: 502, json: async () => ({ detail: "Unable to extract structured job requirements." }) } as unknown as Response;
      }
      if (href.includes("panel-data")) {
        return { ok: true, status: 200, json: async () => responders["panel-data"]() } as unknown as Response;
      }
      return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
    });
    await loadPanel();
    document.getElementById("verify-btn")!.click();
    await flush(12);
    expect(panelHtml()).toContain("Potential Match");
    expect(panelHtml()).toContain("Remaining a Potential Match");
    expect(panelHtml()).not.toContain("Verified Match");
  });

  it("shows verification stages without a fake percentage", async () => {
    let release: (v: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      release = resolve;
    });
    responders["panel-data"] = () =>
      panelData({
        apply_ready: false,
        score: {
          overall_score: 70,
          matched_skills: ["Python"],
          partial_matches: [],
          missing_skills: [],
          recommendation: "consider",
          rationale: "",
          score_kind: "preliminary",
        },
      });
    fetchMock.mockImplementation(async (url: string) => {
      const href = String(url);
      if (href.includes("verified-fit")) {
        await pending;
        return {
          ok: true,
          status: 200,
          json: async () => ({ overall_score: 88, score_kind: "verified", recommendation: "apply" }),
        } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => responders["panel-data"]() } as unknown as Response;
    });
    await loadPanel();
    document.getElementById("verify-btn")!.click();
    await flush();
    expect(document.getElementById("verify-status")!.textContent).toMatch(/Reading full posting|Checking requirements|Checking eligibility|Calculating match|Almost ready/);
    expect(panelHtml()).not.toContain("70%");
    release(null);
    await flush(8);
  });
});

describe("save and materials", () => {
  it("saves and unsaves without a reload", async () => {
    await loadPanel();
    expect(panelHtml()).toContain(">Save<");
    document.getElementById("save-btn")!.click();
    await flush();
    expect(panelHtml()).toContain(">Saved<");
    expect(panelHtml()).toContain("Unsave");
    document.getElementById("unsave-btn")!.click();
    await flush();
    expect(panelHtml()).toContain(">Save<");
    expect(panelHtml()).not.toContain("Unsave");
  });

  it("shows materials states for prepare", async () => {
    responders["panel-data"] = () => panelData({ materials_status: "missing", apply_ready: false, approval_status: null });
    await loadPanel();
    expect(panelHtml()).toContain("Not prepared");
  });
});

describe("autofill preview", () => {
  it("classifies detected fields without filling until asked", async () => {
    responders["autofill"] = () => ({
      job_id: "greenhouse-abc123",
      platform: "greenhouse",
      fields: { email: "a@b.c", linkedin_url: "https://linkedin.com/in/a", work_authorization: "US citizen", gender: "decline" },
    });
    await loadPanel();
    document.getElementById("preview-btn")!.click();
    await flush();
    expect(panelHtml()).toContain("Email");
    expect(panelHtml()).toContain("Ready");
    expect(panelHtml()).toContain("LinkedIn");
    expect(panelHtml()).toContain("Work authorization");
    expect(panelHtml()).toContain("Needs review");
    expect(panelHtml()).toContain("EEO question — gender");
    expect(panelHtml()).toContain("Manual");
    expect(panelHtml()).toContain("never presses Submit");
    expect(executeScript).not.toHaveBeenCalled();
  });
});

describe("resume documents", () => {
  it("loads versions and does not auto-select when more than one exists for the job", async () => {
    responders["resume-versions"] = () => ({
      versions: [
        resumeVersion({ id: "rv-1", version_number: 1 }),
        resumeVersion({ id: "rv-2", version_number: 2, matches_current_profile: false }),
      ],
      current_job_id: "greenhouse-abc123",
    });
    await loadPanel();
    await flush();
    const select = document.getElementById("resume-version-select") as HTMLSelectElement;
    expect(select).not.toBeNull();
    expect(select.value).toBe("");
    select.value = "rv-2";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await flush();
    expect((document.getElementById("resume-version-select") as HTMLSelectElement).value).toBe("rv-2");
    expect(panelHtml()).toContain("PDF");
    expect(panelHtml()).toContain("DOCX");
  });

  it("preselects the only version for the current job", async () => {
    responders["resume-versions"] = () => ({
      versions: [resumeVersion()],
      current_job_id: "greenhouse-abc123",
    });
    await loadPanel();
    await flush();
    expect((document.getElementById("resume-version-select") as HTMLSelectElement).value).toBe("rv-1");
  });

  it("does not download resume bytes until Fill", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    await loadPanel();
    await flush();
    const fileCalls = fetchMock.mock.calls.filter((call) => String(call[0]).includes("/file"));
    expect(fileCalls).toHaveLength(0);
    const listCalls = fetchMock.mock.calls.filter(
      (call) => String(call[0]).includes("resume-versions") && !String(call[0]).includes("/file"),
    );
    expect(listCalls.length).toBeGreaterThan(0);
  });

  it("attaches the selected PDF before filling and never submits", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    executeScript = vi.fn(async ({ func }: { func: { name?: string } }) => {
      if (func.name === "attachDocumentInPage") {
        return [{ result: { status: "attached", fieldKind: "resume", verifiedName: "resume-v1.pdf", reason: null } }];
      }
      if (func.name === "verifyResumeAttachmentInPage") {
        return [{ result: { attached: true } }];
      }
      return [{ result: { filled: [{ name: "email", value: "a@b.c" }], flagged: [] } }];
    });
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    await flush();
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(executeScript).toHaveBeenCalled();
    const names = executeScript.mock.calls.map((call: any) => call[0].func.name);
    expect(names[0]).toBe("attachDocumentInPage");
    expect(names).toContain("fillFormInPage");
    expect(names).toContain("verifyResumeAttachmentInPage");
    expect(panelHtml()).toContain("Resume attached");
    expect(panelHtml()).toContain("Ready for your review");
    expect(panelHtml()).toContain("Submit was not pressed");
    expect(panelHtml()).not.toContain("Application submitted");
  });

  it("lets the user choose DOCX before attaching", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    responders["resume-file"] = () => ({
      ok: true,
      status: 200,
      headers: {
        get: (name: string) =>
          name.toLowerCase() === "content-type"
            ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            : name.toLowerCase() === "content-disposition"
              ? 'attachment; filename="resume-v1.docx"'
              : null,
      },
      arrayBuffer: async () => new Uint8Array([0x50, 0x4b]).buffer,
    });
    executeScript = vi.fn(async ({ func, args }: { func: { name?: string }; args?: unknown[] }) => {
      if (func.name === "attachDocumentInPage") {
        const payload = args?.[0] as { filename?: string; mimeType?: string };
        expect(payload.filename).toBe("resume-v1.docx");
        expect(payload.mimeType).toContain("wordprocessingml");
        return [{ result: { status: "attached", fieldKind: "resume", verifiedName: "resume-v1.docx", reason: null } }];
      }
      if (func.name === "verifyResumeAttachmentInPage") {
        return [{ result: { attached: true } }];
      }
      return [{ result: { filled: [{ name: "email", value: "a@b.c" }], flagged: [] } }];
    });
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    await flush();
    const docx = document.querySelector('input[name="resume-format"][value="docx"]') as HTMLInputElement;
    docx.checked = true;
    docx.dispatchEvent(new Event("change", { bubbles: true }));
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("format=docx"))).toBe(true);
    expect(panelHtml()).toContain("Resume attached");
  });

  it("shows login when the file download is unauthorized", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    responders["resume-file"] = () => ({
      ok: false,
      status: 401,
      headers: { get: () => null },
      json: async () => ({ detail: "Not authenticated" }),
      arrayBuffer: async () => new ArrayBuffer(0),
    });
    await loadPanel();
    await flush();
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(executeScript).not.toHaveBeenCalled();
    expect(panelHtml()).toMatch(/log in/i);
  });

  it("shows manual upload and does not fill when attachment is blocked", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    executeScript = vi.fn(async ({ func }: { func: { name?: string } }) => {
      if (func.name === "attachDocumentInPage") {
        return [
          {
            result: {
              status: "manual",
              fieldKind: "resume",
              verifiedName: null,
              reason: "Attach manually — this site blocked programmatic file attachment.",
            },
          },
        ];
      }
      return [{ result: { filled: [{ name: "email", value: "a@b.c" }], flagged: [] } }];
    });
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    await flush();
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(executeScript.mock.calls.map((call: any) => call[0].func.name)).toEqual([
      "attachDocumentInPage",
    ]);
    expect(panelHtml()).toContain("Needs manual upload");
    expect(panelHtml()).not.toContain("Ready for your review");
  });

  it("does not mark ready if the resume disappears after fill", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    executeScript = vi.fn(async ({ func }: { func: { name?: string } }) => {
      if (func.name === "attachDocumentInPage") {
        return [{ result: { status: "attached", fieldKind: "resume", verifiedName: "resume-v1.pdf", reason: null } }];
      }
      if (func.name === "verifyResumeAttachmentInPage") {
        return [{ result: { attached: false } }];
      }
      return [{ result: { filled: [{ name: "email", value: "a@b.c" }], flagged: [] } }];
    });
    (globalThis as any).chrome.scripting.executeScript = executeScript;
    await loadPanel();
    await flush();
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(document.getElementById("fill-status")!.textContent).toContain("Resume needs re-attachment");
    expect(document.getElementById("fill-status")!.textContent).not.toContain("Ready for your review");
  });

  it("loads documents on a Lever posting", async () => {
    activeTab = { id: 42, url: LEVER_URL };
    responders["panel-data"] = () =>
      panelData({
        platform: "lever",
        job: {
          id: "lever-abc123",
          title: "Backend Engineer",
          company: "Acme",
          location: "Remote",
          salary: null,
          url: LEVER_URL,
          source: "lever",
          status: "discovered",
          date_scraped: "2026-08-26T06:00:00",
        },
      });
    responders["resume-versions"] = () => ({
      versions: [resumeVersion({ id: "rv-lever", job_id: "lever-abc123" })],
      current_job_id: "lever-abc123",
    });
    await loadPanel();
    await flush();
    expect(document.getElementById("resume-version-select")).not.toBeNull();
    expect((document.getElementById("resume-version-select") as HTMLSelectElement).value).toBe("rv-lever");
  });

  it("stops before filling when the backend download fails", async () => {
    responders["resume-versions"] = () => ({ versions: [resumeVersion()], current_job_id: "greenhouse-abc123" });
    responders["resume-file"] = () => ({
      ok: false,
      status: 502,
      headers: { get: () => null },
      json: async () => ({ detail: "Resume export is unavailable." }),
      arrayBuffer: async () => new ArrayBuffer(0),
    });
    await loadPanel();
    await flush();
    document.getElementById("fill-btn")!.click();
    await flush(12);
    expect(executeScript).not.toHaveBeenCalled();
    expect(document.getElementById("fill-status")!.textContent).toContain("unavailable");
  });

  it("does not show documents on an unsupported site", async () => {
    activeTab = { id: 42, url: "https://example.com/careers/1" };
    responders["panel-data"] = () => ({
      tracked: false, job: null, score: null, materials_status: null,
      platform: "unsupported", apply_ready: false, apply_blocked_reason: null,
      materials_unverified: false,
    });
    await loadPanel();
    expect(document.getElementById("resume-version-select")).toBeNull();
  });

  it("attachment and fill helpers never submit", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const panel = readFileSync(join(here, "../src/sidepanel.ts"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(panel).not.toMatch(/\.submit\s*\(/);
    expect(panel).not.toMatch(/requestSubmit/);
  });
});

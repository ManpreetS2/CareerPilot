// Behavioral tests for the side panel itself. sidepanel.ts has no exports —
// it wires itself to the DOM and the chrome.* APIs on import — so each test
// installs fresh fakes, imports the module, and then drives it the way the
// browser would: by firing the background worker's TAB_CHANGED message and
// by clicking the rendered buttons.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type TabChangedListener = (message: { type?: string; url?: string }) => void;

const JOB_URL = "https://boards.greenhouse.io/acme/jobs/1";
const OTHER_URL = "https://boards.greenhouse.io/other-co/jobs/9";

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

  fetchMock = vi.fn(async (url: string) => {
    const key = Object.keys(responders).find((k) => url.includes(k))!;
    return { ok: true, status: 200, json: async () => responders[key]() } as unknown as Response;
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

    expect(panelHtml()).toContain("91% MATCH");
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

  it("shows the untracked state for a job CareerPilot has not seen", async () => {
    responders["panel-data"] = () => ({
      tracked: false, job: null, score: null, materials_status: null,
      platform: "unsupported", apply_ready: false, apply_blocked_reason: null,
      materials_unverified: false,
    });
    await loadPanel();
    expect(panelHtml()).toContain("isn't tracked");
    expect(document.getElementById("fill-btn")).toBeNull();
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  assertInjectionTarget,
  captureInjectionTarget,
  executeScriptOnTarget,
  InjectionAbortedError,
} from "../src/tab-guard";

describe("injection tab guards", () => {
  let activeTab: { id: number; url: string; status?: string };
  let executeScript: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    activeTab = { id: 7, url: "https://boards.greenhouse.io/acme/jobs/1", status: "complete" };
    executeScript = vi.fn(async () => [{ result: true, documentId: "doc-7" }]);
    vi.stubGlobal("chrome", {
      tabs: {
        query: vi.fn(async () => [activeTab]),
        get: vi.fn(async (tabId: number) => (activeTab.id === tabId ? activeTab : undefined)),
      },
      scripting: { executeScript },
      runtime: { lastError: undefined },
    });
  });

  it("captures tab id, url, and document id from the active tab", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    expect(target).toEqual({ tabId: 7, url: activeTab.url, documentId: "doc-7" });
  });

  it("aborts capture when the active tab URL drifted", async () => {
    await expect(captureInjectionTarget("https://boards.greenhouse.io/other/jobs/9")).rejects.toBeInstanceOf(
      InjectionAbortedError,
    );
  });

  it("aborts when the user switches tabs before injection", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    activeTab = { id: 99, url: "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", status: "complete" };
    await expect(assertInjectionTarget(target)).rejects.toThrow(/switched tabs|gone/i);
  });

  it("aborts when the same tab navigates to another URL", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    activeTab = { ...activeTab, url: "https://boards.greenhouse.io/acme/jobs/2" };
    await expect(assertInjectionTarget(target)).rejects.toThrow(/navigated/i);
  });

  it("aborts when the tab is mid-navigation", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    activeTab = { ...activeTab, status: "loading" };
    await expect(assertInjectionTarget(target)).rejects.toThrow(/navigating/i);
  });

  it("pins documentIds on executeScript and aborts on document mismatch", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    executeScript.mockImplementationOnce(async () => [{ result: { ok: true }, documentId: "doc-OTHER" }]);
    await expect(executeScriptOnTarget(target, () => ({ ok: true }), [])).rejects.toThrow(/reloaded or navigated/i);
  });

  it("returns the script result when the tab and document stay stable", async () => {
    const target = await captureInjectionTarget(activeTab.url);
    executeScript.mockImplementationOnce(async ({ args }: { args: unknown[] }) => [
      { result: { echoed: args[0] }, documentId: "doc-7" },
    ]);
    const result = await executeScriptOnTarget(target, (value: string) => ({ echoed: value }), ["hello"]);
    expect(result).toEqual({ echoed: "hello" });
    expect(executeScript.mock.calls.at(-1)?.[0].target).toEqual({ tabId: 7, documentIds: ["doc-7"] });
  });
});

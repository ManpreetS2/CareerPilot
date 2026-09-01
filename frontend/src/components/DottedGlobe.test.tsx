import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DottedGlobe } from "./DottedGlobe";
import { ThemeProvider } from "../lib/theme";

function mockCanvasContext() {
  const ctx = {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    clip: vi.fn(),
    fillRect: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D,
  );
  return ctx;
}

describe("DottedGlobe", () => {
  let rafIds: number[];
  let observers: { disconnect: ReturnType<typeof vi.fn>; observe: ReturnType<typeof vi.fn> }[];

  beforeEach(() => {
    rafIds = [];
    observers = [];
    mockCanvasContext();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => {
      const id = rafIds.length + 1;
      rafIds.push(id);
      return id;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    class Observer {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
      constructor() {
        observers.push(this);
      }
    }
    vi.stubGlobal("IntersectionObserver", Observer);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("does not start animation under reduced motion and keeps a static highlight", () => {
    localStorage.setItem("careerpilot-reduced-motion", "1");
    render(
      <ThemeProvider>
        <div style={{ width: 900, height: 400 }}>
          <DottedGlobe />
        </div>
      </ThemeProvider>,
    );
    expect(screen.getByTestId("dotted-globe")).toBeInTheDocument();
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  it("cancels animation frames and disconnects observers on unmount", () => {
    const { unmount } = render(
      <ThemeProvider>
        <div style={{ width: 900, height: 400 }}>
          <DottedGlobe />
        </div>
      </ThemeProvider>,
    );
    expect(window.requestAnimationFrame).toHaveBeenCalled();
    unmount();
    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    expect(observers[0]?.disconnect).toHaveBeenCalled();
  });
});

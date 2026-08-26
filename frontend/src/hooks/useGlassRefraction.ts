import { useEffect, useRef } from "react";
import { hasFinePointer } from "../lib/pointer";

export function useGlassRefraction<T extends HTMLElement>(enabled = true) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    const reduce =
      document.documentElement.classList.contains("reduce-motion") ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !hasFinePointer()) return;

    let frame = 0;
    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * 100;
        const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * 100;
        el.style.setProperty("--glass-x", `${x}%`);
        el.style.setProperty("--glass-y", `${y}%`);
      });
    };
    const onLeave = () => {
      el.style.setProperty("--glass-x", "50%");
      el.style.setProperty("--glass-y", "0%");
    };

    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [enabled]);

  return ref;
}

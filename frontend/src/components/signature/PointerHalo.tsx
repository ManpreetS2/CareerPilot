import { useEffect, useState } from "react";
import { hasFinePointer } from "../../lib/pointer";
import { useTheme } from "../../lib/theme";

export function PointerHalo() {
  const { reducedMotion } = useTheme();
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    if (reducedMotion || !hasFinePointer()) {
      setEnabled(false);
      return;
    }
    setEnabled(true);
    const root = document.documentElement;
    const onMove = (event: PointerEvent) => {
      root.style.setProperty("--halo-x", `${event.clientX}px`);
      root.style.setProperty("--halo-y", `${event.clientY}px`);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [reducedMotion]);

  if (!enabled) return null;
  return <div className="pointer-halo" aria-hidden data-testid="pointer-halo" />;
}

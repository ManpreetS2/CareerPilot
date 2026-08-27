import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { hasFinePointer } from "../../lib/pointer";
import { useTheme } from "../../lib/theme";
import { cn } from "../../lib/cn";

export function MagneticLink({
  to,
  className,
  children,
}: {
  to: string;
  className?: string;
  children: ReactNode;
}) {
  const { reducedMotion } = useTheme();
  const ref = useRef<HTMLAnchorElement>(null);
  const enabled = !reducedMotion && hasFinePointer();

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    let frame = 0;
    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const x = event.clientX - (rect.left + rect.width / 2);
        const y = event.clientY - (rect.top + rect.height / 2);
        const tx = Math.max(-8, Math.min(8, x * 0.18));
        const ty = Math.max(-6, Math.min(6, y * 0.18));
        el.style.transform = `translate3d(${tx}px, ${ty}px, 0)`;
      });
    };
    const onLeave = () => {
      cancelAnimationFrame(frame);
      el.style.transform = "translate3d(0, 0, 0)";
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [enabled]);

  return (
    <Link ref={ref} to={to} className={cn(className)} data-magnetic={enabled ? "true" : "false"}>
      {children}
    </Link>
  );
}

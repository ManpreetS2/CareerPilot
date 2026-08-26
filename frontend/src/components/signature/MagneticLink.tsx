import { useEffect, useRef, useState, type ReactNode } from "react";
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
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const enabled = !reducedMotion && hasFinePointer();

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    const onMove = (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const x = event.clientX - (rect.left + rect.width / 2);
      const y = event.clientY - (rect.top + rect.height / 2);
      setOffset({ x: Math.max(-8, Math.min(8, x * 0.18)), y: Math.max(-6, Math.min(6, y * 0.18)) });
    };
    const onLeave = () => setOffset({ x: 0, y: 0 });
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [enabled]);

  return (
    <Link
      ref={ref}
      to={to}
      className={cn(className)}
      style={enabled ? { transform: `translate3d(${offset.x}px, ${offset.y}px, 0)` } : undefined}
    >
      {children}
    </Link>
  );
}

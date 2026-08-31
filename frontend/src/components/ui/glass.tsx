import type { HTMLAttributes } from "react";
import { useGlassRefraction } from "../../hooks/useGlassRefraction";
import { cn } from "../../lib/cn";

type GlassVariant = "panel" | "floating" | "solid" | "atmosphere" | "working" | "subtle" | "surface";

const VARIANT_CLASS: Record<GlassVariant, string> = {
  panel: "glass-panel",
  atmosphere: "glass-panel",
  subtle: "glass-panel",
  working: "glass-panel",
  surface: "glass-panel",
  floating: "glass-floating",
  solid: "solid-surface",
};

export function Glass({
  variant = "panel",
  refract = false,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  variant?: GlassVariant;
  refract?: boolean;
}) {
  const ref = useGlassRefraction<HTMLDivElement>(refract);
  const mapped =
    variant === "floating" ? "floating" : variant === "solid" ? "solid" : "panel";
  return (
    <div
      ref={ref}
      data-glass={mapped}
      className={cn(VARIANT_CLASS[variant], refract && "glass-refract", className)}
      {...props}
    />
  );
}

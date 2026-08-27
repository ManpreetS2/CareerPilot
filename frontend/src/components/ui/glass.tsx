import type { HTMLAttributes } from "react";
import { useGlassRefraction } from "../../hooks/useGlassRefraction";
import { cn } from "../../lib/cn";

type GlassVariant = "atmosphere" | "working" | "floating" | "subtle" | "surface";

const VARIANT_CLASS: Record<GlassVariant, string> = {
  atmosphere: "glass-atmosphere",
  subtle: "glass-atmosphere",
  working: "glass-working",
  surface: "glass-working",
  floating: "glass-floating",
};

export function Glass({
  variant = "working",
  refract = false,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  variant?: GlassVariant;
  refract?: boolean;
}) {
  const ref = useGlassRefraction<HTMLDivElement>(refract);
  return (
    <div
      ref={ref}
      data-glass={variant === "subtle" ? "atmosphere" : variant === "surface" ? "working" : variant}
      className={cn(VARIANT_CLASS[variant], refract && "glass-refract", className)}
      {...props}
    />
  );
}

import type { HTMLAttributes } from "react";
import { useGlassRefraction } from "../../hooks/useGlassRefraction";
import { cn } from "../../lib/cn";

type GlassVariant = "subtle" | "surface" | "floating";

export function Glass({
  variant = "surface",
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
      className={cn(
        variant === "subtle" && "glass-subtle",
        variant === "surface" && "glass-surface",
        variant === "floating" && "glass-floating",
        refract && "glass-refract",
        className,
      )}
      {...props}
    />
  );
}

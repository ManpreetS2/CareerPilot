import { cn } from "../../lib/cn";

const NODES = ["Identity", "Skills", "Experience", "Projects", "Preferences"] as const;

export function ReadinessPath({
  flags,
}: {
  flags: boolean[];
}) {
  return (
    <ol className="space-y-2" data-testid="readiness-path">
      {NODES.map((label, index) => {
        const done = Boolean(flags[index]);
        return (
          <li key={label} className="flex items-center gap-3 text-sm">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                done ? "bg-gradient-to-r from-primary to-accent" : "bg-muted-foreground/35",
              )}
              aria-hidden
            />
            <span className={done ? "text-foreground" : "text-muted-foreground"}>{label}</span>
            <span className="ml-auto text-xs tabular text-muted-foreground">{done ? "Ready" : "Open"}</span>
          </li>
        );
      })}
    </ol>
  );
}

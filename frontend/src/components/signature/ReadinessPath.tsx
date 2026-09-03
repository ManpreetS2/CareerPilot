import { cn } from "../../lib/cn";
import type { EvidenceSourceDetail, RequiredReadinessItem } from "../../lib/profile-gate";

export function ReadinessPath({
  requirements,
  evidenceSources,
}: {
  requirements: RequiredReadinessItem[];
  evidenceSources?: EvidenceSourceDetail[];
}) {
  return (
    <div className="space-y-4" data-testid="readiness-path">
      <ol className="space-y-2">
        {requirements.map((item) => (
          <li key={item.id} className="space-y-1" data-testid={`readiness-required-${item.id}`}>
            <div className="flex items-center gap-3 text-sm">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  item.ready ? "bg-gradient-to-r from-primary to-accent" : "bg-muted-foreground/35",
                )}
                aria-hidden
              />
              <span className={item.ready ? "text-foreground" : "text-muted-foreground"}>{item.label}</span>
              <span className="ml-auto text-xs tabular text-muted-foreground">{item.ready ? "Ready" : "Open"}</span>
            </div>
            {item.helper ? <p className="pl-5 text-xs text-muted-foreground">{item.helper}</p> : null}
          </li>
        ))}
      </ol>
      {evidenceSources?.length ? (
        <div>
          <p className="text-xs text-muted-foreground" id="readiness-evidence-sources-label">
            Evidence sources — not individually required
          </p>
          <ul className="mt-2 space-y-1" aria-labelledby="readiness-evidence-sources-label">
            {evidenceSources.map((source) => (
              <li
                key={source.id}
                className="flex items-center gap-3 text-xs text-muted-foreground"
                data-testid={`readiness-source-${source.id}`}
              >
                <span className="w-16">{source.label}</span>
                <span className="tabular">{source.present ? "Present" : "None"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

import { Glass } from "./ui/glass";
import { APP_NAME, APP_TAGLINE } from "../lib/config";

const POINTS = [
  "Grounded candidate profile",
  "Explainable job fit",
  "Human-approved materials",
];

export function PublicStage() {
  return (
    <div className="public-stage relative mx-auto w-full max-w-md lg:max-w-none">
      <div className="public-stage-grid" aria-hidden />
      <Glass variant="floating" className="relative space-y-5 rounded-[var(--radius-lg)] p-6 sm:p-8">
        <p className="text-sm font-semibold tracking-wide text-primary">{APP_NAME}</p>
        <p className="font-display text-2xl font-semibold leading-snug text-foreground wrap-anywhere">
          {APP_TAGLINE}
        </p>
        <ul className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          {POINTS.map((point) => (
            <li key={point} className="flex gap-3">
              <span
                className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
                aria-hidden
              />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      </Glass>
    </div>
  );
}

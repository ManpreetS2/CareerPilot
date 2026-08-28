import { parseSearchIntent } from "../lib/search-intent";
import type { SearchIntent } from "../lib/types";

export function SearchFilterChips({ intent }: { intent: SearchIntent }) {
  if (!intent.parserReady) return null;
  const chips = [
    ...intent.roles,
    ...intent.locations,
    ...intent.employmentTypes,
    ...intent.workModes,
  ];
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {chips.map((chip) => (
        <span key={chip} className="status-pill bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-200">
          {chip}
        </span>
      ))}
    </div>
  );
}

export function NaturalSearchBar({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const intent = parseSearchIntent(value);
  return (
    <div className="space-y-2">
      <label className="block min-w-0">
        <span className="sr-only">Natural language search</span>
        <input
          className="input"
          placeholder="Natural-language search is not ready yet"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby="natural-search-help"
        />
      </label>
      <p id="natural-search-help" className="text-xs text-muted-foreground">
        Typed filters will appear as chips when a safe parser is available. This field does not
        search yet.
      </p>
      <SearchFilterChips intent={intent} />
    </div>
  );
}

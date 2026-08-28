import { Search } from "lucide-react";
import { X } from "lucide-react";
import type { FormEvent } from "react";

export type FilterChip = {
  id: string;
  label: string;
  onRemove: () => void;
};

export function SearchFilterChips({ chips }: { chips: FilterChip[] }) {
  if (chips.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Active search filters">
      {chips.map((chip) => (
        <li key={chip.id}>
          <span className="status-pill filter-chip inline-flex items-center gap-1 bg-primary/10 text-ink-800 dark:text-ink-100">
            {chip.label}
            <button
              type="button"
              className="rounded-full p-0.5 hover:bg-primary/20"
              aria-label={`Remove ${chip.label}`}
              onClick={chip.onRemove}
            >
              <X className="h-3 w-3" aria-hidden />
            </button>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function NaturalSearchBar({
  value,
  onChange,
  onSubmit,
  chips,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  chips: FilterChip[];
}) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form className="space-y-2" onSubmit={handleSubmit}>
      <label className="relative block min-w-0">
        <span className="sr-only">Search jobs</span>
        <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <input
          className="input jobs-search-input pl-10"
          placeholder="Search roles, locations, or work setup"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby="natural-search-help"
          data-testid="jobs-search-input"
          data-has-query={value.trim() ? "true" : "false"}
        />
      </label>
      <p id="natural-search-help" className="text-xs text-muted-foreground">
        Press Enter to search. An empty field is not a query — chips below are the actual request.
      </p>
      <SearchFilterChips chips={chips} />
    </form>
  );
}

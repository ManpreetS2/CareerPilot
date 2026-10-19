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
    <ul className="flex flex-wrap gap-1.5" aria-label="Active search filters">
      {chips.map((chip) => (
        <li key={chip.id}>
          <span className="status-pill filter-chip inline-flex items-center gap-1 bg-primary/10 text-foreground">
            {chip.label}
            <button
              type="button"
              className="rounded-full p-0.5 hover:bg-primary/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--ring)]"
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
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  chips: FilterChip[];
  disabled?: boolean;
}) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (disabled) return;
    onSubmit();
  }

  return (
    <form className="space-y-2" onSubmit={handleSubmit}>
      <label className="relative block min-w-0">
        <span className="sr-only">Search jobs</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          className="input jobs-search-input h-11 min-h-11 py-2 pl-10"
          placeholder="Search roles, locations, or work setup"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby="natural-search-help"
          data-testid="jobs-search-input"
          data-has-query={value.trim() ? "true" : "false"}
          disabled={disabled}
        />
      </label>
      <p id="natural-search-help" className="sr-only">
        Press Enter to search. Filter chips below refine the request when present.
      </p>
      <SearchFilterChips chips={chips} />
    </form>
  );
}

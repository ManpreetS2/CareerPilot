import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { Sheet, SheetContent } from "./ui/sheet";
import { ErrorBanner } from "./ErrorBanner";
import { api } from "../lib/api";
import { queryKeys } from "../lib/query-keys";
import { chipLabel } from "../lib/search-intent";
import type { SavedSearchItem } from "../lib/types";

export type SavedSearchDraft = {
  query_text: string;
  location?: string | null;
  opportunity?: string | null;
  employment_type: string[];
  work_mode: string[];
  date_posted?: string | null;
};

const CADENCE_OPTIONS = [
  [3, "Every 3 hours"],
  [6, "Every 6 hours"],
  [12, "Every 12 hours"],
  [24, "Daily"],
] as const;

function describeCriteria(search: SavedSearchItem): string {
  // Same label mapping Discover's own filter chips use (JobsPage.tsx),
  // so a search's criteria read identically whether shown here or there.
  const bits: string[] = [];
  if (search.opportunity === "internship") bits.push("Internships");
  else if (search.opportunity === "role") bits.push("Roles");
  bits.push(...search.employment_type.map(chipLabel));
  bits.push(...search.work_mode.map(chipLabel));
  if (search.location) bits.push(search.location);
  return bits.length ? bits.join(" · ") : "All new postings for this search";
}

export function SavedSearchesPanel({
  open,
  onOpenChange,
  currentSearch,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentSearch: SavedSearchDraft | null;
}) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [cadenceHours, setCadenceHours] = useState<number>(12);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.savedSearches,
    queryFn: ({ signal }) => api.listSavedSearches({ signal }),
    enabled: open,
  });

  const matchesQuery = useQuery({
    queryKey: queryKeys.savedSearchMatches(expandedId ?? -1),
    queryFn: ({ signal }) => api.listSavedSearchMatches(expandedId as number, { signal }),
    enabled: open && expandedId != null,
  });

  const createMutation = useMutation({
    mutationFn: (payload: SavedSearchDraft & { label: string; cadence_hours: number }) =>
      api.createSavedSearch(payload),
    onSuccess: () => {
      setLabel("");
      void queryClient.invalidateQueries({ queryKey: queryKeys.savedSearches });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.updateSavedSearch(id, { enabled }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.savedSearches }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteSavedSearch(id),
    onSuccess: (_data, id) => {
      setExpandedId((current) => (current === id ? null : current));
      void queryClient.invalidateQueries({ queryKey: queryKeys.savedSearches });
    },
  });

  const markSeenMutation = useMutation({
    mutationFn: (id: number) => api.markSavedSearchMatchesSeen(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.savedSearches });
      void queryClient.invalidateQueries({ queryKey: queryKeys.savedSearchMatches(id) });
    },
  });

  function toggleExpanded(search: SavedSearchItem) {
    const next = expandedId === search.id ? null : search.id;
    setExpandedId(next);
    if (next != null && search.unseen_match_count > 0) {
      markSeenMutation.mutate(next);
    }
  }

  function submitSave() {
    if (!currentSearch || !label.trim()) return;
    createMutation.mutate({ ...currentSearch, label: label.trim(), cadence_hours: cadenceHours });
  }

  const searches = listQuery.data ?? [];
  const matches = matchesQuery.data ?? [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" title="Saved Searches" className="w-[min(28rem,100%)]">
        <div className="space-y-6 text-sm">
          {currentSearch ? (
            <div className="space-y-3 rounded-[var(--radius-md)] border border-border/70 bg-foreground/[0.03] p-3">
              <p className="font-semibold text-foreground">Save this search</p>
              <p className="truncate text-xs text-muted-foreground">&ldquo;{currentSearch.query_text}&rdquo;</p>
              <label className="block space-y-1">
                <span className="sr-only">Name this search</span>
                <input
                  className="input"
                  placeholder="Name this search"
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  data-testid="saved-search-label-input"
                />
              </label>
              <label className="block space-y-1">
                <span className="text-xs text-muted-foreground">Check for new matches</span>
                <select
                  className="input"
                  value={cadenceHours}
                  onChange={(event) => setCadenceHours(Number(event.target.value))}
                >
                  {CADENCE_OPTIONS.map(([value, optionLabel]) => (
                    <option key={value} value={value}>
                      {optionLabel}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="btn-primary w-full"
                onClick={submitSave}
                disabled={!label.trim() || createMutation.isPending}
                data-testid="save-search-submit"
              >
                {createMutation.isPending ? "Saving…" : "Save"}
              </button>
              <ErrorBanner error={createMutation.error} heading="Couldn't save this search" />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Search Discover for a role, then come back here to save it and get alerted on new matches.
            </p>
          )}

          <ErrorBanner error={listQuery.error} heading="Couldn't load saved searches" />

          {listQuery.isPending ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : searches.length === 0 ? (
            <p className="text-muted-foreground">No saved searches yet.</p>
          ) : (
            <ul className="space-y-3">
              {searches.map((search) => (
                <li key={search.id} className="rounded-[var(--radius-md)] border border-border/70 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-foreground">{search.label}</p>
                      <p className="text-xs text-muted-foreground">{describeCriteria(search)}</p>
                    </div>
                    {search.unseen_match_count > 0 ? (
                      <span
                        className="status-pill shrink-0 bg-primary/10 text-primary"
                        data-testid={`unseen-count-${search.id}`}
                      >
                        {search.unseen_match_count} new
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => toggleExpanded(search)}
                      data-testid={`view-matches-${search.id}`}
                    >
                      {expandedId === search.id ? "Hide matches" : "View matches"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => updateMutation.mutate({ id: search.id, enabled: !search.enabled })}
                    >
                      {search.enabled ? "Pause" : "Resume"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost text-danger"
                      aria-label={`Delete ${search.label}`}
                      onClick={() => deleteMutation.mutate(search.id)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </button>
                  </div>
                  {expandedId === search.id ? (
                    <div className="mt-3 space-y-2 border-t border-border/70 pt-3">
                      {matchesQuery.isPending ? (
                        <p className="text-xs text-muted-foreground">Loading matches…</p>
                      ) : matches.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No matches yet.</p>
                      ) : (
                        matches.map((match) => (
                          <a
                            key={match.job_id}
                            href={match.url}
                            target="_blank"
                            rel="noreferrer"
                            className="block rounded-lg border border-border/70 bg-foreground/[0.03] p-2 hover:border-primary/30"
                          >
                            <p className="text-sm font-medium text-foreground">{match.title}</p>
                            <p className="text-xs text-muted-foreground">
                              {match.company}
                              {match.location ? ` · ${match.location}` : ""}
                            </p>
                          </a>
                        ))
                      )}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

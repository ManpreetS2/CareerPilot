import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SavedSearchesPanel, type SavedSearchDraft } from "./SavedSearchesPanel";
import { api } from "../lib/api";
import { createTestQueryClient } from "../test/render";
import type { SavedSearchItem, SavedSearchMatchItem } from "../lib/types";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      listSavedSearches: vi.fn(),
      createSavedSearch: vi.fn(),
      updateSavedSearch: vi.fn(),
      deleteSavedSearch: vi.fn(),
      listSavedSearchMatches: vi.fn(),
      markSavedSearchMatchesSeen: vi.fn(),
    },
  };
});

const draft: SavedSearchDraft = {
  query_text: "backend engineer intern",
  location: "Remote",
  opportunity: "internship",
  employment_type: ["internship"],
  work_mode: [],
  date_posted: null,
};

const savedSearch: SavedSearchItem = {
  id: 1,
  label: "Backend intern roles",
  query_text: "backend engineer intern",
  location: "Remote",
  opportunity: "internship",
  employment_type: ["internship"],
  work_mode: [],
  date_posted: null,
  cadence_hours: 12,
  enabled: true,
  last_run_at: "2026-09-01T00:00:00Z",
  created_at: "2026-08-30T00:00:00Z",
  unseen_match_count: 2,
};

const oneSearch: SavedSearchItem[] = [savedSearch];

const oneMatch: SavedSearchMatchItem[] = [
  {
    job_id: "greenhouse-xyz",
    title: "Backend Engineering Intern",
    company: "Acme",
    location: "Remote",
    url: "https://boards.greenhouse.io/acme/jobs/1",
    source: "greenhouse",
    date_posted: "2026-08-29",
    first_seen_at: "2026-08-30T00:00:00Z",
    seen_at: null,
  },
];

function renderPanel(currentSearch: SavedSearchDraft | null = draft) {
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <SavedSearchesPanel open onOpenChange={onOpenChange} currentSearch={currentSearch} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

describe("SavedSearchesPanel", () => {
  it("saves the current search with a label and cadence", async () => {
    vi.mocked(api.listSavedSearches).mockResolvedValue([]);
    vi.mocked(api.createSavedSearch).mockResolvedValue(savedSearch);
    const user = userEvent.setup();
    renderPanel();

    const submit = await screen.findByTestId("save-search-submit");
    expect(submit).toBeDisabled();

    await user.type(screen.getByTestId("saved-search-label-input"), "Backend intern roles");
    expect(submit).not.toBeDisabled();
    await user.click(submit);

    await waitFor(() =>
      expect(api.createSavedSearch).toHaveBeenCalledWith({
        query_text: "backend engineer intern",
        location: "Remote",
        opportunity: "internship",
        employment_type: ["internship"],
        work_mode: [],
        date_posted: null,
        label: "Backend intern roles",
        cadence_hours: 12,
      }),
    );
  });

  it("hides the save form when there is no active search", async () => {
    vi.mocked(api.listSavedSearches).mockResolvedValue([]);
    renderPanel(null);

    await screen.findByText(/no saved searches yet/i);
    expect(screen.queryByTestId("saved-search-label-input")).not.toBeInTheDocument();
  });

  it("lists saved searches with an unseen-match badge", async () => {
    vi.mocked(api.listSavedSearches).mockResolvedValue(oneSearch);
    renderPanel();

    expect(await screen.findByText("Backend intern roles")).toBeInTheDocument();
    expect(screen.getByTestId("unseen-count-1")).toHaveTextContent("2 new");
  });

  it("loads matches and marks them seen when expanded", async () => {
    vi.mocked(api.listSavedSearches).mockResolvedValue(oneSearch);
    vi.mocked(api.listSavedSearchMatches).mockResolvedValue(oneMatch);
    vi.mocked(api.markSavedSearchMatchesSeen).mockResolvedValue({ updated: 2 });
    const user = userEvent.setup();
    renderPanel();

    await user.click(await screen.findByTestId("view-matches-1"));

    expect(await screen.findByText("Backend Engineering Intern")).toBeInTheDocument();
    await waitFor(() => expect(api.markSavedSearchMatchesSeen).toHaveBeenCalledWith(1));
  });

  it("toggles enabled and deletes a saved search", async () => {
    vi.mocked(api.listSavedSearches).mockResolvedValue(oneSearch);
    vi.mocked(api.updateSavedSearch).mockResolvedValue({ ...savedSearch, enabled: false });
    vi.mocked(api.deleteSavedSearch).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPanel();

    await screen.findByText("Backend intern roles");
    await user.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(api.updateSavedSearch).toHaveBeenCalledWith(1, { enabled: false }));

    await user.click(screen.getByRole("button", { name: /delete backend intern roles/i }));
    await waitFor(() => expect(api.deleteSavedSearch).toHaveBeenCalledWith(1));
  });
});

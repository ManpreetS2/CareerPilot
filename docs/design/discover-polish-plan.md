# Discover UI polish — implementation plan

## Audit findings (highest impact)

1. **Toolbar vertical bloat** — PageHeader actions + NaturalSearchBar (input + help + chips) + URL/filter/sort row stack three dense bands before results. Help text is always visible.
2. **Repetitive Discover language** — Sidebar “Discover”, page title “Jobs”, description mentioning Discover, and empty-state “Browse Discover”.
3. **Muted secondary contrast** — `--muted-foreground: #5a5568` on `#f7f6fb` is soft; card meta and nav labels read weak.
4. **Job card hierarchy** — Title/company/meta compete; fit badge packs score+tier without separating confidence in compact mode.
5. **Verified Fit vs Match % vs Confidence** — Compact badge hides confidence; ScoreAssembly shows a large % without an explicit “Verified Fit” label next to it.
6. **Selection / focus** — Selected card uses heavy glow; focus rings exist but card select affordance can be clearer.

## Intentional (do not change)

- Potential Match hiding preliminary percentages (product honesty).
- Synthetic demo disclosure pills.
- Scoring / matching algorithms and API contracts.
- Saved searches, filters, sort options, job URL ingest.

## Scope

- `JobsPage`, `NaturalSearchBar`, `JobCard`, `MatchBadge`, `ScoreAssembly`, `FitScorePanel`, `AppShell`, token contrast in `index.css`.
- Update unit tests that assert badge copy.
- Screenshots for draft PR; do not merge.

# Roadmap: Fantasy Movie League

## Overview

Existing app (React/Vite frontend, FastAPI backend, JSON data store) gets a visual reskin to match new "Movie League" mockups — dark theme with gold accent, serif titles, status-coded roster table, and a richer movie-detail view. Single UI-only phase; no backend or data-model changes.

## Phases

- [x] **Phase 1: UI Redesign** - Reskin frontend to match new mockups (team/roster view + movie detail view), preserving existing functionality

- [ ] **Phase 2: Live API Enrichment** - Fetch ratings/financials from free APIs (OMDb + TMDB), cached and non-destructive

## Phase Details

### Phase 1: UI Redesign
**Goal**: Frontend matches the new "Movie League" dark design system (team/roster view and movie detail view) while all existing functionality keeps working
**Depends on**: Nothing (first phase)
**Requirements**: UI-01, UI-02, UI-03, UI-04
**Success Criteria** (what must be TRUE):
  1. Team/roster page visually matches the "My Team" mockup (slot table, status pills, pts/proj/owned columns) — per the locked `01-UI-SPEC.md` mapping, "slot" is relabeled ROUND (no fictional slot categories), PROJ is omitted (no projection model exists in real data), and OWNED is repurposed as WATCHED (`who_watched` field)
  2. Movie detail view visually matches the "Nightfall Country" mockup (hero header, points ledger, campaign tracker, ownership sidebar)
  3. Design tokens (color, type, spacing) are consistent across all components, not just the two redesigned views
  4. Existing behaviors (data fetch, expand/collapse breakdown, TMDB enrich trigger) still work after the redesign
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Design tokens, fonts, and full component CSS contract (styles.css + index.html)
- [x] 01-02-PLAN.md — App shell: header restyle, two-column layout, static THIS WEEK sidebar, empty/error copy
- [x] 01-03-PLAN.md — Roster table shell: Leaderboard/PlayerCard stat header + ROUND/TITLE/STATUS/PTS/WATCHED columns
- [x] 01-04-PLAN.md — Movie detail: status pill roster row + expanded hero/stat-strip/points-ledger/campaign-tracker/ownership panel

### Phase 2: Live API Enrichment
**Goal**: Film ratings and financials populate from free public APIs on a manual refresh trigger, cached so repeat runs cost no API calls, and never overwriting hand-entered values
**Depends on**: Nothing (backend-only; independent of Phase 1)
**Requirements**: API-01, API-02, API-03, API-04, API-05
**Success Criteria** (what must be TRUE):
  1. A manually-triggered bulk enrich fills `imdb` (real IMDb rating) and `rt_crit` from OMDb, and `budget`/`gross` from TMDB, for films that have no hand-entered value
  2. Re-running enrichment immediately after a first run makes zero outbound API calls (all served from cache)
  3. A hand-entered value is never silently overwritten — provenance distinguishes `manual` from `fetched`, and overwriting requires an explicit force flag
  4. A single bulk run cannot exceed a configured per-run call cap, so the OMDb 1,000/day free quota cannot be exhausted by accident
  5. Both API keys are documented in `.env.example` and never appear in logs
**Non-goals** (explicitly out of scope):
  - `rt_aud` and `letterboxd` — no free API exists for either; they stay manual
  - `compute_movie_scores()` — the scoring formula lives in the user's spreadsheet; without it the standings will NOT change even after enrichment (see 02-RESEARCH.md §3)
  - Scheduled/background refresh — manual trigger only
**Plans**: TBD

Plans:
- [ ] 02-01: TBD (created during /gsd-plan-phase)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. UI Redesign | 4/4 | Complete | 2026-08-18 |
| 2. Live API Enrichment | 0/TBD | Not started | - |

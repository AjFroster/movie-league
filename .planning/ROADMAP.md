# Roadmap: Fantasy Movie League

## Overview

Existing app (React/Vite frontend, FastAPI backend, JSON data store) gets a visual reskin to match new "Movie League" mockups — dark theme with gold accent, serif titles, status-coded roster table, and a richer movie-detail view. Single UI-only phase; no backend or data-model changes.

## Phases

- [ ] **Phase 1: UI Redesign** - Reskin frontend to match new mockups (team/roster view + movie detail view), preserving existing functionality

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
- [ ] 01-02-PLAN.md — App shell: header restyle, two-column layout, static THIS WEEK sidebar, empty/error copy
- [ ] 01-03-PLAN.md — Roster table shell: Leaderboard/PlayerCard stat header + ROUND/TITLE/STATUS/PTS/WATCHED columns
- [ ] 01-04-PLAN.md — Movie detail: status pill roster row + expanded hero/stat-strip/points-ledger/campaign-tracker/ownership panel

## Progress

**Execution Order:**
Phase 1 only (single-phase scaffold).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. UI Redesign | 0/4 | Not started | - |

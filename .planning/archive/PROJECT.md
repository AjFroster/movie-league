# Fantasy Movie League

## What This Is

A leaderboard app for tracking a friend group's fantasy movie league. Players draft movies into slots (Best Picture, Director, Lead Perf, Screenplay, Craft, Indie Flex, Bench, Vault) and score points from nominations, wins, critics' mentions, and box office. React/Vite frontend, FastAPI backend, single JSON file as the data store.

## Core Value

Players can see accurate, current rankings and per-movie score breakdowns for their league.

## Requirements

### Validated

<!-- Shipped and confirmed valuable, per HANDOFF.md — existing dark "gaming leaderboard" build. -->

- ✓ Leaderboard showing ranked owners
- ✓ Player card with embedded movie cards, expandable score breakdown
- ✓ TMDB enrichment (budget/gross/rating auto-fill) via `/enrich` endpoint
- ✓ Manual score entry via `PUT /api/movies/{owner}/{round}`

### Active

<!-- Current scope: this UI redesign phase. -->

- [ ] Redesign frontend to match new "Movie League" mockups (dark theme, gold accent, serif titles)
- [ ] Team/roster view (slot table: Best Picture, Director, Lead Perf, etc. with status pill, pts, proj, owned%)
- [ ] Movie/title detail view (hero header, points ledger with progress bars, campaign tracker timeline, ownership sidebar)
- [ ] Extract and apply consistent design tokens (color, type, spacing) across the app

### Out of Scope

- Backend scoring formula automation — deferred per HANDOFF.md, not part of this UI phase
- RT/Letterboxd score API integration — no public API, manual entry stays
- New backend endpoints/data model changes — this phase is UI-only, existing API contract stays as-is

## Context

- Existing app already functional: FastAPI backend + React/Vite frontend, dark "gaming leaderboard" aesthetic already in place (see `.planning/codebase/` for full map).
- User supplied two Claude-UI-Builder mockup screenshots: a "My Team" roster view and a "Nightfall Country" movie detail view, both for a reskin called "Movie League" — darker/more refined visual system than current build, gold/amber accent, serif display type, mono/condensed caps for labels, color-coded status dots.
- `.planning/codebase/` already has ARCHITECTURE.md, STACK.md, STRUCTURE.md, CONVENTIONS.md, CONCERNS.md, INTEGRATIONS.md, TESTING.md, REVIEW.md from a prior `/gsd-map-codebase` run.
- This PROJECT.md/ROADMAP.md/REQUIREMENTS.md/STATE.md scaffold was created manually (minimal, single-phase) to unlock `/gsd-ui-phase`, not via full `/gsd-new-project` — app already exists, only the UI phase machinery was missing.

## Constraints

- **Tech stack**: React 18 + Vite, plain CSS (`styles.css`, no component library, no Tailwind) — keep this stack, don't introduce a new one for this reskin
- **API contract**: Backend routes/response shapes must not change — this is a frontend-only visual phase
- **Existing functionality**: Expand/collapse score breakdown, TMDB enrich trigger, data fetching must keep working after redesign

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Minimal manual planning scaffold instead of full `/gsd-new-project` | App already built and working; only needed enough structure to run `/gsd-ui-phase` for the reskin | — Pending |
| UI-only phase, no backend changes | Mockups are visual-only; scoring/data model untouched | — Pending |

---
*Last updated: 2026-08-17 after manual scaffold creation for UI redesign phase*

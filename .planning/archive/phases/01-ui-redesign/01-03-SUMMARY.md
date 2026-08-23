---
phase: 01-ui-redesign
plan: 03
subsystem: ui
tags: [react, jsx, roster-table, design-tokens]

# Dependency graph
requires:
  - phase: 01-ui-redesign/01-01
    provides: "Full CSS class contract (player-card, stat-block, roster-table, roster-header-row, player-meta-line) in frontend/src/styles.css"
provides:
  - "Leaderboard.jsx forwarding ownerCount={rows.length} to every PlayerCard"
  - "PlayerCard.jsx rewritten to roster-table layout: meta line + stat-block header (TOTAL/RATING/FINANCIAL/WATCH, conditional PENALTIES) + roster-header-row + MovieCard rows"
  - "Prop contract for MovieCard.jsx (Plan 01-04): <MovieCard key={m.round} movie={m} ownerCount={ownerCount} />"
affects: [01-ui-redesign/01-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stat-block header pattern (label-above-number) replacing emoji ScoreChip pills"
    - "Conditional PENALTIES stat block ensures the visible stat blocks always reconcile arithmetically to TOTAL"
    - "ownerCount prop threaded Leaderboard -> PlayerCard -> MovieCard for 'X OF Y' / 'X/Y watched' fraction display"

key-files:
  created: []
  modified:
    - frontend/src/components/Leaderboard.jsx
    - frontend/src/components/PlayerCard.jsx

key-decisions:
  - "Followed the plan's literal JSX verbatim for both files (no deviation) since the code blocks were fully specified, including exact prop names, ordinal-suffix table, and the PENALTIES reconciliation logic"
  - "Ran npm install in this worktree checkout before npm run build since node_modules was absent (worktree checkouts don't inherit main-repo node_modules) — a Rule 3 blocking-issue fix, not a scope change"

patterns-established:
  - "Reconciling stat header: TOTAL block always shown; RATING/FINANCIAL/WATCH always shown; PENALTIES shown only when summary.penalties !== 0, replacing the old always-hidden ⚠ Penalty chip logic"

requirements-completed: [UI-01, UI-04]

# Metrics
duration: 3min
completed: 2026-08-18
---

# Phase 01 Plan 03: Leaderboard & PlayerCard Roster-Table Restructure Summary

**Rebuilt `Leaderboard.jsx`/`PlayerCard.jsx` from the old card-grid-of-tiles layout into the mockup's roster-table layout — meta line + stat-block header (TOTAL/RATING/FINANCIAL/WATCH, plus PENALTIES when nonzero) above a ROUND/TITLE/STATUS/PTS/WATCHED table, flat rank-1 amber accent, `ownerCount` threaded through to `MovieCard`.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-08-18T21:21:20Z
- **Completed:** 2026-08-18T21:24:09Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `Leaderboard.jsx` now forwards `ownerCount={rows.length}` alongside `summary` to every `PlayerCard`
- `PlayerCard.jsx` rewritten: removed `RANK_COLORS` map, `MAX_SCORE` progress bar, `ScoreChip` emoji component, and inline `--rank-color` styles
- New owner header: `player-meta-line` ("2ND OF 5 · 6 ROUNDS" pattern from `rank`/`ownerCount`/`rounds_played`) + `player-name` + `player-stats` stat-block cluster (TOTAL/RATING/FINANCIAL/WATCH, PENALTIES conditional on nonzero)
- Rank-1 owner gets `player-card rank-1` (flat amber top-border + amber rank number via Plan 01-01's CSS); all other ranks get no special color
- Replaced `.movie-grid` tile layout with `.roster-table` wrapping a `.roster-header-row` (ROUND/TITLE/STATUS/PTS/WATCHED — SLOT relabeled ROUND, PROJ omitted, OWNED relabeled WATCHED) plus `<MovieCard>` rows, each now receiving `ownerCount`
- `npm run build` passes (after installing this worktree's missing `node_modules`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Forward ownerCount from Leaderboard to PlayerCard** - `1af4cb7` (feat)
2. **Task 2: Restructure PlayerCard into meta line + stat-block header + roster table** - `a3b6a07` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `frontend/src/components/Leaderboard.jsx` - Adds `ownerCount={rows.length}` prop alongside existing `summary` prop for every `PlayerCard`
- `frontend/src/components/PlayerCard.jsx` - Full rewrite: meta line, stat-block header with conditional PENALTIES block, `.roster-table`/`.roster-header-row` column headers, `ownerCount` forwarded to `MovieCard`; old rank-color/ScoreChip/progress-bar code removed

## Decisions Made
- Executed the plan's literal JSX verbatim — no deviations from the specified code blocks, prop names, or class names.
- Installed `node_modules` in this worktree (Rule 3 — blocking issue) since the worktree checkout did not inherit the main repo's `node_modules` and `npm run build` failed with `vite: not found` until dependencies were installed. This did not touch any tracked files (`node_modules`/`dist` are gitignored) and no lockfile changes were needed (`package-lock.json` already existed and was used as-is).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing node_modules to run the required build verification**
- **Found during:** Task 2 (PlayerCard.jsx restructure, running the `npm run build` acceptance criterion)
- **Issue:** This worktree checkout had no `frontend/node_modules`, so `npm run build` failed immediately with `sh: 1: vite: not found` — blocking the mandatory build verification for Task 2.
- **Fix:** Ran `npm install` inside `frontend/` using the existing `package-lock.json` (no dependency versions changed).
- **Files modified:** None tracked (node_modules and dist are gitignored; git status confirmed only `PlayerCard.jsx` as modified after install).
- **Verification:** `npm run build` subsequently succeeded (`✓ 35 modules transformed`, `built in 1.09s`).
- **Committed in:** N/A (no tracked files changed by the install itself)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to run the plan's own mandated build verification; no scope creep, no tracked-file changes beyond the two files the plan specified.

## Issues Encountered
None beyond the missing-node_modules blocker documented above, which was resolved without touching any tracked files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `PlayerCard.jsx` now calls `<MovieCard key={m.round} movie={m} ownerCount={ownerCount} />` per the prop contract this plan defines for Plan 01-04 — Plan 01-04's `MovieCard.jsx` must accept `movie` and `ownerCount` props and render its own `.roster-row` matching `.roster-header-row`'s `grid-template-columns`.
- Until Plan 01-04 lands, the dev-server visual check (status pills, detail rows) will look unstyled/incomplete inside each roster row — expected per this plan's own `<verification>` note, not a regression.
- No blockers for Plan 01-04.

---
*Phase: 01-ui-redesign*
*Completed: 2026-08-18*

## Self-Check: PASSED

- FOUND: frontend/src/components/Leaderboard.jsx
- FOUND: frontend/src/components/PlayerCard.jsx
- FOUND: 1af4cb7 (Task 1 commit)
- FOUND: a3b6a07 (Task 2 commit)

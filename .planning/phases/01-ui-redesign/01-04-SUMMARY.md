---
phase: 01-ui-redesign
plan: 04
subsystem: ui
tags: [react, jsx, status-pill, movie-detail]

# Dependency graph
requires: ["01-01"]
provides:
  - "MovieCard.jsx rewritten to render a .roster-row per round with derived status pill and expanding movie-detail panel"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Derived status precedence: no-pick guard first, then penalty check, then awaiting/scored (reconciled per UI-SPEC token table + prose)"
    - "Dynamic inline style={{ width }} on .ledger-bar-fill for illustrative capped progress bars (documented exception to no-inline-styles rule)"

key-files:
  created: []
  modified:
    - frontend/src/components/MovieCard.jsx

key-decisions:
  - "Precedence order no-pick -> at-risk -> awaiting -> scored, matching both the UI-SPEC token table's !m.movie-first guard and its 'penalty check first' prose among the remaining three states"
  - "penalty_notes rendered whenever penalties !== 0 AND penalty_notes is truthy, using .penalty-note (Body role) per UI-SPEC Typography, not .stat-block-caption"
  - "financialCaption renders bare em-dash when both budget and gross are null, avoiding the 'BUDGET $—M / GROSS $—M' nonsense string"
  - "rt_aud included in ratingCaption alongside rt_crit/letterboxd so no real rating data is silently dropped"

requirements-completed: [UI-02, UI-04]

# Metrics
duration: 12min
completed: 2026-08-18
---

# Phase 01 Plan 04: Movie Card Roster Row & Detail Panel Summary

**Rewrote `MovieCard.jsx` to render each round as a `.roster-row` with a derived status pill (NO PICK/AWAITING SCORE/AT RISK/SCORED) matching PlayerCard's header grid, expanding on click into the full mockup-style movie-detail panel (hero placeholder, stat strip, capped points ledger, penalty explanation, illustrative campaign tracker, real ownership callout) while preserving the exact pre-existing expand/collapse accessibility behavior.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-18T21:20:00Z (approx, wave 2 parallel start)
- **Completed:** 2026-08-18T21:32:00Z (approx)
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Rewrote `MovieCard.jsx` (previously a `.movie-card` tile with emoji mini-chips) to a `.roster-row` grid row matching the shared column layout with PlayerCard's header row: ROUND, TITLE, STATUS PILL, PTS, WATCHED
- Implemented `statusFor(m)` deriving NO PICK / AT RISK / AWAITING SCORE / SCORED from real `Movie` fields, with precedence order reconciled per UI-SPEC (no-pick guard first, then penalty check, then awaiting/scored)
- Preserved the existing `isPending`/`handleToggle`/keyboard-accessibility logic byte-identical to the pre-redesign version (same `m.imdb === null && m.gross === null && m.rt_crit === null` condition gates both AWAITING SCORE and click-disabled state)
- Built the full expanded `MovieDetail` panel: `.movie-hero` gradient placeholder, serif movie title, meta line (`R{round} · {owner}'s pick`), 4-block `.stat-strip` (ROUND TOTAL, RATING, ROI, WATCHED), 3-column `.detail-columns` (POINTS LEDGER, CAMPAIGN TRACKER, LEAGUE OWNERSHIP)
- Points ledger renders only nonzero categories with bars scaled to documented illustrative caps (Rating 40, Financial 15, Watch 10, Penalty 30) using `.ledger-bar-fill` (which carries `display: block; height: 100%` from Plan 01-01, making the inline `width` percentage actually render)
- `penalty_notes` renders under the ledger via `.penalty-note` (Body role) whenever `penalties !== 0` and notes text is present — carries forward the pre-redesign behavior that explained AT RISK penalties
- `rt_aud` included in the ratings caption alongside `rt_crit`/`letterboxd` so no real audience-rating data is dropped
- `financialCaption` renders a bare `—` when both `budget` and `gross` are null, instead of the malformed `BUDGET $—M / GROSS $—M` string
- CAMPAIGN TRACKER is a fixed, hardcoded 3-item timeline (amber/blue/gray dots) with an "Illustrative — not live data" note; no per-movie point-delta numbers invented
- LEAGUE OWNERSHIP shows only the real `Picked by {owner} · Round {round}` callout; "SIMILAR AVAILABLE" omitted entirely
- `npm run build` passes (installed frontend `node_modules` into this worktree since it wasn't present — gitignored, not committed)

## Task Commits

Each task was committed atomically:

1. **Task 1: Roster row shell with derived status pill** - `f4401a7` (feat)
2. **Task 2: Full expanded movie-detail panel** - `09980f6` (feat)

**Plan metadata:** (pending — see final commit below)

## Files Created/Modified

- `frontend/src/components/MovieCard.jsx` - Full rewrite: `.roster-row` shell with `statusFor()` derived status pill (Task 1), then `MovieDetail` expanded panel with hero, stat strip, points ledger, penalty note, campaign tracker, and ownership callout (Task 2)

## Decisions Made

- Followed the plan's literal two-task JSX blocks exactly as written, including all "Key decisions baked into this code" callouts (precedence reconciliation, penalty-note requirement, rt_aud inclusion, bare em-dash for null budget+gross, illustrative ledger caps, no per-row sub-captions, static campaign tracker content, ownership-only sidebar).
- No architectural deviations; props contract (`movie`, `ownerCount`) consumed exactly as specified by the cross-plan contract with sibling Plan 01-03's PlayerCard.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `frontend/node_modules` was absent in this worktree (only present in the main repo checkout). Ran `npm install` inside the worktree's `frontend/` directory to make `npm run build` (Task 2's verification command) runnable. `node_modules/` is gitignored and was not committed — this is a worktree-local dependency install, not a plan deviation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `MovieCard.jsx` now fully implements the roster-row + expanded-detail contract from `01-UI-SPEC.md` and consumes the `movie`/`ownerCount` props exactly as defined by sibling Plan 01-03 (PlayerCard).
- No blockers for downstream plans. This plan touched only `frontend/src/components/MovieCard.jsx` per its file-ownership boundary; `App.jsx`/`ThisWeekSidebar.jsx` (01-02) and `Leaderboard.jsx`/`PlayerCard.jsx` (01-03) were not touched.
- Full app visual verification (rendering the roster table end-to-end) depends on all three wave-2 plans (01-02, 01-03, 01-04) being merged together, since PlayerCard (01-03) is what actually renders `<MovieCard>` inside a `.roster-table`.

---
*Phase: 01-ui-redesign*
*Completed: 2026-08-18*

## Self-Check: PASSED

- FOUND: frontend/src/components/MovieCard.jsx
- FOUND: f4401a7 (Task 1 commit)
- FOUND: 09980f6 (Task 2 commit)

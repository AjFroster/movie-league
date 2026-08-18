---
phase: 01-ui-redesign
plan: 02
subsystem: ui
tags: [react, jsx, app-shell, layout, static-widget]

# Dependency graph
requires:
  - phase: 01-ui-redesign/01-01
    provides: "Full CSS class contract (app-layout, this-week*, header*, empty-state*, state-msg) in frontend/src/styles.css"
provides:
  - "ThisWeekSidebar.jsx: static, non-fetching THIS WEEK widget component"
  - "App.jsx rewired to the new two-column app-layout shell, mono-caps header, and locked empty/error copy"
affects: [01-ui-redesign/01-03, 01-ui-redesign/01-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static illustrative widget pattern: zero-prop, zero-state component rendering hardcoded content, explicitly labeled 'Illustrative — not live data' to prevent confusion with live data"
    - "Conditional layout gating: app-layout grid (with sidebar) only renders when rows is a non-empty array; loading/error/empty states render standalone state-msg/empty-state blocks instead"

key-files:
  created:
    - frontend/src/components/ThisWeekSidebar.jsx
  modified:
    - frontend/src/App.jsx

key-decisions:
  - "Installed frontend node_modules via npm install (Rule 3 - blocking) since the worktree had no dependencies installed and 'vite' was not found, blocking the build verification step"
  - "Omitted the mockup's fictional nav bar (League/My Team/Titles/Trades/Calendar) and 'SAVE LINEUP' CTA per plan's explicit scope decision — app has no routing and no lineup-editing UI"
  - "Kept existing 'Fantasy Movie League' header title text unchanged (only typography restyled) since UI-SPEC's Copywriting Contract defines no new app-title copy"

patterns-established:
  - "Static illustrative widgets carry a small muted disclaimer ('Illustrative — not live data') per UI-SPEC's Illustrative Widgets section, distinguishing them from live-data-backed UI"

requirements-completed: [UI-03, UI-04]

# Metrics
duration: 6min
completed: 2026-08-18
---

# Phase 01 Plan 02: App Shell Layout & THIS WEEK Widget Summary

**Rewired `App.jsx` to the new mono-caps header and two-column `app-layout` grid (roster + THIS WEEK sidebar), added the static illustrative `ThisWeekSidebar` component, and updated error/empty-state copy to UI-SPEC's locked Copywriting Contract strings, while preserving the existing fetch-on-mount/error-catch logic byte-for-byte.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-08-18T21:17:40Z (approx, following 01-01 completion)
- **Completed:** 2026-08-18T21:23:40Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created `frontend/src/components/ThisWeekSidebar.jsx`: a pure static component (no props, no state, no fetch) rendering the two locked THIS WEEK items plus the "Illustrative — not live data" disclaimer
- Rewrote `frontend/src/App.jsx`: mono-caps `header-mark` + `<h1>`/`<p>` header (replacing the old serif/gradient treatment), two-column `.app-layout` grid wrapping `.app-main` (Leaderboard) and `<ThisWeekSidebar />`, new empty-state block for zero-length API responses, and the exact locked error copy string
- Preserved existing `useEffect(() => { api.leaderboard().then(setRows).catch((e) => setError(e.message)) }, [])` fetch logic unchanged
- Omitted the mockup's fictional nav bar and SAVE LINEUP CTA per the plan's explicit scope decision (no routing library, no lineup-editing UI in this app)
- `npm run build` passes (after installing missing frontend dependencies — see Deviations)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create the static ThisWeekSidebar component** - `750c09c` (feat)
2. **Task 2: Wire App.jsx layout, header, THIS WEEK, and copy updates** - `03f23df` (feat)

**Plan metadata:** (pending — see final commit below)

## Files Created/Modified
- `frontend/src/components/ThisWeekSidebar.jsx` - New static THIS WEEK sidebar widget, hardcoded content, no data fetching
- `frontend/src/App.jsx` - App shell rewired: mono-caps header, two-column app-layout grid, ThisWeekSidebar wiring, empty/error state copy updated to locked UI-SPEC strings, existing fetch logic unchanged

## Decisions Made
- Followed the plan's literal JSX blocks verbatim for both files, including the exact locked copy strings from UI-SPEC's Copywriting Contract
- Kept `.header h1` text as "Fantasy Movie League" (not renamed to the mockup's fictional "Movie League") since only typography changes were specified, not new title copy
- Omitted the mockup's top nav bar and SAVE LINEUP CTA — no routing library exists in this app and no lineup-editing UI exists, so rendering either would create dead links/non-functional buttons

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing frontend dependencies**
- **Found during:** Task 2 (App.jsx build verification)
- **Issue:** `cd frontend && npm run build` failed with `sh: 1: vite: not found` — the worktree's `frontend/node_modules` directory did not exist (dependencies were never installed in this worktree checkout)
- **Fix:** Ran `npm install` in `frontend/` to install the existing `package.json`/`package-lock.json` dependency set (no dependency versions changed, `node_modules` is gitignored so nothing new was staged)
- **Files modified:** None tracked (node_modules is gitignored per `frontend/.gitignore`)
- **Verification:** `npm run build` subsequently succeeded (`vite build` produced `dist/` with 36 modules transformed)
- **Committed in:** N/A (no trackable file changes — node_modules is gitignored)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to run the plan's own build verification step; no code or dependency version changes, no scope creep.

## Issues Encountered
None beyond the dependency-install blocker documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `App.jsx` now renders the two-column shell and wires `ThisWeekSidebar` — Plans 01-03 (Leaderboard/PlayerCard) and 01-04 (MovieCard) can render inside `.app-main` without any further App.jsx changes needed
- Build passes end-to-end with the new styles.css (from 01-01) and the new App.jsx/ThisWeekSidebar.jsx; the roster/movie-card visuals will still look unstyled/broken until 01-03 and 01-04 land — expected, not a regression, per those plans' own scope
- No blockers for downstream plans or for the wave-2 merge

## Known Stubs

None. `ThisWeekSidebar` renders hardcoded content by design (per UI-SPEC's Illustrative Widgets section — a permanent, intentional static widget, not a placeholder awaiting future wiring) and is clearly labeled "Illustrative — not live data" so it cannot be mistaken for live data.

---
*Phase: 01-ui-redesign*
*Completed: 2026-08-18*

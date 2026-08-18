# Requirements: Fantasy Movie League

**Defined:** 2026-08-17
**Core Value:** Players can see accurate, current rankings and per-movie score breakdowns for their league.

## v1 Requirements

Requirements for the UI redesign phase.

### UI Redesign

- [ ] **UI-01**: Team/roster view (`Leaderboard`/`PlayerCard`/`OwnerDetail`) matches the new "Movie League" mockup layout — slot table with status pill, pts, proj, owned%
- [ ] **UI-02**: Movie detail view (`MovieCard` expanded state) matches the new mockup layout — hero header, points ledger with progress bars, campaign tracker timeline, ownership/similar sidebar
- [x] **UI-03**: Design tokens (color palette, type scale, spacing scale, status-pill colors) extracted from mockups and applied consistently across `styles.css` and all components
- [ ] **UI-04**: Existing functionality (data fetch, expand/collapse score breakdown, TMDB enrich trigger) still works after the redesign

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Backend

- **BACK-01**: Automatic scoring formula (`compute_movie_scores`) instead of manual entry
- **BACK-02**: OMDb integration for RT critic score
- **BACK-03**: Bulk TMDB enrich endpoint

## Out of Scope

| Feature | Reason |
|---------|--------|
| New backend endpoints or data model changes | This phase is UI-only; API contract stays as-is |
| Component library / CSS framework adoption | Keep existing plain-CSS approach, reskin in place |
| RT/Letterboxd live scraping | No public API, against ToS — manual entry stays |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UI-01 | Phase 1 | Pending |
| UI-02 | Phase 1 | Pending |
| UI-03 | Phase 1 | Complete |
| UI-04 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 4 total
- Mapped to phases: 4
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-17*
*Last updated: 2026-08-17 after manual scaffold creation for UI redesign phase*

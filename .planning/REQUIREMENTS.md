# Requirements: Fantasy Movie League

**Defined:** 2026-08-17
**Core Value:** Players can see accurate, current rankings and per-movie score breakdowns for their league.

## v1 Requirements

Requirements for the UI redesign phase.

### UI Redesign

- [x] **UI-01**: Team/roster view (`Leaderboard`/`PlayerCard`/`OwnerDetail`) matches the new "Movie League" mockup layout — slot table with status pill, pts, proj, owned%
- [x] **UI-02**: Movie detail view (`MovieCard` expanded state) matches the new mockup layout — hero header, points ledger with progress bars, campaign tracker timeline, ownership/similar sidebar
- [x] **UI-03**: Design tokens (color palette, type scale, spacing scale, status-pill colors) extracted from mockups and applied consistently across `styles.css` and all components
- [x] **UI-04**: Existing functionality (data fetch, expand/collapse score breakdown, TMDB enrich trigger) still works after the redesign

### Scoring

- [x] **SCORE-01**: `compute_movie_scores()` derives rating_score, financial_score, penalties, watch_points and total from the enrichment inputs, using the commissioner's tier tables
- [x] **SCORE-02**: Scores recompute automatically on enrich, bulk enrich, and manual PUT, so standings reflect live data
- [x] **SCORE-03**: Formula validated against every hand-scored row before adoption (rating 16/16, penalties 30/30, watch points 30/30)

### Live API Enrichment

- [x] **API-01**: OMDb service module fetches real IMDb rating and RT critic score, looked up by IMDb ID (via TMDB) rather than fuzzy title match
- [x] **API-02**: Persistent JSON file cache with tiered TTL and negative caching, so repeat enrichment does not re-hit the APIs
- [x] **API-03**: Per-field provenance (`manual` vs `fetched`) with a no-clobber rule — automatic enrichment never overwrites a hand-entered value unless explicitly forced
- [x] **API-04**: Bulk enrich endpoint, manually triggered, with sequential pacing and a per-run call cap so the OMDb daily quota cannot be exhausted
- [x] **API-05**: Both API keys documented in `.env.example` and README, never logged

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Backend

- ~~**BACK-01**: Automatic scoring formula~~ — delivered in Phase 3 as `SCORE-01`
- **BACK-02**: Scheduled/background refresh of stale cache entries (current scope is manual trigger only)
- **BACK-03**: `rt_aud` and `letterboxd` automation — no free API exists for either; stays manual entry

## Out of Scope

| Feature | Reason |
|---------|--------|
| New backend endpoints or data model changes | This phase is UI-only; API contract stays as-is |
| Component library / CSS framework adoption | Keep existing plain-CSS approach, reskin in place |
| RT/Letterboxd live scraping | No public API, against ToS — manual entry stays |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UI-01 | Phase 1 | Complete |
| UI-02 | Phase 1 | Complete |
| UI-03 | Phase 1 | Complete |
| UI-04 | Phase 1 | Complete |
| API-01 | Phase 2 | Complete |
| API-02 | Phase 2 | Complete |
| API-03 | Phase 2 | Complete |
| API-04 | Phase 2 | Complete |
| API-05 | Phase 2 | Complete |
| SCORE-01 | Phase 3 | Complete |
| SCORE-02 | Phase 3 | Complete |
| SCORE-03 | Phase 3 | Complete |

**Coverage:**
- v1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-17*
*Last updated: 2026-08-17 after manual scaffold creation for UI redesign phase*

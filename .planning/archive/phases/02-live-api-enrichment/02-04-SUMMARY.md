---
phase: 02-live-api-enrichment
plan: 04
subsystem: api
tags: [enrichment, caching, provenance, roi, rate-limiting, pytest-asyncio, tdd]

# Dependency graph
requires:
  - phase: 02-live-api-enrichment
    provides: "provenance.can_write()/apply_fetched()/mark_manual() no-clobber rule (02-02); cache.get()/put()/make_key()/ttl_for() persistent JSON cache (02-01); omdb.fetch_ratings() and tmdb.fetch_movie_financials() provider clients with injectable client param (02-03)"
provides:
  - "app.enrichment: CallBudget (hard per-run call ceiling), fetch_tmdb()/fetch_omdb() (cache-first, key-gated before budget/cache, distinguishes no-key/cache/fetched/miss/capped/error), compute_roi() (no-clobber roi = gross/budget), enrich_entry() (single-row merge, imdb sourced exclusively from OMDb), enrich_all() (sequential paced bulk runner with a shared CallBudget)"
  - "The concrete fix for RESEARCH section 4 (unconditional overwrite) and section 1 (vote_average-as-imdb bug), now enforced by executable code rather than just documented"
  - "37 new tests (166 total) proving the phase's two headline guarantees under test: a second run costs zero provider calls, and a call cap bounds a bulk run to at most N calls"
affects: [02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Key-before-budget-before-cache ordering: fetch_tmdb/fetch_omdb check os.environ for the provider key FIRST, before touching CallBudget or the cache, so a keyless run spends nothing and writes nothing -- adding a key later takes effect immediately rather than after a 24h negative-cache TTL"
    - "Spend-before-call budgeting: CallBudget.spend() runs before the provider awaits, so a provider exception still counts against the cap (a flaky provider cannot be used to bypass the budget by always erroring)"
    - "Sequential-only bulk processing: enrich_all loops with `await sleep(delay)` per row and never asyncio.gather's the rows, so pacing cannot be silently defeated by concurrency; enforced by a acceptance-criteria grep and a same test module read-and-assert on the source text"
    - "Every field write goes through provenance.apply_fetched() (never a bare `entry[field] = value`), so a refused overwrite is recorded in report['protected'] instead of silently vanishing"
    - "Report-not-raise error handling: provider exceptions are caught inside fetch_tmdb/fetch_omdb, redacted via redact_secrets(), and returned as an 'error: ...' outcome string rather than propagated, so one bad row cannot abort a bulk run"

key-files:
  created:
    - backend/app/enrichment.py
    - backend/tests/test_enrichment.py
  modified: []

key-decisions:
  - "Fixed a self-contradiction in the plan's own verbatim enrich_all docstring: it contained the literal substring 'asyncio.gather' (in the phrase 'never with asyncio.gather'), which fails the plan's own acceptance criterion (grep -c \"asyncio.gather\" == 0) and its own explicitly-instructed test. Reworded to describe a 'fan-out that gathers every row's coroutine at once' without the banned literal substring -- no behavior change, purely documentation wording"
  - "Rewrote three of my own bulk-runner tests (generous-cap call count, second-run-zero-calls, force-refetch) after discovering they assumed the shared fake_providers fixture (constant imdb_id for every title) would yield 3 distinct OMDb calls across 3 rows. That assumption was wrong: the cache correctly dedupes by imdb_id, so 3 rows sharing one fake id legitimately cost 1 OMDb call, not 3 -- this is the engine working correctly, not a bug. Added fake_providers_distinct, a fixture that resolves a different imdb_id per title, so these tests genuinely exercise a 3-different-movies scenario as the behavior bullet intends"
  - "requirements-completed below copies the plan's frontmatter verbatim per executor instructions, but only API-01 and API-02 (already Complete from prior plans) were passed to `requirements mark-complete`. API-03 and API-04 are NOT marked complete in REQUIREMENTS.md by this plan: Plan 02-05's own frontmatter also lists API-03 and API-04 as its requirements, meaning the roadmap's own structure treats both as spanning two plans (02-04 delivers the no-clobber engine and the paced/capped runner; 02-05 delivers the PUT endpoint's mark_manual stamping and the actual POST /api/enrich-all HTTP surface). Marking either complete from 02-04 alone would make REQUIREMENTS.md claim an endpoint exists before it does. This mirrors the precedent already set in 02-03-SUMMARY.md for the API-05 gap."

requirements-completed: [API-01, API-02, API-03, API-04]

# Metrics
duration: 9min
completed: 2026-08-19
---

# Phase 02 Plan 04: Enrichment Engine Summary

**Cache-first, budget-capped enrichment engine (`app/enrichment.py`) that merges TMDB financials and OMDb ratings into a row exclusively through `provenance.apply_fetched`, derives `roi` under the same no-clobber rule, and runs bulk enrichment strictly sequentially with a shared per-run call cap -- proven by 37 new tests with zero network and zero real API keys.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-19T15:17:00Z
- **Completed:** 2026-08-19T15:26:00Z
- **Tasks:** 2 (both TDD: RED then GREEN)
- **Files modified:** 2 (both created)

## Accomplishments
- Built `CallBudget`, a hard ceiling on outbound provider calls per run -- the concrete mechanism behind ROADMAP success criterion 4 (OMDb's 1,000/day free quota cannot be exhausted by accident)
- Built `fetch_tmdb`/`fetch_omdb`: cache-first lookups that check for an API key *before* touching the budget or the cache (so a keyless run never poisons the cache with a 24h negative entry), spend the budget before the provider call (so a provider error still counts against the cap), and never write a cache entry on error
- Built `compute_roi`, superseding `main.py`'s unconditional `_compute_roi`: derives `roi = round(gross/budget, 3)` under the exact same no-clobber rule (`provenance.can_write`) as every other enrichable field
- Built `enrich_entry`: merges TMDB financials and OMDb ratings into a row entirely through `provenance.apply_fetched` (no bare field assignment anywhere), sources `imdb` exclusively from OMDb's `imdbRating` (TMDB's `vote_average` is read but never written to `imdb` -- the accuracy bug from RESEARCH section 1 / HANDOFF.md line 43), skips the OMDb call when TMDB returns no `imdb_id`, and reports `updated`/`protected`/`errors` per field so a refused overwrite is visible rather than silent
- Built `enrich_all`: loops rows strictly sequentially (never `asyncio.gather`), awaits an injectable `sleep` once per row, shares one `CallBudget` across the whole run so later rows report `capped` once it's spent, mutates rows in place for the caller to persist, and survives a single row's provider error without aborting the run
- Proved the phase's two headline guarantees under test: `test_second_run_costs_zero_api_calls`/`test_enrich_all_second_run_costs_zero_api_calls` (repeat run makes zero outbound calls) and `test_cap_stops_the_run_from_burning_quota` (a cap of N yields at most N provider calls)
- Full backend suite: 166 passed (129 baseline + 37 new), 0 failures, no network, no real API keys

## Task Commits

Each task followed the RED -> GREEN TDD cycle, committed atomically:

1. **Task 1: Single-entry enrichment -- cached fetches, no-clobber merge, ROI**
   - `53bef54` (test) -- failing tests: CallBudget, fetch_tmdb/fetch_omdb (cold cache, force, no-match negative cache, no-key, capped, provider error), compute_roi, enrich_entry (fills fields, no-clobber, unknown-overwrite with legacy_value, no-imdb-id skip, invariant fields, redacted errors), plus the three verbatim regression tests
   - `b4c76d0` (feat) -- `enrichment.py` implementation (CallBudget, fetch_tmdb, fetch_omdb, compute_roi, enrich_entry); 28/28 new tests pass, full suite 157 passed
2. **Task 2: Bulk runner -- sequential pacing and an enforced per-run cap**
   - `cad8d44` (test) -- failing tests: enrich_all processes every row, second-run-zero-calls, force-refetch, mutates in place, summary totals, per-row error doesn't abort the run, plus the two verbatim regression tests (cap stops the run, rows paced sequentially) and a source-scan asserting `asyncio.gather` never appears
   - `044961d` (feat) -- `enrich_all` appended to `enrichment.py`; fixed the plan's own `asyncio.gather` docstring self-contradiction and three of my own bulk-test fixture assumptions (see Deviations); 37/37 new tests pass, full suite 166 passed

**Plan metadata:** _pending -- committed immediately after this file_

_Note: no REFACTOR commit was needed for either task -- both GREEN commits already matched the acceptance criteria once the fixes described in Deviations were folded in._

## Files Created/Modified
- `backend/app/enrichment.py` (219 lines) - `CallBudget`, `fetch_tmdb`, `fetch_omdb`, `compute_roi`, `enrich_entry`, `enrich_all`, `DEFAULT_MAX_CALLS`/`HARD_MAX_CALLS`/`MAX_CALLS_PER_ENTRY`/`PACING_DELAY_SECONDS`, outcome constants, and the private `_error()` redaction helper
- `backend/tests/test_enrichment.py` (639 lines, 37 tests) - Full behavior-bullet coverage for both tasks: `fake_providers`/`fake_providers_distinct` fixtures, CallBudget, fetch_tmdb/fetch_omdb (every outcome path), compute_roi, enrich_entry, enrich_all, and the five verbatim PLAN.md regression tests (zero-call repeat run, vote_average/imdb isolation, keyless-run cache safety, cap enforcement, sequential pacing)

## Decisions Made
- Implemented `enrichment.py`'s Task 1 code (CallBudget, fetch_tmdb, fetch_omdb, compute_roi, enrich_entry) exactly as given verbatim in the plan's `<action>` block -- it was already engineered to satisfy its own grep-based acceptance criteria exactly (verified: every count matched on the first run)
- Implemented `enrich_all` verbatim as given, except for the docstring wording fix described below
- Did not add a `max_calls` clamp inside `enrich_all` itself, per the plan's explicit instruction -- the hostile-input clamp against a `?max_calls=` query parameter belongs at the HTTP boundary in Plan 02-05, using the `HARD_MAX_CALLS` constant already defined here
- Did not touch `backend/app/main.py` or `backend/data/league_data.json`, per the plan's scope boundary -- `main.py`'s `_compute_roi` and `enrich_movie` are superseded logically but left in place for Plan 02-05 to rewire

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan text] `enrich_all`'s own docstring contains the literal substring its own acceptance criterion forbids**
- **Found during:** Task 2 GREEN, running `grep -c "asyncio.gather" backend/app/enrichment.py` (the plan's own Task 2 acceptance criterion) and the plan's own explicitly-instructed test (`assert "asyncio.gather" not in source`)
- **Issue:** The plan's verbatim `<action>` code for `enrich_all`'s docstring reads: "Rows are processed strictly sequentially with a delay between them -- never with asyncio.gather." This sentence's own literal text contains the substring `asyncio.gather`, which both the plan's own acceptance criterion (`grep -c "asyncio.gather"` must equal 0) and the plan's own explicitly-instructed test (read the module source, assert the substring is absent) require to be absent. No verbatim copy of the given docstring can satisfy either check.
- **Fix:** Reworded the sentence to preserve the exact same meaning (rows are never processed via a concurrent fan-out) without using the literal banned substring: "concurrency (a fan-out that gathers every row's coroutine at once) is never used here." No change to any executable code, control flow, or public contract -- documentation wording only.
- **Files modified:** `backend/app/enrichment.py`
- **Verification:** `grep -c "asyncio.gather" backend/app/enrichment.py` now returns `0`; `test_enrichment_module_never_uses_asyncio_gather` passes
- **Committed in:** `044961d` (Task 2 GREEN commit)

**2. [Rule 1 - Bug in my own tests] Three bulk-runner tests assumed the shared single-payload fixture would produce per-row-distinct OMDb calls**
- **Found during:** Task 2 GREEN, running the newly-written tests against the newly-implemented `enrich_all`
- **Issue:** `test_enrich_all_processes_every_row_with_generous_cap`, `test_enrich_all_second_run_costs_zero_api_calls`, and `test_enrich_all_force_true_refetches_every_row` used the Task 1 `fake_providers` fixture (which always returns the identical `TMDB_PAYLOAD`, and therefore the identical `imdb_id`, regardless of title) across 3 differently-titled rows, then asserted 3 distinct OMDb calls. Because `fetch_omdb`'s cache key is `omdb:{imdb_id}` (by design -- OMDb is looked up by exact IMDb ID, never by title), all 3 rows resolved to the same cache key, so rows 2 and 3 correctly served from row 1's cache entry -- 1 OMDb call, not 3. This was a bug in my test's assumption, not in the implementation: the caching behavior is exactly what Plan 02-01/02-03's design intends.
- **Fix:** Added `fake_providers_distinct`, a fixture that derives a distinct fake `imdb_id` per title (`tt{index:07d}`), so a 3-row bulk test over 3 genuinely-different movies produces 3 distinct TMDB calls and 3 distinct OMDb calls, matching what the plan's behavior bullet ("enrich_all over 3 rows ... calls TMDB 3 times and OMDb 3 times") actually describes. The original `fake_providers` fixture is left unchanged and is still used everywhere a single movie (or intentional cache-collision) is the point of the test.
- **Files modified:** `backend/tests/test_enrichment.py`
- **Verification:** All 3 corrected tests pass; full suite 166 passed
- **Committed in:** `044961d` (Task 2 GREEN commit, folded into the same commit as the implementation since both were part of reaching GREEN)

---

**Total deviations:** 2 auto-fixed (1 plan-text self-contradiction discovered via the plan's own acceptance criteria, 1 bug in my own test assumptions discovered the same way). 0 required a user decision.
**Impact on plan:** Both fixes are confined to documentation wording and test fixtures -- no change to `enrich_entry`'s or `enrich_all`'s runtime behavior, public signatures, or the no-clobber/caching/budget contracts. No scope creep.

## Issues Encountered
None beyond the two deviations above, both resolved within the same GREEN cycle they were discovered in.

## User Setup Required
None - no external service configuration required. This plan is a pure library layer with no HTTP surface; every test is monkeypatched with sentinel key literals (`TMDBSENTINEL`, `OMDBSENTINEL`, and a few distinctive sentinel strings used specifically to prove redaction, e.g. `SUPERSECRETOMDBKEY`) and touches no network. Real `TMDB_API_KEY`/`OMDB_API_KEY` values are still only needed once Plan 02-05 wires this engine behind an HTTP endpoint.

## Next Phase Readiness
- `app.enrichment`'s full public surface (`CallBudget`, `fetch_tmdb`, `fetch_omdb`, `compute_roi`, `enrich_entry`, `enrich_all`, `DEFAULT_MAX_CALLS`, `HARD_MAX_CALLS`, `MAX_CALLS_PER_ENTRY`, `PACING_DELAY_SECONDS`) is ready for Plan 02-05's endpoints to call directly
- `HARD_MAX_CALLS = 200` is defined and exported here specifically for Plan 02-05's HTTP-boundary clamp against a hostile `?max_calls=` query parameter (`enrich_all` itself trusts its caller and applies no clamp, per the plan's explicit instruction)
- `backend/.venv/bin/python -m pytest backend/tests -q` is green: 166 passed
- Requirement tracking: API-01 and API-02 confirmed complete (unchanged from prior plans). API-03 and API-04 are **not** marked complete in `REQUIREMENTS.md` by this plan, even though this plan's frontmatter lists both -- Plan 02-05's own frontmatter also claims both, and the literal requirement text for API-04 ("bulk enrich **endpoint**") and the manual-marking side of API-03 (the `PUT` endpoint stamping `mark_manual`) are 02-05's scope, not 02-04's. Flagging for the orchestrator/user to confirm both are marked complete only after 02-05 lands, consistent with the same judgment call already documented in `02-03-SUMMARY.md` for API-05.
- No blockers for Plan 02-05 (rewire `/enrich`, add provenance-stamping `PUT`, add `POST /api/enrich-all`) or Plan 02-06 (`.env.example`/README secret-hygiene docs)

---
*Phase: 02-live-api-enrichment*
*Completed: 2026-08-19*

## Self-Check: PASSED

**Files verified present on disk:**
- FOUND: backend/app/enrichment.py
- FOUND: backend/tests/test_enrichment.py
- FOUND: .planning/phases/02-live-api-enrichment/02-04-SUMMARY.md

**Commits verified in git log:**
- FOUND: 53bef54 (Task 1 RED)
- FOUND: b4c76d0 (Task 1 GREEN)
- FOUND: cad8d44 (Task 2 RED)
- FOUND: 044961d (Task 2 GREEN)

**Re-ran plan-level verification:**
1. `backend/.venv/bin/python -m pytest backend/tests -q` -> 166 passed, exit 0. PASS
2. Zero-call repeat run: `test_second_run_costs_zero_api_calls` and `test_enrich_all_second_run_costs_zero_api_calls` both pass. PASS
3. Cap enforcement: `test_cap_stops_the_run_from_burning_quota` passes; inline acceptance script (`max_calls=2` -> exactly 2 provider calls, `cap_reached is True`, all 3 rows still reported) prints `ok`. PASS
4. `grep -n "asyncio.gather" backend/app/enrichment.py` returns nothing (count 0, after the docstring wording fix documented in Deviations). PASS
5. `grep -rn "def compute_movie_scores" backend/app/` and `grep -rEn '\["(rating_score|financial_score|penalties|watch_points|total)"\] *=' backend/app/` both return nothing. PASS
6. No test sets a real key or opens a socket -- every provider function is monkeypatched directly (`monkeypatch.setattr(tmdb, ...)` / `monkeypatch.setattr(omdb, ...)`), and every env value used is a sentinel literal (`TMDBSENTINEL`, `OMDBSENTINEL`, plus a few distinctive strings used only to prove redaction). PASS

**Re-ran all Task 1 and Task 2 acceptance-criteria greps and inline Python scripts:** all pass, including every exact grep count in both tasks' `<acceptance_criteria>` blocks and both inline Python verification scripts (`CallBudget`/`compute_roi` behavior; `enrich_all` cap/pacing/mutation behavior).

**Re-ran all `must_haves.truths` (9 total):** all 9 independently confirmed true via the test suite (see Accomplishments and Task Commits above for the specific tests proving each one).

**Re-ran all `must_haves.artifacts` and `key_links`:** `backend/app/enrichment.py` exports all ten listed names (`CallBudget`, `fetch_tmdb`, `fetch_omdb`, `compute_roi`, `enrich_entry`, `enrich_all`, `DEFAULT_MAX_CALLS`, `HARD_MAX_CALLS`, `MAX_CALLS_PER_ENTRY`, `PACING_DELAY_SECONDS`) confirmed via direct `hasattr` check; `backend/tests/test_enrichment.py` is 639 lines (well above the 120 min_lines); all three `key_links` regex patterns (`provenance\.apply_fetched`, `cache\.put\(key, payload, cache\.ttl_for`, `omdb\.fetch_ratings`) match exactly once each.

**Scope boundary confirmed:** `git diff --stat f4631f9..HEAD` shows only `backend/app/enrichment.py` and `backend/tests/test_enrichment.py` changed -- `backend/app/main.py` and `backend/data/league_data.json` were not touched, per the plan's explicit scope boundary.

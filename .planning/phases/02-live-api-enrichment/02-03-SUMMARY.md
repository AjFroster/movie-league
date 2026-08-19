---
phase: 02-live-api-enrichment
plan: 03
subsystem: api
tags: [omdb, tmdb, httpx, provider-integration, secret-redaction, pytest-asyncio]

# Dependency graph
requires:
  - phase: 02-live-api-enrichment
    provides: "redact_secrets()/ProviderError secret-redaction boundary and the pytest+httpx.MockTransport test harness (Plan 02-01)"
provides:
  - "OMDb ratings client (backend/app/services/omdb.py): fetch_ratings() by IMDb ID + pure parse_omdb_payload() for network-free testing"
  - "TMDB client extended with release_date (feeds cache TTL tiering), a regex-validated imdb_id (feeds the OMDb lookup), hardened numeric parsing, and an injectable client for tests"
  - "Accuracy-bug fix path: omdb.py now supplies the real IMDb rating so a future enrichment layer no longer has to write TMDB's vote_average into the `imdb` field"
  - "critic_scores_stub.py docstring corrected: rt_crit has a real source now (omdb.py); only rt_aud/Letterboxd remain genuinely unavailable"
affects: [02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Own-it-or-borrow-it client injection: fetch_ratings()/fetch_movie_financials() accept an optional httpx.AsyncClient; production omits it (function owns + closes it), tests inject a MockTransport-backed client (function borrows, caller closes)"
    - "Provider JSON validation boundary: every third-party field is isinstance()-checked (bool explicitly rejected before it can coerce to 1.0), NaN-checked, and range-checked before it can reach league_data.json"
    - "Lookup-by-ID-not-by-title: OMDb is queried by TMDB's exact imdb_id via a params dict (never string interpolation), designing out fuzzy-title mismatch rather than mitigating it after the fact"
    - "Redact-at-the-boundary asymmetry, by design: omdb.py raises key-bearing httpx errors as ProviderError(str(e), provider='omdb') from None (OMDb has no header auth, so its key rides in the URL); tmdb.py deliberately keeps raising raw httpx.HTTPStatusError since its key is in a Bearer header (never in a URL) and main.py's handler is not rewired to catch ProviderError until Plan 02-05"

key-files:
  created:
    - backend/app/services/omdb.py
    - backend/tests/test_omdb.py
    - backend/tests/test_tmdb.py
  modified:
    - backend/app/services/tmdb.py
    - backend/app/services/critic_scores_stub.py

key-decisions:
  - "Rewrote tmdb._vote_average to round via Decimal(str(value)).quantize(Decimal('0.1'), ROUND_HALF_UP) instead of the plan's literal round(value, 1): plain round(7.35, 1) evaluates to 7.3 in Python (7.35 is not exactly representable in binary floating point), which contradicts the plan's own acceptance criterion asserting tmdb._vote_average(7.35) == 7.4. The Decimal-based fix makes the plan's own stated criterion pass exactly, with no other behavior change."
  - "Kept the plan's verbatim omdb.py docstring content, including the 'apikey.aspx' URL fragment (the OMDb key-signup page), even though the plan's own verification-section grep (excluding lines containing the literal '\"\"\"' marker) flags that one docstring line as a false positive -- the filter only strips the docstring's opening/closing quote lines, not prose nested between them. Not a redaction gap: the string never touches request construction."
  - "This worktree had no backend/.venv/ (git worktrees do not share gitignored directories with the main repo checkout). Created a fresh venv with `uv venv --python 3.12 backend/.venv` and installed the exact pinned versions from requirements.txt/requirements-dev.txt to match the main repo's environment -- no code impact, pure local tooling setup."

requirements-completed: [API-01, API-05]

# Metrics
duration: 7min
completed: 2026-08-19
---

# Phase 02 Plan 03: OMDb Ratings Client and TMDB Hardening Summary

**New OMDb client fetches the real IMDb rating and Rotten Tomatoes critic score by exact IMDb ID with redact-at-construction error handling, and the existing TMDB client now returns `release_date` plus a validated `imdb_id` through range-checked parsers.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-19T15:04:03Z
- **Completed:** 2026-08-19T15:11:00Z
- **Tasks:** 2
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- Built `backend/app/services/omdb.py`: `fetch_ratings(imdb_id)` looks up OMDb by exact IMDb ID (`params={"i": imdb_id, "apikey": key}`, never a string-built URL or a `?t=` title search), and the pure `parse_omdb_payload()` type- and range-validates every field (`imdb` 0-10, `rt_crit` 0-100, explicit `bool` rejection so `True` can't coerce to `1.0`, NaN rejection, tolerant `"89%"`/`" 89 % "`/`89` percent parsing) so a malformed OMDb response can never write garbage into `league_data.json`
- Closed the key-leak path that motivated this plan: every OMDb HTTP/JSON failure raises `ProviderError(str(e), provider="omdb") from None` -- redacted at construction, and `from None` keeps the original exception (which embeds the raw `?apikey=...` URL) out of the printed traceback. Verified directly: `excinfo.value.__cause__ is None` and the raw key string never appears in `str(exc)`
- Extended `backend/app/services/tmdb.py` with `release_date` (feeds `cache.ttl_for`'s TTL tiering), a regex-validated `imdb_id` (the join key `omdb.py` needs), and range-checked `_millions`/`_vote_average` parsers -- while explicitly preserving the existing Bearer-header auth and `httpx.HTTPStatusError` exception type that `main.py` still depends on until Plan 02-05
- Added dependency-injectable `client: httpx.AsyncClient | None = None` to both `fetch_ratings` and `fetch_movie_financials`, so both providers' full HTTP round-trips are covered by `httpx.MockTransport` with zero network and zero API keys
- Corrected `critic_scores_stub.py`'s docstring, which previously claimed Rotten Tomatoes has no public API at all -- now states that `rt_crit` is fetched for real by `omdb.py`, and only the RT *audience* score and Letterboxd remain genuinely unavailable

## Task Commits

Each task followed the RED -> GREEN TDD cycle, committed atomically:

1. **Task 1: OMDb client -- real IMDb rating + RT critic score, by IMDb ID**
   - `37862f7` (test) -- failing test suite: full parse matrix, key-gate, ID validation, MockTransport HTTP behavior, and the two verbatim security regression tests
   - `b113e30` (feat) -- `omdb.py` implementation; 32/32 new tests pass
2. **Task 2: TMDB -- release_date, hardened numeric parsing, client injection**
   - `da09cef` (test) -- failing test suite: release_date/imdb_id/budget/vote_average validation, MockTransport round-trip, httpx.HTTPStatusError contract, direct parser unit tests
   - `e397602` (feat) -- `tmdb.py` + `critic_scores_stub.py` changes, including the Rule 1 rounding fix; 49/49 new tests pass

**Plan metadata:** _pending -- committed immediately after this file_

_Note: both tasks were `tdd="true"`; no REFACTOR commit was needed since the one behavioral fix (Decimal-based rounding) was folded into the GREEN commit before it landed, not cleaned up afterward._

## Files Created/Modified
- `backend/app/services/omdb.py` - New OMDb client: `fetch_ratings`, `parse_omdb_payload`, `OMDB_BASE`, `IMDB_ID_RE`, and the private `_parse_rating_10`/`_parse_percent`/`_extract_rt_crit` validators
- `backend/tests/test_omdb.py` - 32 tests: full parse matrix + MockTransport-driven `fetch_ratings` coverage, including the plan's two verbatim security regression tests
- `backend/app/services/tmdb.py` - Added `release_date`, validated `imdb_id`, `_millions`/`_vote_average`/`_imdb_id`/`_release_date` parsers, injectable `client` param; preserved Bearer auth and `httpx.HTTPStatusError`
- `backend/tests/test_tmdb.py` - 49 tests: MockTransport round-trip, per-field validation, direct parser unit coverage, and a cross-module check that `release_date` feeds `cache.ttl_for`'s tiering
- `backend/app/services/critic_scores_stub.py` - Docstring corrected to state `rt_crit` now has a real source (`omdb.py`); only `rt_aud`/Letterboxd remain manual

## Decisions Made
- Implemented `omdb.py` exactly as specified in the plan's `<action>` block (verbatim), since it is a load-bearing interface for Plan 02-04's enrichment layer and Plan 02-05's error-handling rewire
- Fixed `tmdb._vote_average`'s rounding to use `Decimal`-based round-half-up instead of the plan's literal `round(value, 1)` -- see Deviations below; this is the only place implementation diverged from the plan's literal code
- Used a single `MockTransport` handler branching on `request.url.path` for the TMDB search+details round-trip, as the plan's action text directed
- Did not touch `cache.py`, `enrichment.py`, `.env.example`, or `main.py` -- caching is applied one layer up in Plan 02-04 per the plan's own interface note, and this plan's `files_modified` list does not include those files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `tmdb._vote_average`'s plain `round(value, 1)` contradicts the plan's own acceptance criterion for the value 7.35**
- **Found during:** Task 2, running the plan's literal acceptance-criteria script
- **Issue:** The plan's `<action>` code specifies `return round(value, 1)`. Python's `round(7.35, 1)` evaluates to `7.3`, not `7.4`, because `7.35` is not exactly representable in binary floating point (it is stored as `~7.349999999999996...`) and `round()` operates on that binary value. The plan's own acceptance criterion is `assert tmdb._vote_average(7.35) == 7.4 and ...` -- so the plan's literal implementation and its literal acceptance criterion are mutually contradictory; no verbatim implementation of `round(value, 1)` can satisfy both at once.
- **Fix:** Replaced `round(value, 1)` with `float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))`. Converting through `str(value)` first recovers the intended decimal digits (`"7.35"`) before rounding, avoiding the binary-representation trap. Added `from decimal import ROUND_HALF_UP, Decimal` to imports. No other behavior changed -- verified `_millions`, `_imdb_id`, `_release_date`, and every other `_vote_average` test case (including the boundary values `0`, `11`) still pass unchanged.
- **Files modified:** `backend/app/services/tmdb.py`
- **Verification:** `tmdb._vote_average(7.35) == 7.4` now holds; full suite (108 tests) and both of the plan's inline acceptance scripts pass
- **Committed in:** `e397602` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 -- a genuine contradiction between the plan's own literal code and its own literal acceptance criterion, not an implementation bug of my own making)
**Impact on plan:** One-line, behavior-preserving fix confined to `_vote_average`'s internal rounding. No public contract changed -- the function's signature, range checks, and every other test case are unaffected. `_millions` uses the same `round()` pattern but has no test/acceptance criterion exercising a similar half-rounding edge case, so it was left unchanged per the deviation-rules scope boundary (fix only what is demonstrated broken).

## Issues Encountered
- **No `.venv` in this worktree.** Git worktrees do not share gitignored directories (like `backend/.venv/`) with the main repository checkout, so this worktree started with no Python environment at all. Resolved by running `uv venv --python 3.12 backend/.venv` and installing the exact pinned versions from `backend/requirements.txt` and `backend/requirements-dev.txt` (matching the main repo's installed versions exactly: fastapi==0.115.0, httpx==0.27.2, pytest==9.1.1, pytest-asyncio==1.4.0, etc.). No code impact; this is local tooling setup, not a plan deviation.
- **Requirement-mapping inconsistency worth flagging (not fixed by this plan):** This plan's frontmatter lists `requirements: [API-01, API-05]`, and `API-05` is defined in `.planning/REQUIREMENTS.md` as "Both API keys documented in `.env.example` and README, never logged." Neither this plan's `files_modified` list nor its actual task output touches `.env.example` or `README.md` -- the same gap exists in `02-01-SUMMARY.md`, which also claims `API-05` in its frontmatter without touching those files. Per executor instructions this Summary's `requirements-completed` field copies the plan's frontmatter verbatim (`[API-01, API-05]`), but the orchestrator/user should verify `API-05` before marking it complete in `REQUIREMENTS.md` -- as of this plan, `.env.example`/README documentation for `OMDB_API_KEY`/`TMDB_API_KEY` still appears undone.

## User Setup Required
None for this plan's own tasks -- everything is tested via `httpx.MockTransport` with no real API keys. `OMDB_API_KEY` / `TMDB_API_KEY` still need to be added to `backend/.env` by the user before live enrichment can run against real data, but wiring that into an endpoint is Plan 02-04's scope, and documenting the setup in `.env.example`/README is the `API-05` gap noted above.

## Next Phase Readiness
- `backend/.venv/bin/python -m pytest backend/tests -q` is green: 108 passed (27 from Plan 02-01 + 32 new OMDb tests + 49 new TMDB tests)
- `omdb.fetch_ratings()` and `tmdb.fetch_movie_financials()` are ready for Plan 02-04's enrichment layer to call and wrap with `cache.py`'s `get`/`put` -- both accept an injectable `client` for that layer's own tests, and both return `None` uniformly for "no key" or "no match" (the negative-cacheable case)
- `tmdb._release_date()`'s output is already verified to feed `cache.ttl_for()`'s tiering correctly (undated/unreleased -> `TTL_NEGATIVE`, released >1yr -> `TTL_RELEASED`)
- `omdb.py` raises `ProviderError` (redacted, `from None`) on failure; `tmdb.py` still raises raw `httpx.HTTPStatusError` by design -- Plan 02-04's enrichment layer should catch `(httpx.HTTPError, ProviderError)` together, exactly as the plan's interface note specifies
- No blockers for Plan 02-04. Flag for the orchestrator/user: verify the `API-05` requirement-mapping gap noted above before marking it complete.

---
*Phase: 02-live-api-enrichment*
*Completed: 2026-08-19*

## Self-Check: PASSED

**Files verified present on disk:**
- FOUND: backend/app/services/omdb.py
- FOUND: backend/tests/test_omdb.py
- FOUND: backend/tests/test_tmdb.py
- FOUND: backend/app/services/tmdb.py
- FOUND: backend/app/services/critic_scores_stub.py
- FOUND: .planning/phases/02-live-api-enrichment/02-03-SUMMARY.md

**Commits verified in git log:**
- FOUND: 37862f7 (Task 1 RED)
- FOUND: b113e30 (Task 1 GREEN)
- FOUND: da09cef (Task 2 RED)
- FOUND: e397602 (Task 2 GREEN)

**Re-ran plan-level verification:** `backend/.venv/bin/python -m pytest backend/tests -q` -> 108 passed, exit 0.
**Re-ran all Task 1 and Task 2 acceptance-criteria greps and inline Python scripts:** all pass, including the Rule-1-fixed `tmdb._vote_average(7.35) == 7.4`.
**Re-ran the plan's overall `<verification>` section:** suite green; `MockTransport` present in both new test files with no bare untransported `httpx.AsyncClient()`; `no_real_api_keys` autouse fixture confirmed in `conftest.py`; the one `apikey` grep hit outside `params=`/`redaction.py` is the benign `apikey.aspx` docstring URL fragment in `omdb.py` (see Deviations).
**TDD gate sequence confirmed:** both tasks show `test(...)` before `feat(...)` in git log (RED before GREEN); no REFACTOR commit was needed.

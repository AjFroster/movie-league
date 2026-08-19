---
phase: 02-live-api-enrichment
plan: 06
subsystem: docs
tags: [documentation, secret-hygiene, pytest, static-analysis, tdd, security]

# Dependency graph
requires:
  - phase: 02-live-api-enrichment
    provides: "Final shipped endpoint contract from 02-05 (POST /api/movies/{owner}/{round}/enrich, PUT /api/movies/{owner}/{round}, POST /api/enrich-all) and redaction.redact_secrets/ProviderError (02-01) — this plan's guards assert against that shipped state and document that exact contract"
provides:
  - "backend/.env.example documents both TMDB_API_KEY and OMDB_API_KEY with strictly-enforced placeholder values (your_tmdb_key_here / your_omdb_key_here)"
  - "README.md 'Auto-fetching data' section rewritten against the real shipped endpoint contract: key acquisition, both endpoints with force/max_calls params, the field-source matrix, provenance semantics, cache TTLs, and an explicit 'enrichment does not change the standings' caveat"
  - "README.md 'Editing scores' amended to note a PUT stamps changed fields manual; new 'Running the tests' section documents the uv-only (no pip) test workflow"
  - "backend/tests/test_secret_hygiene.py: 7 static guards over backend/app/** enforcing no interpolated API keys, no print(), no raw exception detail in main.py, placeholder-only .env.example, gitignored secrets/cache, and no tracked .env — proven to actually catch a regression via an executed-and-reverted negative control"
  - "API-05 (the last open Phase 2 requirement) is now satisfied and marked complete"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static string-scan guards over backend/app/** as regression tests for security guarantees that would otherwise be invisible at a glance and trivially undone by a well-meaning edit (no interpolated apikey={, no print(), no bare detail=str(e))"
    - "A guard test earns trust only via a negative control: temporarily reintroduce the exact regression it exists to catch, confirm the suite goes red, then revert and confirm green again. Writing the assertion alone is not sufficient evidence it works."
    - "A static-analysis test that scans a glob must also assert the glob is non-empty (test_app_sources_exist_to_scan), or a future directory rename silently turns every other check in the file into a no-op pass"

key-files:
  created:
    - backend/tests/test_secret_hygiene.py
  modified:
    - backend/.env.example
    - README.md

key-decisions:
  - "Added a 'cap a bulk run at 20 calls' curl example to README's Trigger-enrichment section — the plan's own verbatim README content mentioned 'max_calls' only once, one short of its own acceptance criterion requiring >=2 occurrences. The addition is genuine documentation value (shows how to actually use the cap), not padding to satisfy a grep."
  - "Reworded test_secret_hygiene.py's assertion failure message so it no longer contains the literal substring 'detail=str(e)' it asserts is absent from main.py — the plan's own verbatim prose ('...detail=str(e) would return OMDB_API_KEY...') contained the exact string its own acceptance criterion (grep count == 1) forbade appearing twice. Same class of plan-text self-reference bug already fixed twice elsewhere in this phase (02-04's asyncio.gather docstring, 02-05's main.py comment)."
  - "Left README's pre-existing 'Running locally' section untouched (still shows 'pip install -r requirements.txt', which fails in this repo — there is no pip, only uv) even though it is stale in the same way this plan fixes for 'Running the tests'. Task 1's action explicitly scoped edits to three sections (Auto-fetching data, Editing scores, Running the tests) and this fourth section was not among them; a correct fix also needs to handle a fresh clone with no backend/.venv yet, which is bigger than a drive-by swap. Logged to deferred-items.md instead of fixed opportunistically."
  - "Performed the negative control for real rather than treating it as a documentation-only checkbox: reintroduced the exact OMDb-key-leak pattern into a live copy of main.py via sed, ran the guard suite and confirmed 1 failure (EXIT=1), then restored main.py from a scratchpad backup and confirmed byte-identical via md5sum plus a clean git diff. This is the only thing that proves the guard bites rather than merely passing vacuously."

patterns-established:
  - "Secret-handling guarantees in this codebase are enforced by static tests, not by convention or code review alone — any future change that reintroduces an interpolated key, a print(), or a bare exception detail will fail backend/tests/test_secret_hygiene.py immediately."

requirements-completed: [API-05]

# Metrics
duration: 7min
completed: 2026-08-19
---

# Phase 02 Plan 06: Documentation + Secret-Hygiene Guards Summary

**Documented both API keys and the shipped enrichment endpoints in `.env.example`/README (including the explicit "standings don't move" caveat), then added 7 static regression tests that make the phase's secret-handling guarantees enforceable — proven via an executed-and-reverted negative control that turned the suite red on a reintroduced OMDb key leak.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-19T19:44:35Z
- **Completed:** 2026-08-19T19:51:36Z
- **Tasks:** 2 (both `type="auto"`)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Replaced `backend/.env.example`'s single TMDB placeholder with both `TMDB_API_KEY` and `OMDB_API_KEY`, each carrying a strict, machine-checkable placeholder (`your_tmdb_key_here` / `your_omdb_key_here`) and a comment naming the free-tier source and exactly which fields it supplies
- Rewrote README's "Auto-fetching data" section end-to-end against the endpoint contract Plan 02-05 actually shipped: key acquisition table, `cp backend/.env.example backend/.env` setup, both endpoints (`/enrich` and `/api/enrich-all`) with their `force`/`max_calls` query params and a runnable example of each, the field-source matrix, the `manual`/`fetched`/`unknown` provenance semantics (including `legacy_value`), the tiered cache TTLs, and a dedicated "Enrichment does not change the standings" subsection naming `BACK-01` as the tracked follow-up
- Corrected the stale claim that "RT Critic/Audience and Letterboxd scores have no public API" — RT *critic* now has one (OMDb); only RT *audience* and Letterboxd remain manual, and the rewritten section says so precisely
- Amended "Editing scores" to note a `PUT` stamps changed fields `manual`; added a new "Running the tests" section documenting that this repo's venv has no `pip` and `uv` is required, matching the fact already independently documented in `backend/requirements-dev.txt`
- Added `backend/tests/test_secret_hygiene.py`: 7 static guards scanning `backend/app/**` for interpolated API keys, `print()` calls, and a raw `detail=str(e)` in `main.py` (must use `detail=redact_secrets(str(e))` at both call sites instead), plus guards on `.env.example` placeholder-only values, `.gitignore` still excluding `backend/.env`/`backend/data/api_cache.json`, and `backend/.env` never being tracked by git
- Ran the plan's literal negative control: reintroduced `detail=str(e)` into a live copy of `main.py` via `sed`, confirmed the guard suite goes red (`1 failed`, `EXIT=1`), then restored `main.py` from a scratchpad backup and confirmed it byte-identical via `md5sum` with a clean `git diff` afterward — proving the guard actually catches the regression it exists to catch
- Full backend suite: 196 passed (189 baseline + 7 new), 0 failures, no network calls, no real API keys, `backend/.env` never created

## Task Commits

1. **Task 1: Document both keys, the endpoints, and the standings caveat** - `aae5c92` (docs)
2. **Task 2: Static secret-hygiene guards** - `a6f2444` (test)

**Plan metadata:** _pending — committed immediately after this file_

_Note: Task 2 is marked `tdd="true"` in the plan but has no paired `<implementation>` block — the application code it guards (`main.py`) already shipped in Plan 02-05. Its "RED" proof is the negative control (temporarily reintroducing the regression and confirming failure) rather than a separate pre-implementation failing-test commit, since there was no new production code to write against. One commit for the guard file, consistent with the plan's own single-file `<files>` scope for this task._

## Files Created/Modified
- `backend/.env.example` (2 -> 10 lines) — documents both `TMDB_API_KEY` and `OMDB_API_KEY` with enforced placeholders and per-key provenance comments
- `README.md` (57 -> 139 lines) — "Auto-fetching data" rewritten in full, "Editing scores" amended, new "Running the tests" section added
- `backend/tests/test_secret_hygiene.py` (72 lines, 7 tests) — static regression guards for the phase's secret-handling guarantees
- `.planning/phases/02-live-api-enrichment/deferred-items.md` (new) — logs the out-of-scope "Running locally" pip-instruction staleness rather than fixing it opportunistically

## Decisions Made
See `key-decisions` in frontmatter for full rationale on all four judgment calls made this plan: the `max_calls` example addition, the assertion-message reword, leaving "Running locally" untouched, and actually executing the negative control rather than skipping it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan text] README's own verbatim "Auto-fetching data" content under-shoots its own acceptance criterion for `max_calls` occurrences**
- **Found during:** Task 1, running `grep -c "max_calls" README.md` (the plan's own acceptance criterion requiring `-ge 2`)
- **Issue:** The plan's verbatim replacement markdown for the "Auto-fetching data" section mentions `max_calls` exactly once (in the query-param table), one short of the `-ge 2` the plan's own acceptance criteria demand.
- **Fix:** Added a genuinely useful "Example — cap a bulk run at 20 calls" curl snippet (`curl -X POST http://localhost:8000/api/enrich-all?max_calls=20`) immediately after the query-param table, showing a reader how to actually combine the endpoint with the parameter rather than padding text to satisfy a grep.
- **Files modified:** `README.md`
- **Verification:** `grep -c "max_calls" README.md` now returns `2`; all other Task 1 acceptance criteria re-verified passing (15 total)
- **Committed in:** `aae5c92` (Task 1 commit)

**2. [Rule 1 - Bug in plan text] Test file's own assertion message contains the literal substring it asserts is absent**
- **Found during:** Task 2, running `grep -c "detail=str(e)" backend/tests/test_secret_hygiene.py` (the plan's own acceptance criterion requiring exactly `1`)
- **Issue:** The plan's verbatim `<action>` code for `test_main_never_returns_a_raw_exception_string`'s assertion message reads "...query parameter -- detail=str(e) would return OMDB_API_KEY in the response body" — explanatory prose about the leak being guarded against, but its own literal text contains the substring `detail=str(e)`, pushing the grep count to `2` against the plan's own acceptance criterion of exactly `1`. Same class of issue as 02-04's `asyncio.gather` docstring self-contradiction and 02-05's `main.py` comment, both already documented in this phase's STATE.md.
- **Fix:** Reworded to "...query parameter -- passing the raw exception through unredacted would leak OMDB_API_KEY into the response body" — identical meaning, no literal `detail=str(e)` substring.
- **Files modified:** `backend/tests/test_secret_hygiene.py`
- **Verification:** `grep -c "detail=str(e)" backend/tests/test_secret_hygiene.py` now returns `1`; the guard still fails correctly when the negative control reintroduces the real leak into `main.py` (re-verified after the reword)
- **Committed in:** `a6f2444` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1, both the same plan-text/acceptance-criteria self-reference class already documented three times earlier in this phase — 02-02's `migrated=0` literal, 02-04's `asyncio.gather` docstring, 02-05's `main.py` comment). 0 required a user decision.
**Impact on plan:** Both fixes are confined to documentation prose and a test's own assertion message — no change to any runtime behavior, the shipped endpoint contract, or the guard's actual detection logic. No scope creep.

## Issues Encountered
None beyond the two auto-fixed plan-text deviations above.

## User Setup Required
None — no external service configuration required. `backend/.env` was never created; no real API key was written anywhere. The negative control's `sed` mutation to `backend/app/main.py` was applied to the real file, confirmed to fail the guard suite, then restored from a `/tmp` scratchpad backup and verified byte-identical via `md5sum` before any commit — no trace of the mutation reached git.

## Next Phase Readiness
- API-05 is now satisfied: `backend/.env.example` documents both keys with enforced placeholders, and README covers key acquisition, both endpoints with their query params, the field-source matrix, provenance, caching, the uv-based test command, and the standings caveat.
- REQUIREMENTS.md: all five Phase 2 requirements (API-01 through API-05) are now complete — this was the last one. ROADMAP.md Phase 2 is fully delivered (6/6 plans).
- `backend/.venv/bin/python -m pytest backend/tests -q` is green: 196 passed, no network, no keys.
- One deferred, non-blocking item logged to `.planning/phases/02-live-api-enrichment/deferred-items.md`: README's "Running locally" section still instructs `pip install -r requirements.txt`, which fails in this repo (uv-only, no pip) — same staleness this plan fixed for the test-running instructions, but out of this plan's explicit task scope. Worth a small follow-up, not a blocker.
- No other blockers. Phase 2 (Live API Enrichment) is complete.

---
*Phase: 02-live-api-enrichment*
*Completed: 2026-08-19*

## Self-Check: PASSED

**Files verified present on disk:**
- FOUND: backend/.env.example
- FOUND: README.md
- FOUND: backend/tests/test_secret_hygiene.py

**Commits verified in git log:**
- FOUND: aae5c92 (Task 1)
- FOUND: a6f2444 (Task 2)

**Re-ran plan-level verification (all 5 items in the plan's `<verification>` section):**
1. `backend/.venv/bin/python -m pytest backend/tests -q` -> 196 passed, exit 0. PASS
2. Negative control: reintroducing `detail=str(e)` into `main.py` -> suite goes red (1 failed, EXIT=1); restoring from backup -> suite green again, `main.py` confirmed byte-identical via `md5sum` and a clean `git diff`. PASS
3. `git ls-files | grep -c "\.env$"` -> `0`. PASS
4. Read README's "Auto-fetching data" section end to end: every command shown (`cp backend/.env.example backend/.env`, both curl examples, the `max_calls=20` example) is runnable as written from the repo root; the "Enrichment does not change the standings" subsection heading is impossible to miss. PASS
5. `grep -rn "your_key_here" backend/` -> no matches (old ambiguous placeholder fully replaced). PASS

**Re-ran all Task 1 acceptance criteria (15 total):** all pass, including every exact-count and `-ge` grep.

**Re-ran all Task 2 acceptance criteria (9 total):** all pass, including `def test_` == 7, `APP_PY_FILES` >= 4 (actual 4), `detail=str(e)` == 1, the `git ls-files` grep == 1, the negative control producing `EXIT=1` and a fully restored file, and `git ls-files backend/.env` producing no output.

**Re-ran all `must_haves.truths` (7 total):** all 7 independently confirmed — both keys documented with placeholders, README explains key sourcing/free-tier limits/fields supplied, both endpoints documented with `force`/`max_calls`, the standings caveat is stated plainly, the uv-not-pip test instructions are present, the static guard against key-in-URL/print/raw-exception-detail exists and is proven to fire, and the static guard against a non-placeholder `.env.example` value or a tracked `backend/.env` exists.

**Re-ran all `must_haves.artifacts` and `key_links`:** `backend/.env.example` contains `OMDB_API_KEY`; `README.md` contains `/api/enrich-all`; `backend/tests/test_secret_hygiene.py` is 72 lines (above the 50 `min_lines`); the `README.md` -> `.env.example` link (pattern `\.env\.example`) matches via the `cp backend/.env.example backend/.env` line; the `test_secret_hygiene.py` -> `main.py` link (pattern `detail=redact_secrets`) matches via `text.count("detail=redact_secrets(str(e))")`.

**Scope boundary confirmed:** `git diff --stat f711397..HEAD` shows exactly `backend/.env.example`, `README.md`, `backend/tests/test_secret_hygiene.py`, and `.planning/phases/02-live-api-enrichment/deferred-items.md` changed by this plan's two commits — `backend/app/main.py` and `backend/data/league_data.json` were not modified in any committed state (the negative control's mutation to `main.py` was applied, tested, and reverted entirely within Task 2's working-tree steps, before that task's commit).

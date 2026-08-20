---
phase: 02-live-api-enrichment
plan: 02
subsystem: api
tags: [provenance, data-safety, migration, pydantic, no-clobber]

# Dependency graph
requires:
  - phase: 02-live-api-enrichment
    provides: "Plan 02-01's pytest+pytest-asyncio harness and sample_movie/tmp_league fixtures"
provides:
  - "app.provenance: MANUAL/FETCHED/UNKNOWN origins, can_write() no-clobber rule with force override, apply_fetched(), mark_manual(), ENRICHABLE_FIELDS"
  - "Movie.sources field so provenance survives a PUT round-trip through Pydantic"
  - "Migrated backend/data/league_data.json: all 30 rows carry a sources dict, 48 manual field-entries protected, 61 unknown field-entries correctable with legacy_value preserved"
  - "backend/scripts/migrate_provenance.py: reusable, idempotent, --dry-run-capable backfill pattern for future one-shot data migrations"
affects: [02-03, 02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No-clobber rule: can_write() defaults fail-closed for unrecorded-but-populated fields (protects pre-provenance data by default), force=True is the only override, and origin==unknown is deliberately writable (ambiguous legacy values are correctable, not frozen)"
    - "legacy_value preservation: set_source() carries forward an existing legacy_value across successive calls unless a new one is explicitly given, so correcting an unknown field never loses the pre-migration number"
    - "Evidence-based migration classification: field origin assigned by grepping the actual historical write path (main.py::enrich_movie), not by guessing which fields 'look' hand-entered"
    - "One-shot migration script pattern: shutil.copy2 backup before any write, .tmp + os.replace atomic write (mirrors app/storage.py), idempotent via a per-row already-migrated skip check"

key-files:
  created:
    - backend/app/provenance.py
    - backend/tests/test_provenance.py
    - backend/scripts/migrate_provenance.py
    - backend/tests/test_migration.py
  modified:
    - backend/app/models.py
    - backend/data/league_data.json

key-decisions:
  - "Implemented provenance.py and migrate_provenance.py exactly as specified in PLAN.md's <interfaces>/<action> blocks (verbatim), since the plan explicitly marked the field classification as evidence-derived and not to be re-derived"
  - "Task 2's acceptance criterion expecting the post-migration dry-run to print 'migrated=0 skipped=16' is mathematically impossible given the plan's own migrate() code (migrated+skipped always equals movies=30 by loop construction) and contradicts the plan's own first-run expectation (migrated=30 skipped=0) using the same skip predicate -- documented as a plan-text bug, verified true idempotency (byte-identical file, stable re-run output) as the substantive equivalent"

requirements-completed: [API-03]

# Metrics
duration: 12min
completed: 2026-08-19
---

# Phase 02 Plan 02: Per-Field Provenance and Evidence-Based Migration Summary

**Added a manual/fetched/unknown provenance system with a force-overridable no-clobber rule, then backfilled all 30 existing league_data.json rows using an evidence-derived classification (48 manual field-entries protected forever, 61 ambiguous field-entries left correctable with their pre-migration value preserved under legacy_value).**

## Performance

- **Duration:** 12 min
- **Started:** 2026-08-19T14:57:00Z
- **Completed:** 2026-08-19T15:08:25Z
- **Tasks:** 2
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments
- Built `app/provenance.py`: three origins (`manual`/`fetched`/`unknown`), a no-clobber rule that fails closed for unrecorded-but-populated fields, `force=True` as the sole override (including over `manual`), and `apply_fetched()`/`mark_manual()` helpers — this is the direct regression fix for RESEARCH section 4 (main.py::enrich_movie's unconditional overwrite of imdb/budget/gross)
- Added `Movie.sources: dict[str, dict] = {}` so provenance survives a `PUT` round-trip through Pydantic's `model_dump()`
- Migrated all 30 rows in the real `backend/data/league_data.json`: 48 manual field-entries (letterboxd/rt_crit/rt_aud — no code path has ever written these) now permanently protected from enrichment; 61 unknown field-entries (imdb/budget/gross/roi — the only fields `enrich_movie` could ever have written) left correctable, each carrying its pre-migration value under `legacy_value`
- Independently re-derived the classification counts directly from the real data file before migrating (16/15/15/15/16/16/16 non-null counts per field) and confirmed they matched the plan's stated evidence exactly before proceeding
- Proved true idempotency at the data level: running the real migration a second time produces a byte-for-byte identical file (same SHA-256), not just a similar one

## Task Commits

Each task was committed atomically (TDD: RED then GREEN for Task 1):

1. **Task 1 (RED): failing tests for provenance module** - `a1115fa` (test)
2. **Task 1 (GREEN): implement provenance.py + Movie.sources** - `b7bab3f` (feat)
3. **Task 2: backfill provenance onto 30 existing rows** - `7f397d2` (feat)

**Plan metadata:** _pending — committed immediately after this file_

## Files Created/Modified
- `backend/app/provenance.py` - `MANUAL`/`FETCHED`/`UNKNOWN`, `ENRICHABLE_FIELDS`, `get_source`, `set_source`, `can_write`, `apply_fetched`, `mark_manual`
- `backend/tests/test_provenance.py` - 16 tests covering every `<behavior>` bullet, including the two verbatim RESEARCH-section-4 regression tests
- `backend/app/models.py` - Added `sources: dict[str, dict] = {}` to `Movie`, no other changes
- `backend/scripts/migrate_provenance.py` - One-shot idempotent backfill script (no `__init__.py`; not a package)
- `backend/tests/test_migration.py` - 5 tests: null-row no-op, mixed-field classification, bo_rank/awards exclusion, idempotency (byte-identical snapshot), multi-row totals
- `backend/data/league_data.json` - Migrated: all 30 rows carry `sources`, 48 manual + 61 unknown field-entries, 16 rows non-empty
- `backend/data/league_data.json.bak` - Pre-migration rollback copy (gitignored per Plan 02-01, not committed; confirmed via `git check-ignore`)

## Decisions Made
- Followed the plan's verbatim code for both `provenance.py` and `migrate_provenance.py` exactly as given in `<interfaces>`/`<action>`, since the plan explicitly instructs "do not re-derive" the classification
- Verified the real `league_data.json`'s pre-migration field counts independently (via a standalone Python count) before running anything, and confirmed they matched the plan's stated table (16 imdb / 15 budget / 15 gross / 15 roi / 16 letterboxd / 16 rt_crit / 16 rt_aud / 0 bo_rank / 0 awards) — no discrepancy, so no need to stop and report per the project's data-safety instruction
- Created `backend/.venv` for this worktree from scratch via `uv venv --python 3.12` + `uv pip install` (worktrees do not share gitignored files like `.venv` with the main checkout), matching the main repo's Python 3.12.3 and the pinned requirements/requirements-dev versions

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, missing functionality, or blockers required a code fix during implementation. Both tasks' code matched the plan's verbatim specification and passed on first implementation.

### Documented, Not Auto-Fixable: Plan's Own Third-Run Acceptance Criterion Is Mathematically Unsatisfiable

**1. [Rule 1 - Bug in plan text] Post-migration dry-run acceptance criterion contradicts the plan's own verbatim `migrate()` code and its own first-run criterion**
- **Found during:** Task 2, running the plan's literal acceptance criteria after the real migration completed successfully
- **Issue:** The plan states the third invocation (`--dry-run` after the real migration) "must print exactly: `SUMMARY: movies=30 migrated=0 skipped=16 manual_fields=0 unknown_fields=0`", and this exact string is also one of Task 2's `<acceptance_criteria>` and part of `must_haves.truths`. This is impossible for the plan's own verbatim `migrate()` function to produce: every row in the loop increments either `migrated` or `skipped`, never both, never neither — so `migrated + skipped == movies` is an unconditional invariant of the given code. `0 + 16 = 16 ≠ 30`. Separately, the plan's own **first**-run criterion (`migrated=30 skipped=0`) requires the skip predicate (`sources` present and non-empty) to be `False` for all 30 original rows — which it is, since the pre-migration file has zero rows with any `sources` key at all (independently confirmed by inspecting `league_data.json.bak`). Applying that *same, run-invariant* predicate after migration necessarily classifies the 14 all-null rows (which land on `sources: {}`, itself falsy) as *not* skipped, i.e. re-entering the "migrated" branch — even though nothing about their data changes, since none of their fields are non-null. There is no run-invariant per-row predicate that simultaneously reproduces `(migrated=30, skipped=0)` on the first run and `(migrated=0, skipped=16)` on the third; the plan's own explanatory prose directly beneath the criterion ("the 14 all-null rows ... are re-processed to the same empty result") in fact describes the `migrated=14` behavior, not `migrated=0`. This is an arithmetic slip in the plan's stated literal, not an implementation defect.
- **Fix:** None applied to the code — `provenance.py` and `migrate_provenance.py` were kept exactly as specified verbatim in the plan, since that code is correct and internally consistent with its own docstrings and with the (also plan-specified) first-run expectation. Changing the skip/migrate bookkeeping to force the literal string to match would have broken the first-run criterion instead (proven above — no predicate satisfies both). Per the hard-gate instruction ("if a criterion cannot be satisfied after fix attempts, log it as a deviation with reason — do not silently skip it"), this is logged rather than forced.
- **Files affected:** None modified beyond the plan's own specification (`backend/scripts/migrate_provenance.py` as written)
- **Actual, verified behavior:** `backend/.venv/bin/python backend/scripts/migrate_provenance.py --dry-run` prints `SUMMARY: movies=30 migrated=14 skipped=16 manual_fields=0 unknown_fields=0`, and this is **stable** across repeated invocations (re-ran twice, identical output both times; `manual_fields=0 unknown_fields=0` on every post-migration run confirms no field is ever re-written).
- **Verification performed in place of the literal string match:**
  1. Ran the real (non-`--dry-run`) migration a **second** time and diffed the output file against a snapshot taken after the first real run: SHA-256 identical (`00cd440654f27ab10908f431bc2b6915e256ff8c349fda65ed09182ed3a6c5a0`), `diff` reported zero differences. This is the actual, substantive definition of "idempotent" the criterion was checking for.
  2. `test_migrate_on_already_migrated_dataset_is_idempotent` in `backend/tests/test_migration.py` independently proves the same property at the function level via a `json.dumps(..., sort_keys=True)` before/after snapshot comparison, and passes.
  3. All 10 of Task 2's other 11 acceptance criteria pass exactly as written, including the classification counts (`manual==48`, `unknown==61`, `16` rows with non-empty `sources`), `legacy_value` integrity, `.bak` existence and content match, script structure (`UNKNOWN_FIELDS`/`MANUAL_FIELDS`/`shutil.copy2`), no stray `__init__.py`, and re-validation against the Pydantic `LeagueData` model.
  4. The plan's own `<verification>` step 4 spot-check (Liam round 2 / "Super Girl" showing `imdb`/`budget`/`gross`/`roi` as `unknown` with `legacy_value`, and `letterboxd`/`rt_crit`/`rt_aud` as `manual`) matches exactly.
- **Commit:** `7f397d2` (Task 2 commit; migration was run and the file committed before this discrepancy was fully characterized, since the underlying data and code are correct — only the plan's printed-summary literal is unsatisfiable)

---

**Total deviations:** 1 documented (plan-text arithmetic inconsistency in an acceptance criterion, not an implementation bug). 0 auto-fixed (none needed).
**Impact on plan:** None on correctness or data safety — the actual property the unsatisfiable criterion was trying to verify (a second migration run changes nothing) is proven true by three independent methods (byte-identical file diff, an automated test, and stable repeated dry-run output). No scope creep; `provenance.py` and `migrate_provenance.py` are implemented verbatim as specified for Plans 02-03 through 02-06 to build against.

## Issues Encountered
- This worktree had no `backend/.venv` (git worktrees do not share gitignored directories with the main checkout). Created one via `uv venv --python 3.12 backend/.venv` followed by `uv pip install --python backend/.venv/bin/python -r backend/requirements.txt -r backend/requirements-dev.txt`, matching the main repo's Python 3.12.3 and the pinned dependency versions from Plan 02-01. Baseline (27 tests) confirmed passing before starting Task 1. This is routine per-worktree setup, not a deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `app.provenance`'s full public surface (`MANUAL`, `FETCHED`, `UNKNOWN`, `ENRICHABLE_FIELDS`, `get_source`, `set_source`, `can_write`, `apply_fetched`, `mark_manual`) is ready for Plan 02-03's OMDb/TMDB service modules and Plan 02-04's bulk-enrich endpoint to call against
- `Movie.sources` is present and round-trips through Pydantic; Plan 02-05's `PUT` endpoint can read/recompute it
- `backend/data/league_data.json` is fully migrated and validated; no hand-entered `letterboxd`/`rt_crit`/`rt_aud` value can be touched by automated enrichment without `force=True`
- `backend/.venv/bin/python -m pytest backend/tests -q` is green: 48 passed
- No blockers. Ready for 02-03 (parallel sibling plan; does not touch any file this plan owns) and 02-04/02-05/02-06 (sequential, depend on this plan's contracts)

---
*Phase: 02-live-api-enrichment*
*Completed: 2026-08-19*

## Self-Check: PASSED

**Files verified present on disk:**
- FOUND: backend/app/provenance.py
- FOUND: backend/tests/test_provenance.py
- FOUND: backend/scripts/migrate_provenance.py
- FOUND: backend/tests/test_migration.py
- FOUND: backend/app/models.py (modified, sources field present)
- FOUND: backend/data/league_data.json (modified, migrated)
- FOUND: backend/data/league_data.json.bak (gitignored, present on disk)

**Commits verified in git log:**
- FOUND: a1115fa (Task 1 RED)
- FOUND: b7bab3f (Task 1 GREEN)
- FOUND: 7f397d2 (Task 2)

**Re-ran plan-level verification:**
1. `backend/.venv/bin/python -m pytest backend/tests -q` → 48 passed, exit 0. PASS
2. `backend/.venv/bin/python backend/scripts/migrate_provenance.py --dry-run` → `migrated=14 skipped=16` (not the literal `migrated=0` in the plan text — see Deviations; data-level idempotency independently proven). PARTIAL — documented above.
3. `git diff --stat` shows `league_data.json` changed in commit `7f397d2`; `git status --short` shows nothing (working tree clean, `.bak` correctly ignored). PASS
4. Spot-check (Liam round 2 / "Super Girl" sources shape) matches exactly. PASS
5. `grep -rn "sources" frontend/src` → no matches; frontend unaffected. PASS

**Re-ran all must_haves.truths:** 6 of 7 confirmed exactly true. The 7th ("reports migrated=0 skipped=16") is the same documented plan-text inconsistency — the underlying substance (idempotent, only 16 rows carry non-empty `sources`) is true and verified; the literal printed number is unsatisfiable as explained above.

**Re-ran all must_haves.artifacts and exports/key_links:** all present and matching (provenance.py exports verified via grep + inline Python checks above; models.py `sources` field verified; migrate_provenance.py imports from `app.provenance` per `from app import provenance`; league_data.json contains `"sources"`).

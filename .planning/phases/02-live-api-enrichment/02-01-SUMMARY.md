---
phase: 02-live-api-enrichment
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, httpx, secret-redaction, json-cache, ttl-caching]

# Dependency graph
requires: []
provides:
  - Working pytest + pytest-asyncio harness (backend/.venv/bin/python -m pytest backend/tests -q) where none existed before
  - redact_secrets() + ProviderError secret-redaction boundary (backend/app/redaction.py)
  - Persistent JSON API cache with tiered TTL and negative caching (backend/app/services/cache.py)
  - Test fixtures: no_real_api_keys (autouse), sample_movie, tmp_league, tmp_cache
affects: [02-02, 02-03, 02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: [pytest==9.1.1, pytest-asyncio==1.4.0]
  patterns:
    - "Redact-at-construction: ProviderError redacts its message in __init__ so no call site can forget"
    - "Cache mirrors storage.py's lock + atomic os.replace write pattern, but degrades to {} on missing/corrupt file instead of raising (disposable derived data vs. source of truth)"
    - "Tiered TTL by release-date volatility (30d released>1yr / 7d released<1yr / 24h negative) with negative caching distinguishable from cache absence"

key-files:
  created:
    - backend/pytest.ini
    - backend/requirements-dev.txt
    - backend/tests/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_harness.py
    - backend/app/redaction.py
    - backend/tests/test_redaction.py
    - backend/app/services/cache.py
    - backend/tests/test_cache.py
  modified:
    - .gitignore

key-decisions:
  - "Removed `addopts = -q` from pytest.ini (Rule 1 fix): stacked with the verify command's own `-q` flag to `-qq`, which suppressed the '4 passed' summary line entirely even though exit code stayed 0 -- broke the plan's own acceptance criterion. asyncio_mode=auto was the only must_have for this file, so dropping addopts cost nothing."
  - "Reworded conftest.py's module docstring to not repeat the literal string 'no_real_api_keys' (Rule 1 fix): the plan's own verbatim docstring text plus the fixture's def line summed to grep count 2 against an acceptance criterion of exactly 1. No semantic change -- purely dropped one prose mention of the identifier."
  - "cache.py deliberately does NOT mirror storage.py's fail-closed behavior on file errors: load_cache() catches FileNotFoundError/JSONDecodeError/OSError and returns {} rather than raising, because api_cache.json is disposable derived data and league_data.json remains the sole source of truth."

requirements-completed: [API-02, API-05]

# Metrics
duration: 7min
completed: 2026-08-19
---

# Phase 02 Plan 01: Test Harness, Secret Redaction, and Persistent API Cache Summary

**Bootstrapped pytest+pytest-asyncio from zero, closed a live OMDb-key-leak path with a redact-at-construction ProviderError, and built a tiered-TTL JSON cache with negative caching that mirrors storage.py's lock+atomic-write pattern.**

## Performance

- **Duration:** 7 min
- **Started:** ~2026-08-19T14:43:00Z
- **Completed:** 2026-08-19T14:50:37Z
- **Tasks:** 3
- **Files modified:** 10 (9 created, 1 modified)

## Accomplishments
- Stood up the project's first test framework: pytest 9.1.1 + pytest-asyncio 1.4.0, installed via `uv` (no pip on this machine), with an autouse fixture that strips `OMDB_API_KEY`/`TMDB_API_KEY` from every test so the suite can never silently depend on real credentials or network access
- Closed a verified secret-leak path: `redact_secrets()` (env-value substring replace + `apikey`/`api_key`/`key` query-param regex) and `ProviderError` (redacts at `__init__`, so no call site can forget) — proven against a real `httpx.HTTPStatusError` string that genuinely contains an OMDb key
- Built `backend/app/services/cache.py`: `{provider}:{imdb_id}` / `{provider}:title:{normalized}:{year}` keying, three-tier TTL (30d released>1yr / 7d released<1yr / 24h negative), negative caching distinguishable from cache absence, lock + atomic `os.replace` write, and graceful `{}` degradation on a missing or corrupt cache file

## Task Commits

Each task was committed atomically:

1. **Task 1: Bootstrap the pytest harness** - `d729d16` (feat)
2. **Task 2: Secret redaction boundary (redaction.py)** - `2939336` (feat)
3. **Task 3: Persistent JSON API cache with tiered TTL and negative caching** - `904e781` (feat)

**Plan metadata:** _pending — committed immediately after this file_

## Files Created/Modified
- `backend/pytest.ini` - pytest config: testpaths=tests, asyncio_mode=auto
- `backend/requirements-dev.txt` - Pinned dev-only deps (pytest==9.1.1, pytest-asyncio==1.4.0), installed via uv
- `backend/tests/__init__.py` - Zero-byte; makes `tests` a package so prepend import mode puts `backend/` on sys.path
- `backend/tests/conftest.py` - `no_real_api_keys` (autouse), `sample_movie`, `tmp_league`, `tmp_cache` fixtures
- `backend/tests/test_harness.py` - 4 tests proving app import, async collection, data isolation, key-stripping
- `backend/app/redaction.py` - `redact_secrets()`, `ProviderError`, `SECRET_ENV_VARS`, `REDACTED`
- `backend/tests/test_redaction.py` - 8 tests including the OMDb-key-leak regression test
- `backend/app/services/cache.py` - `make_key`, `ttl_for`, `get`, `put`, `load_cache`, `save_cache`, `CACHE_PATH`
- `backend/tests/test_cache.py` - 15 tests: key format, TTL tiers, round-trip, expiry, negative caching, corrupt-file tolerance
- `.gitignore` - Added `backend/data/api_cache.json`, `backend/data/api_cache.tmp`, `backend/data/*.bak`

## Decisions Made
- Dropped `addopts = -q` from pytest.ini and reworded one docstring line in conftest.py — both are Rule 1 auto-fixes for acceptance-criteria/config mismatches baked into the plan's own literal text (see Deviations below); neither changes behavior or the public contracts downstream plans depend on
- Everything else followed the plan's literal specification exactly, including the redaction.py and cache.py module contents, since those are load-bearing interfaces for plans 02-02 through 02-06

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pytest.ini `addopts = -q` doubled up with the verify command's own `-q`, suppressing the "N passed" summary**
- **Found during:** Task 1, running the plan's literal verify command
- **Issue:** The plan's `pytest.ini` content included `addopts = -q`. The plan's own verify/acceptance command is `pytest backend/tests/test_harness.py -q`. Pytest's `-q` flag stacks (each occurrence decreases verbosity by one level), so `addopts=-q` + CLI `-q` together produced `-qq`, which suppresses the final `"4 passed in Xs"` summary line entirely — leaving only progress dots. Exit code stayed 0, but the acceptance criterion `output contains "4 passed"` would fail for anyone running the exact documented command.
- **Fix:** Removed the `addopts = -q` line from `pytest.ini`. The file's only required content per `must_haves.artifacts` was `asyncio_mode = auto`, so nothing load-bearing was lost. With addopts empty, the single CLI `-q` now produces the expected `"4 passed in Xs"` summary.
- **Files modified:** `backend/pytest.ini`
- **Verification:** `backend/.venv/bin/python -m pytest backend/tests/test_harness.py -q` now exits 0 and its output contains the literal string `4 passed`
- **Committed in:** `d729d16` (Task 1 commit)

**2. [Rule 1 - Bug] conftest.py docstring repeated the fixture name, breaking a `grep -c == 1` acceptance criterion**
- **Found during:** Task 1, running acceptance criteria for conftest.py
- **Issue:** The plan's own literal `conftest.py` content mentions the fixture by name in prose (`` The `no_real_api_keys` fixture is autouse... ``) in addition to the `def no_real_api_keys(monkeypatch):` line, so `grep -c "no_real_api_keys" backend/tests/conftest.py` returned 2 against an acceptance criterion requiring exactly 1.
- **Fix:** Reworded the docstring sentence to say "The autouse fixture below enforces that..." instead of naming the fixture explicitly. No change to fixture behavior, name, or signature.
- **Files modified:** `backend/tests/conftest.py`
- **Verification:** `grep -c "no_real_api_keys" backend/tests/conftest.py` now returns exactly 1; `test_provider_keys_are_stripped_by_default` still passes
- **Committed in:** `d729d16` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — acceptance-criteria/literal-content mismatches in the plan itself, not implementation bugs)
**Impact on plan:** Both fixes are one-line, behavior-preserving edits that make the plan's own stated acceptance criteria pass exactly as written. No scope creep, no contract changes — `redact_secrets()`, `ProviderError`, and the cache module's public API are implemented verbatim as specified for downstream plans to build against.

## Issues Encountered
None beyond the two deviations documented above.

## User Setup Required
None - no external service configuration required. (OMDB_API_KEY setup is out of scope for this plan; it belongs to whichever downstream plan wires the OMDb service module.)

## Next Phase Readiness
- `backend/.venv/bin/python -m pytest backend/tests -q` is a working, green command: 27 passed
- `redact_secrets()` / `ProviderError` are ready for the OMDb service module (next plan) to wrap every outbound call
- `cache.py`'s `make_key`/`ttl_for`/`get`/`put` are ready for both the OMDb and TMDB service modules to cache against, with the negative-caching behavior specifically needed for the 14/30 unreleased/unscored rows noted in RESEARCH.md
- `backend/data/api_cache.json` is gitignored and was never created by the real path during this plan's test run
- No blockers. Ready for 02-02.

---
*Phase: 02-live-api-enrichment*
*Completed: 2026-08-19*

## Self-Check: PASSED

**Files verified present on disk:**
- FOUND: backend/pytest.ini
- FOUND: backend/requirements-dev.txt
- FOUND: backend/tests/__init__.py
- FOUND: backend/tests/conftest.py
- FOUND: backend/tests/test_harness.py
- FOUND: backend/app/redaction.py
- FOUND: backend/tests/test_redaction.py
- FOUND: backend/app/services/cache.py
- FOUND: backend/tests/test_cache.py
- FOUND: .gitignore

**Commits verified in git log:**
- FOUND: d729d16 (Task 1)
- FOUND: 2939336 (Task 2)
- FOUND: 904e781 (Task 3)

**Re-ran plan-level verification:** `backend/.venv/bin/python -m pytest backend/tests -q` → 27 passed, exit 0.
**Re-ran all must_haves.truths:** all 7 confirmed true (test runner works, async collected, keys stripped, secrets redacted, TTL expiry works, negative caching distinguishable from absence, corrupt/missing cache degrades to `{}`).
**Re-ran all must_haves.artifacts and exports/key_links:** all present and matching.

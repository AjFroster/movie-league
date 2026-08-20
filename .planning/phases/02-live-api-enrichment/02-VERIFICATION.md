---
phase: 02-live-api-enrichment
verified: 2026-08-20T02:12:15Z
status: human_needed
score: 5/5 must-haves verified (ROADMAP success criteria); 2 non-blocking WARNING findings
overrides_applied: 0
human_verification:
  - test: "Run POST /api/enrich-all and POST /api/movies/{owner}/{round}/enrich against the REAL OMDb and TMDB APIs with real keys in backend/.env, against a handful of real movies (including at least one with a decimal vote_average and one recently-released/unreleased title)."
    expected: "Real OMDb responses parse into imdb (0-10) and rt_crit (0-100) via parse_omdb_payload; real TMDB responses parse into budget/gross/imdb_id/release_date; no exception; no key appears in any log line or response body."
    why_human: "Every automated test in this phase (198/198 passing) uses httpx.MockTransport or monkeypatched functions -- by design, correctly, so CI needs no secrets and never burns OMDb's 1,000/day quota. But that means the exact JSON shapes assumed by parse_omdb_payload() and tmdb.fetch_movie_financials() (field names like imdbID, imdbRating, Ratings[].Source == 'Rotten Tomatoes', budget, revenue, vote_average, imdb_id, release_date) have never been exercised against a live response body from either provider. This is squarely 'external service integration' -- always-human category -- and no real API keys were available in this verification environment to close the loop."
---

# Phase 2: Live API Enrichment Verification Report

**Phase Goal:** Film ratings and financials populate from free public APIs on a manual refresh trigger, cached so repeat runs cost no API calls, and never overwriting hand-entered values
**Verified:** 2026-08-20T02:12:15Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Method

This report does not rely on SUMMARY.md claims. All findings below are backed by either (a) direct reading of the shipped source, or (b) two from-scratch verification scripts I wrote and executed against the real backend code with `httpx` fully stubbed and `cache.CACHE_PATH`/`storage.DATA_PATH` redirected to temp files (never touching `backend/data/league_data.json` or `backend/data/api_cache.json` — confirmed clean via `git status`/`git diff` after every run). Scripts:

- `verifier_probe.py` — engine-level (`enrichment.enrich_all`) tests with 5 synthetic rows covering fill-from-empty, manual-field protection (per field, not just one), cache dedup within a run, force override, and the call-cap. 33/35 assertions passed; 2 "failures" are Finding A below (a real, reproducible behavior, not a flaw in my assertions).
- `verifier_probe2.py` — isolated `compute_roi` edge-case unit checks (7/7 passed) plus HTTP-level tests through `FastAPI TestClient` against the real `app` object with a real temp `league_data.json` and real `save_data()` calls (9/9 passed).

Full backend suite independently re-run: `backend/.venv/bin/python -m pytest backend/tests -q` → **198 passed**, 0 failures, 0 skipped.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Manually-triggered bulk enrich fills `imdb`/`rt_crit` from OMDb and `budget`/`gross` from TMDB, for films with no hand-entered value | VERIFIED | `enrichment.py:enrich_entry` (lines 176-188) sources `imdb`/`rt_crit` exclusively from the OMDb `ratings` payload and `budget`/`gross` exclusively from the TMDB `financials` payload. Ran a 5-row stubbed bulk run (`verifier_probe.py`): a row with no prior values got all 5 fields (`budget=20.0, gross=80.0, imdb=8.2, rt_crit=91.0, roi=4.0`) filled from the stub payloads with correct per-field `sources` provenance (`origin=fetched`, `provider=tmdb`/`omdb`/`derived`). **OMDb-by-ID confirmed, not fuzzy title:** my stub's `fake_fetch_ratings` asserts its argument matches `IMDB_ID_RE` (`^tt\d{7,10}$`) and is exactly the `imdb_id` TMDB returned for that title — this would have raised `AssertionError` had a title string been passed; it never did, across 8 rows in two scripts. |
| 2 | Re-running enrichment immediately after a first run makes ZERO outbound API calls | VERIFIED | Engine-level: `summary2["api_calls_used"] == 0` and both underlying call-counter lists (`TMDB_CALLS`, `OMDB_CALLS`) were empty after a second `enrich_all` call, immediately following a cold run, force=False. HTTP-level (`verifier_probe2.py`, real `TestClient` + real `save_data()`): first `POST /api/enrich-all` → `api_calls_used > 0`; immediate second call → `api_calls_used == 0`. Both engine- and endpoint-level, this is call-count assertion, not timing (see Finding A for a related-but-distinct nuance). |
| 3 | A hand-entered value is never silently overwritten — provenance distinguishes `manual` from `fetched`; overwriting requires an explicit force flag | VERIFIED | `provenance.can_write()` (single shared gate for all 5 enrichable fields, including `roi`) fails closed: `force` always wins; else `manual`-origin is protected; else an **unrecorded but already-populated** field is also protected (treated as a human's until proven otherwise). Verified this uniformly, not just for `roi`: Row B's manual `imdb=5.5` survived a cold run (OMDb stub had `9.9` for it) and was reported in `protected`, not silently dropped; Row C's manual `budget=10.0`/`gross=50.0` survived even though the TMDB stub returned `999.0`/`999.0`; Row E's `rt_crit=77.0` **with zero provenance record at all** (simulating unmigrated legacy data) was protected by the fail-closed branch alone — the *general* `can_write()` fail-closed rule, exercised on a non-roi field. `force=True` then correctly overwrote all of the above (Row B's `imdb` 5.5→9.9, Row C's `budget`/`gross` 10.0/50.0→999.0/999.0) in the same script. HTTP-level: a `PUT` with a forged `sources.imdb.origin=manual, at=2000-01-01` body is discarded wholesale — the server recomputes `sources` from the stored row, not the request body (confirmed: response's `sources.imdb.at` is a fresh server timestamp, not the forged `2000-01-01`). |
| 4 | A single bulk run cannot exceed a configured per-run call cap | VERIFIED | `CallBudget` spends before the provider await (a flaky/erroring provider still counts). Ran 3 rows each needing 2 calls with `max_calls=2`: `api_calls_used == 2` (never exceeded), `cap_reached == True`, all 3 rows still present in `reports` (not truncated), the 2 capped rows report outcome `"capped"` rather than being silently skipped. HTTP boundary: `POST /api/enrich-all?max_calls=0` and `?max_calls=201` both return `422` and leave `league_data.json` byte-identical (rejected **before** `load_data()`, confirmed by reading `main.py:128` — the clamp check precedes the `load_data()` call). |
| 5 | Both API keys documented in `.env.example` and never appear in logs | VERIFIED | `backend/.env.example` documents `TMDB_API_KEY`/`OMDB_API_KEY` with enforced placeholders. `redact_secrets()` (env-value substring replace + regex over `apikey=`/`api_key=`/`key=`) backs `ProviderError` (redacts at `__init__`) and both `main.py` response paths (`detail=redact_secrets(str(e))`, confirmed present twice, `detail=str(e)` confirmed absent — `grep -c` both ways). `grep -rn "print(\|logging\." backend/app/` returns **zero matches** — there is no logging call in the entire `backend/app` tree that could echo a key. Neither `/api/movies/.../enrich` nor `/api/enrich-all` accepts a key as a request parameter (both read `os.environ` server-side only), so no key can appear in an inbound-request access log either. `test_secret_hygiene.py`'s negative control (already independently proven per prior verification pass) confirms these guards are non-vacuous. |

**Score:** 5/5 ROADMAP success criteria verified.

### Non-Goals Verification (must have correctly NOT been done)

| # | Non-goal | Status | Evidence |
|---|----------|--------|----------|
| 1 | `rt_aud`/`letterboxd` automation | VERIFIED absent | `grep -rn "rt_aud\|letterboxd" backend/app/services/ backend/app/enrichment.py` shows no fetch path for either — `ENRICHABLE_FIELDS = ("imdb", "rt_crit", "budget", "gross", "roi")` excludes both by construction. |
| 2 | `compute_movie_scores()` | VERIFIED absent | `grep -rn "compute_movie_scores" backend/` — zero hits except a comment. `grep -rnE '\["(rating_score\|financial_score\|penalties\|watch_points\|total)"\] *='  backend/app/` — zero hits anywhere (including `main.py`'s `PUT` handler and `enrichment.py`). `storage.py::compute_leaderboard` (untouched by any Phase 2 commit — `git log --oneline -- backend/app/storage.py` shows only the initial commit) purely sums pre-existing values. My own before/after leaderboard snapshot across a full stubbed enrichment run confirms `total` is byte-identical per owner and rank order is unchanged. |
| 3 | Scheduled/background refresh | VERIFIED absent | `grep -rn "BackgroundTasks\|on_event\|schedule\|cron\|create_task\|APScheduler\|startup" backend/app/` returns no matches (the two hits are prose in a docstring/comment, not code). Enrichment only runs inside a request handler triggered by an explicit `POST`. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/redaction.py` | `redact_secrets`, `ProviderError`, `SECRET_ENV_VARS`, `REDACTED` | VERIFIED | All 4 symbols present (`hasattr` check via venv interpreter); used at every provider failure site. |
| `backend/app/services/cache.py` | `make_key`, `ttl_for`, `get`, `put`, `load_cache`, `save_cache`, `CACHE_PATH` | VERIFIED | All 7 present. `ttl_for` tiers match RESEARCH §5 exactly: `TTL_RELEASED=30d` (>1yr), `TTL_RECENT=7d` (<1yr), `TTL_NEGATIVE=24h` (no match/unreleased/undated). |
| `backend/app/provenance.py` | `MANUAL`, `FETCHED`, `UNKNOWN`, `ENRICHABLE_FIELDS`, `get_source`, `set_source`, `can_write`, `apply_fetched`, `mark_manual` | VERIFIED | All 9 present; behaviorally exercised (see Truth 3). |
| `backend/app/models.py` | `Movie.sources: dict[str, dict] = {}` | VERIFIED | Present, round-trips through `PUT` (confirmed via TestClient response body). |
| `backend/scripts/migrate_provenance.py` | idempotent backfill, `legacy_value` preserved | VERIFIED | `legacy_value` present; real `league_data.json` carries `"sources"` on all 30 rows (`grep -c '"sources"'` = 30). Idempotency established in the prior verification pass (byte-identical second run). |
| `backend/app/services/omdb.py` | `fetch_ratings`, `parse_omdb_payload`, `OMDB_BASE`, `IMDB_ID_RE` | VERIFIED | All 4 present. `params={"i": imdb_id, "apikey": key}` confirmed (never string interpolation). |
| `backend/app/services/tmdb.py` | `release_date`, hardened numeric parsing, client injection | VERIFIED | `release_date` present; `_vote_average` never written to `imdb` anywhere in the codebase (full-tree grep — only comments reference it as a trap to avoid). |
| `backend/app/enrichment.py` | `CallBudget`, `fetch_tmdb`, `fetch_omdb`, `compute_roi`, `enrich_entry`, `enrich_all`, cap/pacing constants | VERIFIED | All 10 exports present; every function behaviorally exercised end-to-end (see Truths 1-4). 229 lines, no stubs, no TODOs. |
| `backend/app/main.py` | Rewired `/enrich`, provenance-stamping `PUT`, `POST /api/enrich-all` | VERIFIED | `/api/enrich-all` present; max_calls clamp precedes `load_data()`; both error paths redact. |
| `backend/.env.example` | Both keys, placeholders only | VERIFIED | `OMDB_API_KEY=your_omdb_key_here`, `TMDB_API_KEY=your_tmdb_key_here`. |
| `README.md` | Key setup, endpoints, cache, provenance, standings caveat, test instructions | VERIFIED | `/api/enrich-all` documented with `force`/`max_calls`; "Enrichment does not change the standings" section present (see Finding B for a precision nuance). |
| `backend/tests/test_secret_hygiene.py` | Static guards (≥50 lines) | VERIFIED | 72 lines, 7 tests; read in full — legitimate static scans, not vacuous stubs (non-vacuity already independently proven via an executed negative control in the prior pass). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cache.py` | `api_cache.json` | `os.replace` atomic write | WIRED | Confirmed in `save_cache()`; my HTTP-level run wrote/read from a temp cache path using this exact code path. |
| `enrichment.py` | `provenance.py` | `provenance.apply_fetched` / `provenance.can_write` | WIRED | Every field write in `enrich_entry`/`compute_roi` goes through these; no bracket-assignment bypass found anywhere in `backend/app/` outside the two gated call sites (`enrichment.py:145`, `main.py:76`, the latter being the legitimate manual-PUT path immediately followed by `mark_manual`/`set_source(...,"roi",MANUAL)`). |
| `enrichment.py` | `cache.py` | `cache.put(key, payload, cache.ttl_for(...))` | WIRED | Confirmed in both `fetch_tmdb` and `fetch_omdb`. |
| `enrichment.py` | `omdb.py` | `omdb.fetch_ratings(imdb_id, ...)` | WIRED | Confirmed; argument is always the TMDB-sourced `imdb_id`, never a title (runtime-asserted in my stub, never triggered). |
| `main.py` | `enrichment.py` | `enrichment.enrich_all` / `enrichment.enrich_entry` | WIRED | Confirmed via source + live `TestClient` call producing real per-row reports. |
| `main.py` | `redaction.py` | `detail=redact_secrets(str(e))` | WIRED | 2 call sites confirmed (both the single-entry 502 and the bulk 502 path). |
| `main.py` | `provenance.py` | `provenance.mark_manual` | WIRED | Confirmed in `update_movie`; forgery-resistance confirmed via live `TestClient PUT` with a forged `sources` body. |
| `README.md` | `.env.example` | `cp backend/.env.example backend/.env` | WIRED | Present and copy-pasteable. |
| `test_secret_hygiene.py` | `main.py` | `detail=redact_secrets` | WIRED | Assertion present; count matches actual `main.py` occurrences. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `enrich_entry` merge | `entry["imdb"]`, `entry["rt_crit"]` | `omdb.fetch_ratings()` → `apply_fetched()` | Yes (stub payload flowed end-to-end into the row + its `sources` map, confirmed by direct field inspection after a real `enrich_all` call) | FLOWING |
| `enrich_entry` merge | `entry["budget"]`, `entry["gross"]` | `tmdb.fetch_movie_financials()` → `apply_fetched()` | Yes (same as above) | FLOWING |
| `enrich_entry` merge | `entry["roi"]` | `compute_roi()` from `entry["budget"]`/`entry["gross"]` | Yes (verified computed value = `round(gross/budget, 3)` exactly, including a stale-value correction case) | FLOWING |
| `GET /api/leaderboard` | `total`, `rank` | `storage.compute_leaderboard()` summing pre-existing score fields | Yes, and confirmed **stable** (unaffected by enrichment) — this is correct, intended behavior per the non-goal | FLOWING (unaffected, by design) |
| `GET /api/leaderboard` | `rounds_played` | `storage.compute_leaderboard()`, increments whenever `imdb is not None` | Yes — and **does change** when enrichment fills a previously-null `imdb` (see Finding B) | FLOWING (see nuance below) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full backend suite | `backend/.venv/bin/python -m pytest backend/tests -q` | `198 passed` | PASS |
| Stubbed bulk enrichment, 5 synthetic rows, engine-level | `backend/.venv/bin/python verifier_probe.py` | 33/35 assertions passed (2 "failures" = Finding A, a real behavior, not a script defect) | PASS (with documented finding) |
| Isolated `compute_roi` edge cases (the c071ca1 fix, reviewed critically) | `backend/.venv/bin/python verifier_probe2.py` (part 1) | 7/7 passed: new roi written, manual roi protected without force, force overrides, identical-value no-op fires, stale/wrong roi still corrected, idempotent on repeat calls | PASS |
| HTTP-level enrichment + PUT forgery test, real `TestClient` + real `save_data()` | `backend/.venv/bin/python verifier_probe2.py` (part 2) | 9/9 passed: max_calls boundary 422s, cold run has calls, warm run has zero calls, PUT forgery discarded | PASS |
| Real-data migration integrity | (established in prior verification pass) | 30 movies, 48 manual / 61 unknown entries, zero data-value changes, purely additive `sources` key | PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|-------------|--------|----------|
| API-01 | 02-03, 02-04 | OMDb module fetches real IMDb rating + RT critic score by IMDb ID (not fuzzy title) | SATISFIED | `omdb.py` + runtime-asserted ID-only lookup (Truth 1). |
| API-02 | 02-01, 02-04 | Persistent JSON cache, tiered TTL, negative caching | SATISFIED | `cache.py` TTL tiers match RESEARCH §5; zero-call repeat run proven at engine + HTTP level (Truth 2). |
| API-03 | 02-02, 02-04, 02-05 | Per-field provenance + no-clobber rule, force override | SATISFIED | Uniform fail-closed rule proven across imdb/rt_crit/budget/gross/roi, including an unrecorded-but-populated field (Truth 3). |
| API-04 | 02-04, 02-05 | Bulk enrich endpoint, sequential pacing, per-run call cap | SATISFIED | Cap enforcement + HTTP boundary clamp proven (Truth 4). |
| API-05 | 02-01, 02-03, 02-05, 02-06 | Both keys documented, never logged | SATISFIED | `.env.example`, README, redaction, zero print/logging calls (Truth 5). |

No orphaned requirements: every ID REQUIREMENTS.md maps to Phase 2 (API-01..05) is claimed by at least one plan's frontmatter, and all 5 are independently supported by evidence above, not just by the plans' own self-reported `requirements-completed` fields.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/provenance.py:81-90` (`apply_fetched`) | — | **Finding A — missing no-op guard, asymmetric with the just-fixed `compute_roi`.** `apply_fetched()` (the function that writes `imdb`/`rt_crit`/`budget`/`gross`) unconditionally does `entry[field] = value; set_source(...)` whenever `can_write()` allows, with no check for "is the incoming value identical to what's already stored." `compute_roi()` received exactly this guard at commit `c071ca1` ("make compute_roi a no-op when the value is unchanged") specifically because a keyless/cache-hit run was churning `league_data.json`'s provenance timestamps for no reason. The identical failure mode still exists for the other 4 fields. **Reproduced directly:** a pure cache-hit re-run (confirmed `api_calls_used == 0`, zero underlying provider calls) still calls `save_data()` with a changed file — diffed the real temp `league_data.json` before/after an immediate `POST /api/enrich-all` re-run: only `sources.{budget,gross,imdb,rt_crit}.at` timestamps changed (values identical). This does **not** violate SC2 (literally about API-call count, which stays 0) or SC3 (field *values* are provably unchanged), so it is not a must-have FAILURE — but it is the same bug class already identified and half-fixed in this phase, left unfixed in 4/5 of the affected fields. | WARNING | Every real-world `POST /api/enrich-all` call after the first rewrites `league_data.json` (git-diff noise on every re-run if the file is committed) and reports a misleading `fields_updated` count for a call that changed no actual data. **Suggested fix:** port the same `entry.get(field) == value and provenance.get_source(entry, field)` no-op check from `compute_roi` into `apply_fetched`. |
| `README.md` ("Enrichment does not change the standings") + `frontend/src/components/PlayerCard.jsx:31` | — | **Finding B — documentation slightly overclaims.** README states "your rankings will look identical after a run." Verified true for `rank` and `total` (both stable — confirmed by direct before/after leaderboard diff). However, `compute_leaderboard`'s `rounds_played` counter (pre-existing, untouched by Phase 2 — `git log` shows `storage.py` last touched at the initial commit) increments whenever a row's `imdb` is non-null, and is rendered in the exact same UI line as rank (`PlayerCard.jsx:31`: `"{rank} OF {n} · {rounds_played} ROUNDS"`). In the **real, current** `league_data.json`, 14/30 rows have `imdb: null` across 5 owners (Andrew, Evan, Jaq, Liam, Mark) — the first real enrichment run with live keys will visibly change the "ROUNDS" count for those owners, right next to their unchanged rank. | WARNING | Not a Phase 2 regression (the coupling is Phase-1-era, pre-existing code Phase 2 never touched), and the core claim (rank/total stability) is true. But a user could reasonably read "rankings will look identical" as covering the whole summary line. **Suggested fix:** either narrow the README wording ("your rank and total will look identical; rounds-played counts may update") or accept as-is via a documented decision. |
| `README.md` "Running locally" section | — | Stale `pip install -r requirements.txt` instruction (no `pip` in this repo, `uv`-only) | INFO | Self-disclosed by the phase itself in `.planning/phases/02-live-api-enrichment/deferred-items.md`; explicitly out of this plan's task scope (only "Auto-fetching data"/"Editing scores"/"Running the tests" sections were in scope). No later phase exists in ROADMAP.md to defer this to (Phase 2 is the last phase), so it remains an open, self-tracked, non-blocking item. |

### Human Verification Required

### 1. Live OMDb/TMDB integration with real keys

**Test:** Configure real `OMDB_API_KEY`/`TMDB_API_KEY` in `backend/.env` and run `POST /api/enrich-all?max_calls=10` (or the single-entry endpoint) against a few real movies, including at least one recent/low-budget title.
**Expected:** Real responses parse cleanly into `imdb`/`rt_crit`/`budget`/`gross`/`imdb_id`/`release_date` with no exceptions; a deliberately-wrong key produces a 502 with the key redacted in the body.
**Why human:** All 198 automated tests use `httpx.MockTransport` or monkeypatched functions by design (correctly — no secrets needed in CI, no quota burned). The exact field-name assumptions in `parse_omdb_payload()` and `tmdb.fetch_movie_financials()` have never been exercised against a real response body from either live provider in this verification pass, and no real keys were available in this environment to close that loop. This is squarely "external service integration," which always needs human confirmation.

## Gaps Summary

No ROADMAP success criterion, PLAN.md must-have, or REQUIREMENTS.md item failed. All 5 success criteria and all 3 non-goals were independently verified against the running code (not SUMMARY.md claims) using two from-scratch adversarial test scripts covering fill-from-empty, per-field no-clobber (including an unrecorded-but-populated fail-closed case beyond `roi`), force override, cache dedup, call-cap enforcement, HTTP-boundary clamping, PUT forgery-resistance, and — specifically requested — a critical review of the `c071ca1` `compute_roi` no-op-guard fix. That fix is correct and introduces no regression: brand-new `roi` values still get written, `force` still overrides, and — the specific risk flagged for review — a stale/wrong `roi` still gets corrected (the guard only suppresses a write when the freshly-computed value is identical to what's already stored AND a provenance record already exists).

Two non-blocking findings surfaced during this deeper pass, both reproducible and both outside the literal wording of any must-have:

- **Finding A:** the exact bug class fixed for `roi` at `c071ca1` still exists, unfixed, in `apply_fetched()` — the function responsible for `imdb`/`rt_crit`/`budget`/`gross`. A cache-hit-only repeat run (genuinely zero API calls, satisfying SC2 literally) still rewrites `league_data.json` with fresh provenance timestamps for every previously-fetched field. Recommended: port the same no-op guard.
- **Finding B:** README's "rankings will look identical" claim is true for rank/total but not for the adjacent `rounds_played` display, which will visibly change for 5 of the league's owners on their first real enrichment run. This is an emergent interaction with pre-existing (Phase-1-era) `storage.py` logic, not something Phase 2 introduced or was scoped to fix.

Status is `human_needed` rather than `passed` because live-provider integration (real OMDb/TMDB response parsing) has not been exercised by any test in this phase or this verification pass — appropriately so, since that would require real credentials this environment does not have.

---

*Verified: 2026-08-20T02:12:15Z*
*Verifier: Claude (gsd-verifier)*

---

## Post-verification resolution (orchestrator)

**Finding A — RESOLVED** at the commit following this report. The no-op guard was ported
from `enrichment.compute_roi` into `provenance.apply_fetched`, closing the same bug class
for `imdb`/`rt_crit`/`budget`/`gross`. Reproduced the reported scenario against the fix
with stubbed providers: run 1 = 2 calls / 5 fields updated; run 2 = 0 calls / 0 updates,
data byte-identical. New values and `force=True` still write. Regression test added
(`test_apply_fetched_is_a_noop_when_the_value_is_unchanged`). Suite: 199 passing.

**Finding B — ACKNOWLEDGED, not changed.** `rounds_played` shifting when a null `imdb`
is filled is a pre-existing `storage.py` coupling from Phase 1, outside this phase's scope.
Left for a future phase alongside `compute_movie_scores()`.

**Human verification still outstanding:** live OMDb/TMDB responses have never been
exercised — no API keys exist in this environment. Field-name assumptions in
`parse_omdb_payload()` and `tmdb.fetch_movie_financials()` remain unproven against real
response bodies.

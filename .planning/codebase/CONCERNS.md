# Codebase Concerns

**Analysis Date:** 2026-07-08

---

## Overall Health Rating: 5/10

The codebase is clean, readable, and appropriately scoped for a small friend-group app. However, it has several structural issues that would cause real problems if deployed publicly or expanded: no authentication on mutating endpoints, a flat-file persistence model with only a process-scoped lock, no scoring formula logic (all scores are manual imports), two permanently stubbed services, and zero test coverage. The foundations are honest about their limitations but those limitations are significant.

---

## Security Concerns

### No Authentication on Write Endpoints

**Risk:** Any user who can reach the backend can overwrite any owner's movie scores.
**Files:** `backend/app/main.py` lines 47–55 (`update_movie`), lines 58–73 (`enrich_movie`)
**Detail:** `PUT /api/movies/{owner}/{round_number}` and `POST /api/movies/{owner}/{round_number}/enrich` require no token, session, or shared secret. The Pydantic `Movie` body validates field types but nothing stops an anonymous caller from zeroing out another owner's scores or inflating their own. Relevant only once the backend is accessible beyond localhost, but the README explicitly describes deploying to Fly.io/Render.
**Fix approach:** Add a simple shared-secret header check (an `X-API-Key` FastAPI dependency) for all mutating routes before deployment.

### Wildcard CORS Origin

**Risk:** Any website can make credentialed cross-origin requests to the API.
**Files:** `backend/app/main.py` lines 10–15
**Detail:** `allow_origins=["*"]` is a commented placeholder — the comment reads "tighten this once you have a real deployed frontend origin" — but there is no mechanism to enforce that tightening happens before deployment. In its current state, once the backend is on a public URL, any page on the internet can call the write endpoints.
**Fix approach:** Drive the allowed origin from an environment variable (`CORS_ORIGIN`) with no default; the server should refuse to start if it is unset.

### TMDB API Key Exposed in HTTP Query String

**Risk:** API key leaks into server access logs and network intermediary logs.
**Files:** `backend/app/services/tmdb.py` lines 32, 42
**Detail:** Both TMDB HTTP calls pass the key as a query parameter (`params = {"api_key": key, ...}`). Uvicorn logs full request URLs by default. Any log-aggregation system will store the key in plaintext. TMDB also supports Bearer token auth (`Authorization: Bearer <read_access_token>`) which does not appear in URLs.
**Fix approach:** Switch to TMDB's v4 read-access token via the `Authorization` header. Replace `params={"api_key": key}` with `headers={"Authorization": f"Bearer {key}"}` and remove the key from params.

### PUT Body Owner Field Not Validated Against URL Parameter

**Risk:** A caller can supply a `Movie` body where `owner` differs from the URL `{owner}`, resulting in the stored record having a mismatched owner field.
**Files:** `backend/app/main.py` lines 47–55
**Detail:** `update_movie` locates the record by `owner` and `round_number` from the URL path, then replaces it with `movie.model_dump()` from the body verbatim. If the body contains `"owner": "SomeoneElse"`, the stored JSON will contain a movie entry whose `owner` field no longer matches the URL key used to find it, silently corrupting the data.
**Fix approach:** After `data["movies"][i] = movie.model_dump()`, assert (or explicitly overwrite) `data["movies"][i]["owner"] == owner` and `data["movies"][i]["round"] == round_number`.

---

## Performance Risks

### JSON File Read on Every Request

**Risk:** Contention and slow response time under concurrent load; data races on multi-worker deployments.
**Files:** `backend/app/storage.py` lines 9–18
**Detail:** Every API call — including the read-only `/api/leaderboard` and `/api/owners/{owner}` — calls `load_data()`, which opens and fully parses the JSON file under a `threading.Lock`. With one uvicorn worker this serialises all requests. With `--workers N` (the normal production flag), each worker has its own `_lock` instance, making the lock useless — concurrent writes from different workers can interleave and corrupt the JSON file.
**Fix approach:** For this scale a simple in-process cache with a short TTL (e.g., 5 seconds, invalidated on write) eliminates most redundant reads. For true multi-worker safety, either restrict to one worker or switch storage to SQLite (which handles concurrency correctly and requires minimal code change).

### Linear Scan for Every Lookup

**Risk:** O(n) movie list scan on every owner lookup, round lookup, and update.
**Files:** `backend/app/main.py` lines 29, 36, 50–54, 62–72; `backend/app/storage.py` lines 28–35
**Detail:** All endpoints iterate the full `data["movies"]` list. At 30 entries this is fine. If rounds or owners grow, or if the leaderboard computation is called frequently, this will be wasteful. `compute_leaderboard` does a full scan too.
**Fix approach:** Not urgent at current scale. If data grows, index movies by `(owner, round)` after loading. SQLite with a proper index would solve this permanently.

### Google Fonts Loaded from External CDN

**Risk:** External network dependency on every page load; blocks render if Google Fonts is slow.
**Files:** `frontend/index.html` lines 8–16
**Detail:** Three font families (Bebas Neue, Inter, IBM Plex Mono) are loaded from `fonts.googleapis.com` with preconnect hints. This is a third-party dependency that adds a network round-trip and can block text rendering. It also sends user IP addresses to Google.
**Fix approach:** Self-host fonts using a tool like `fontsource` npm packages (`@fontsource/inter`, etc.) and import them in `styles.css`. Eliminates the external dependency and the privacy concern.

---

## Technical Debt

### Scoring Formulas Not Implemented — All Scores Are Manual

**Issue:** The application stores and displays scores but does not compute them. Every `rating_score`, `financial_score`, `penalties`, `watch_points`, and `total` value must be calculated externally (e.g., in a spreadsheet) and entered by hand via `PUT /api/movies/{owner}/{round_number}`.
**Files:** `backend/app/storage.py` lines 22–41, `backend/app/models.py` lines 18–23, `README.md` lines 45–48
**Detail:** `compute_leaderboard` in `storage.py` aggregates pre-computed sub-scores but performs no actual scoring logic. The README explicitly acknowledges this: "there's no scoring-formula code here yet — your rating/financial/penalty/watch-point numbers are stored as-is from your spreadsheet". The penalty logic (`-10` for RT Critics < 50%, `-10` for Letterboxd < 2.5, `-10/-15` for not recouping budget) is visible in `league_data.json` penalty notes but not in code.
**Fix approach:** Implement `score_movie(movie: dict) -> dict` in `storage.py` that derives `rating_score`, `financial_score`, `penalties`, `watch_points`, and `total` from raw fields (`imdb`, `letterboxd`, `rt_crit`, `rt_aud`, `budget`, `gross`, `who_watched`). Call it on every `save_data`. This removes the spreadsheet dependency and makes the app the source of truth.

### `critic_scores_stub.py` Is Imported but Never Called

**Issue:** Dead import consuming startup time and creating a misleading dependency.
**Files:** `backend/app/main.py` line 6, `backend/app/services/critic_scores_stub.py`
**Detail:** `from .services import tmdb, critic_scores_stub` imports the stub module at startup. Neither `critic_scores_stub.fetch_rt_scores` nor `critic_scores_stub.fetch_letterboxd_rating` is called anywhere in `main.py` or any other file. The enrich endpoint only calls `tmdb.fetch_movie_financials`. The stub exists to define the interface shape for future scraping but is not wired into any endpoint.
**Fix approach:** Either wire `fetch_rt_scores` and `fetch_letterboxd_rating` into the enrich endpoint (returning the results even if `None`), or remove the import until scraping is implemented to avoid misleading readers into thinking RT/Letterboxd enrichment already runs.

### `bo_rank` and `awards` Fields Are Entirely Unused

**Issue:** Two model fields are `null` across all 30 records with no UI or logic that reads them.
**Files:** `backend/app/models.py` lines 15–16, `backend/data/league_data.json` (all 30 entries)
**Detail:** Every movie entry has `"bo_rank": null` and `"awards": null`. The frontend (`OwnerDetail.jsx`, `Leaderboard.jsx`) does not display them. No scoring logic references them. They represent intended features that were never built.
**Fix approach:** Either implement box-office rank scoring and awards scoring, or remove the fields from the model and JSON until they are needed.

### `roi` Field Computed Outside the App

**Issue:** Like the score fields, `roi` is calculated manually and stored, not derived from `gross / budget` in code.
**Files:** `backend/app/models.py` line 13, `backend/data/league_data.json`
**Detail:** Some entries have `roi` values (e.g., `4.653` for Scream 7) while others with non-null `budget` and `gross` have `null` roi. This inconsistency means the stored data can be internally contradictory. ROI is trivially derivable: `gross / budget`.
**Fix approach:** Remove `roi` from the model as a stored field; compute it on-the-fly as a derived property or add it in the serialisation layer.

### No Dependency Lockfile

**Issue:** Builds are not reproducible; a `pip install -r requirements.txt` with unpinned transitive dependencies can silently install different versions.
**Files:** `backend/requirements.txt` (no lockfile present)
**Detail:** `requirements.txt` pins direct dependencies (fastapi, uvicorn, httpx, pydantic) but there is no `poetry.lock`, `Pipfile.lock`, or `pip-compile`-generated lockfile for transitive dependencies. The npm side also has no `package-lock.json` committed.
**Fix approach:** Run `pip-compile requirements.txt > requirements.lock` and commit it. For npm, commit `package-lock.json`.

---

## Missing Features That Look Incomplete

### Enrich Endpoint Silently Skips RT and Letterboxd

**Issue:** The `/enrich` endpoint is documented as auto-filling data but only fills budget and gross. It silently does nothing for `rt_crit`, `rt_aud`, `letterboxd`, and `imdb`.
**Files:** `backend/app/main.py` lines 58–73
**Detail:** The endpoint name and docstring imply full enrichment. The stub `fetch_rt_scores` and `fetch_letterboxd_rating` exist and have the right signatures but are never called. A user hitting `/enrich` expecting IMDb or RT scores to be filled will get a response that looks successful (`tmdb_match: true`) but leaves those fields unchanged.
**Fix approach:** Either update the docstring to clearly state only budget/gross are populated, or call the stub functions and merge their results (they return `None` now but will be correct once implemented).

### No Add-Owner or Add-Round Endpoint

**Issue:** There is no way to add a new owner or a new round via the API. These operations require direct JSON file edits.
**Files:** `backend/app/main.py` (no POST /api/owners or POST /api/rounds endpoints)
**Detail:** The `owners` list and initial `movies` entries can only be modified by editing `backend/data/league_data.json` by hand. The README does not mention this limitation.

### No Frontend Write UI

**Issue:** All data entry requires direct API calls (curl, Postman, etc.) or direct JSON edits. There is no form, admin panel, or inline edit UI in the frontend.
**Files:** `frontend/src/components/OwnerDetail.jsx`, `frontend/src/components/Leaderboard.jsx`
**Detail:** The PUT and POST enrich endpoints exist but the frontend only exposes GET functionality. Score entry, movie assignment, and enrichment all require out-of-band tooling.

---

## Error Handling Gaps

### Owner Toggle in Leaderboard Has No Error Handling

**Issue:** If the `GET /api/owners/{owner}` call fails (network error, backend down after initial load), the expanded panel silently stays empty with only "Loading rounds..." shown permanently.
**Files:** `frontend/src/components/Leaderboard.jsx` lines 15–25
**Detail:** The `toggle` function calls `api.owner(owner)` with no `.catch()`. An uncaught promise rejection in an async event handler does not trigger React's error boundary and will surface only in the browser console. The user sees the "Loading rounds..." state indefinitely.
**Fix approach:** Add try/catch in `toggle` and set per-owner error state; display an error message inside the expanded panel.

### TMDB Network Errors Propagate as Unhandled 500s

**Issue:** If TMDB is unreachable or returns a non-2xx status, `raise_for_status()` throws an `httpx.HTTPStatusError` that FastAPI catches as an unhandled exception and returns a generic 500.
**Files:** `backend/app/services/tmdb.py` lines 36, 43; `backend/app/main.py` lines 58–73
**Detail:** There is no try/except around the TMDB HTTP calls. A TMDB outage, rate limit (HTTP 429), or invalid API key (HTTP 401) results in an unhelpful 500 response to the caller rather than a descriptive error.
**Fix approach:** Wrap the `httpx` calls in `fetch_movie_financials` in a `try/except httpx.HTTPError` block and return `None` (with optional logging) on failure, allowing the enrich endpoint to return `{"tmdb_match": false}` gracefully.

### `compute_leaderboard` Crashes on Data Inconsistency

**Issue:** If a movie entry references an owner not in `data["owners"]`, the function raises an unhandled `KeyError`.
**Files:** `backend/app/storage.py` line 29 (`row = board[m["owner"]]`)
**Detail:** The board dict is built from `data["owners"]`. If `data["movies"]` contains an entry whose `owner` value was edited into the JSON directly and does not match any listed owner, the leaderboard endpoint returns a 500. There is no validation at load time.
**Fix approach:** Add a guard: `if m["owner"] not in board: continue` (or log a warning). Better: validate data integrity in `load_data()`.

### `load_data` Does Not Handle Missing or Corrupt File

**Issue:** If `league_data.json` is missing or contains invalid JSON, `load_data()` raises an unhandled exception that crashes every endpoint with a 500.
**Files:** `backend/app/storage.py` lines 9–12
**Detail:** No try/except around `open()` or `json.load()`. A corrupted write (e.g., from a crash mid-`save_data`) will take the entire API down.
**Fix approach:** Implement atomic writes in `save_data` (write to a `.tmp` file, then `os.replace()`) to prevent partial writes. Add a try/except in `load_data` that returns a safe default or raises a descriptive HTTPException.

---

## Scalability Concerns

### Single JSON File as Database

**Issue:** The entire data store is a single JSON file on disk. This is the most fundamental scaling constraint.
**Files:** `backend/app/storage.py`, `backend/data/league_data.json`
**Detail:** Concurrent writes require process-level locking (which breaks across uvicorn workers), there is no transaction support, there is no query capability, and any sufficiently large concurrent read load will cause lock contention. The file is currently 39 lines; if the league runs for years with many rounds and owners this will grow but remain manageable. The real risk is the multi-worker write-corruption issue if deployed without careful configuration.
**Fix approach:** For this scale, SQLite is a drop-in replacement that handles concurrency correctly. FastAPI + SQLite with `aiosqlite` is a minimal change.

### No Caching Layer

**Issue:** The leaderboard is recomputed from the full JSON file on every request.
**Files:** `backend/app/storage.py` lines 21–41; `backend/app/main.py` lines 18–21
**Detail:** `compute_leaderboard` reads and parses the file, iterates all movies, sorts results, and re-ranks on every GET. For a 5-owner, 6-round dataset this is trivially fast. It is not architected to scale and there is no response caching (HTTP Cache-Control headers, ETags, or in-process memoisation).

---

## Dependencies at Risk

### Backend Dependencies Are Not Current (as of 2026-07-08)

**Files:** `backend/requirements.txt`
**Detail:**
- `fastapi==0.115.0` — Released September 2024. Current stable is 0.115.x / 0.116.x range. Not critically outdated but a minor version behind.
- `uvicorn[standard]==0.30.6` — Released mid-2024. Minor versions released since.
- `httpx==0.27.2` — Released mid-2024.
- `pydantic==2.9.2` — Released late 2024. Patch versions available.

None of these have known critical CVEs at time of analysis, but all are 12–18 months old. Because there is no lockfile and no automated update process, transitive dependency drift is invisible.

### Frontend Dependencies Are Pinned to Caret Ranges, No Lockfile

**Files:** `frontend/package.json`
**Detail:** `"react": "^18.3.1"` and `"vite": "^5.4.1"` use caret ranges. Without a committed `package-lock.json`, `npm install` resolves dependencies freshly each time, which can pull in breaking minor updates. React 19 is a major version break that caret will not cross, but Vite 6 was released and `^5.4.1` would not upgrade to it — though patch/minor updates within v5 could still introduce regressions silently.

---

## TODOs and Informal Notes in Code

| File | Line | Note |
|------|------|-------|
| `backend/app/main.py` | 12 | `# tighten this once you have a real deployed frontend origin` — CORS wildcard left as a reminder but no enforcement |
| `backend/app/services/tmdb.py` | 52 | `"imdb_id": None, # available via /movie/{id}/external_ids if needed` — IMDb ID lookup is stubbed out; the field is always `None` in every enrichment response |
| `backend/app/services/critic_scores_stub.py` | 3 | "a stub so the rest of the pipeline has a consistent shape to call into whenever scraping...gets wired up" — scraping is not wired up and the stub is not called |
| `README.md` | 45–48 | "there's no scoring-formula code here yet — wire up the formulas in `app/storage.py` if you want them computed instead of entered by hand" — this is the single largest functional gap |

---

## Test Coverage Gaps

### Zero Tests Exist

**Issue:** There are no unit tests, integration tests, or end-to-end tests anywhere in the project.
**Files:** No test files found in `backend/` or `frontend/`
**Detail:** No pytest setup, no Vitest/Jest config, no test runner scripts. The following logic is entirely untested:
- `compute_leaderboard` aggregation and ranking (`backend/app/storage.py`)
- `update_movie` owner/body field mismatch behaviour
- `enrich_movie` TMDB integration and partial enrichment
- `load_data` / `save_data` file I/O and lock behaviour
- All frontend component rendering and toggle state

**Priority:** High for `compute_leaderboard` (it is the core business logic) and `update_movie` (it mutates persistent state).
**Fix approach:** Add `pytest` and `pytest-asyncio` to a `requirements-dev.txt`. Write tests for `compute_leaderboard` with fixture data covering edge cases (unknown owner, all-null movies, tie-break on totals). Add `httpx` mock tests for the enrich endpoint.

---

*Concerns audit: 2026-07-08*

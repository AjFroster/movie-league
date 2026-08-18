# Movie League — Code Review

**Date:** 2026-07-08  
**Depth:** standard  
**Files reviewed:** 13

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 6 |
| 🟠 Warning | 9 |
| 🔵 Info | 5 |
| **Total** | **20** |

---

## Critical Findings

**backend/app/main.py:52: 🔴 Critical: `update_movie` stores caller-supplied `owner` and `round`, allowing silent data corruption. If the PUT body contains `"owner": "AnotherPerson"` or `"round": 99`, those values are written verbatim into `league_data.json`. The URL parameters (`owner`, `round_number`) are used only to *find* the existing record — the replacement comes entirely from `movie.model_dump()`. Fix: after writing, force the correct values: `data["movies"][i]["owner"] = owner; data["movies"][i]["round"] = round_number` before calling `save_data`.**

`backend/app/main.py:52: 🔴 Critical: body owner/round not overwritten with URL params before save — caller can silently corrupt any stored record's identity fields.`

---

**backend/app/main.py:10-14: 🔴 Critical: CORS wildcard `allow_origins=["*"]` combined with unauthenticated write endpoints means any web page on the internet can issue PUT/POST requests to mutate league data once the backend is on a public URL. The inline comment acknowledges this but there is no enforcement gate. Fix: read allowed origin from an environment variable and raise a startup error if it is unset; e.g., `allow_origins=[os.environ["CORS_ORIGIN"]]` where missing key aborts boot.**

`backend/app/main.py:12: 🔴 Critical: allow_origins=["*"] with no authentication on write endpoints — any origin can overwrite scores once backend is publicly reachable.`

---

**backend/app/services/tmdb.py:32,42: 🔴 Critical: TMDB API key is appended as a URL query parameter (`params={"api_key": key, ...}`). Uvicorn logs full request URLs to stdout by default, so the key is written to every access log line and any downstream log aggregator. Fix: switch to the Bearer token flow — remove `api_key` from params and add `headers={"Authorization": f"Bearer {key}"}` to the `AsyncClient` calls. TMDB v3 accepts Bearer tokens for all endpoints.**

`backend/app/services/tmdb.py:32: 🔴 Critical: TMDB API key sent as a URL query parameter — key leaks into server access logs on every enrichment call.`

---

**backend/app/storage.py:15-18: 🔴 Critical: `save_data` writes the JSON file non-atomically. If the process is killed between `open(DATA_PATH, "w")` truncating the file and `json.dump` completing the write, the file is left empty or half-written and every subsequent request returns a 500. Fix: write to a sibling temp file then use `os.replace()` for an atomic swap: `tmp = DATA_PATH.with_suffix(".tmp"); json.dump(data, tmp.open("w"), indent=2); os.replace(tmp, DATA_PATH)`.**

`backend/app/storage.py:15-18: 🔴 Critical: non-atomic file write — a crash mid-write permanently corrupts league_data.json, taking down every endpoint.`

---

**backend/app/storage.py:9-12: 🔴 Critical: `load_data` has no error handling. A missing file, an empty file (from a prior crashed write), or invalid JSON raises an unhandled exception that FastAPI catches as a 500. Every endpoint depends on this function. Fix: wrap the `open`/`json.load` in `try/except (FileNotFoundError, json.JSONDecodeError) as e` and raise `HTTPException(status_code=503, detail=f"Data store unavailable: {e}")`.**

`backend/app/storage.py:9-12: 🔴 Critical: no error handling on file open/parse — missing or corrupt league_data.json crashes every API endpoint with an opaque 500.`

---

**backend/app/storage.py:29: 🔴 Critical: `compute_leaderboard` performs `board[m["owner"]]` without checking whether `m["owner"]` is a key in `board`. `board` is built from `data["owners"]`; if a movie record has an owner value that was hand-edited into the JSON and does not appear in `data["owners"]`, this raises `KeyError` and the `/api/leaderboard` endpoint returns a 500. Fix: `row = board.get(m["owner"]); if row is None: continue` (or log a warning).**

`backend/app/storage.py:29: 🔴 Critical: unguarded dict access board[m["owner"]] — a single orphaned movie entry crashes the leaderboard endpoint with KeyError.`

---

## Warning Findings

**backend/app/main.py:6: 🟠 Warning: `critic_scores_stub` is imported at module level but neither `fetch_rt_scores` nor `fetch_letterboxd_rating` is called anywhere in the codebase. The import is dead weight and misleads readers into thinking RT/Letterboxd enrichment is already wired up. Fix: remove the import (`from .services import tmdb, critic_scores_stub` → `from .services import tmdb`) until the stub is actually called.**

`backend/app/main.py:6: 🟠 Warning: critic_scores_stub imported but never called — dead import that signals false functionality.`

---

**backend/app/main.py:58-73: 🟠 Warning: `enrich_movie` calls `tmdb.fetch_movie_financials` with no try/except. A TMDB outage, rate-limit (HTTP 429), invalid API key (HTTP 401), or network timeout causes `raise_for_status()` in tmdb.py to throw `httpx.HTTPStatusError`, which FastAPI surfaces as an unhandled 500 with no diagnostic detail. Fix: wrap the `await tmdb.fetch_movie_financials(...)` call in `try/except httpx.HTTPError as e` and raise `HTTPException(status_code=502, detail=str(e))`.**

`backend/app/main.py:64: 🟠 Warning: TMDB call in enrich_movie has no exception handling — any TMDB error returns an opaque 500 instead of a descriptive 502.`

---

**backend/app/main.py:47-55: 🟠 Warning: `update_movie` succeeds silently when the movie is not found only if the loop completes without the `if` branch ever matching — that path correctly falls through to `raise HTTPException(404)`. However, if a match is found and `save_data` raises (e.g., disk full, permission denied), the exception is unhandled and the caller receives a 500 with no indication of whether the write succeeded or not. Fix: wrap `save_data(data)` in a try/except and raise `HTTPException(status_code=507, detail="Failed to persist update")`.**

`backend/app/main.py:53: 🟠 Warning: save_data exceptions in update_movie are unhandled — a failed write is indistinguishable from a server error to the caller.`

---

**backend/app/services/tmdb.py:46-47: 🟠 Warning: `budget = d.get("budget") or 0` silences a legitimate `0` budget returned by TMDB (some films have `"budget": 0` meaning "unreported", not literally zero). The same applies to `revenue`. This is fine for this use case but the conversion to `None` in the return dict (`round(budget / 1_000_000, 2) if budget else None`) means a film with a real budget that TMDB happens to store as `0` will be indistinguishable from one with no data. Fix: use explicit `None` check: `budget = d.get("budget"); revenue = d.get("revenue")` and then `budget_millions = round(budget / 1_000_000, 2) if budget else None`.**

`backend/app/services/tmdb.py:46-47: 🟠 Warning: "or 0" coercion conflates TMDB's "budget unreported" (0) with a true zero — a film budgeted at $0 reported by TMDB is stored as None, not 0.`

---

**frontend/src/components/Leaderboard.jsx:15-25: 🟠 Warning: the `toggle` async function is called from an event handler with no `.catch()` and no try/catch inside the function. If `api.owner(owner)` rejects (network error, backend 404, etc.), the rejected promise is silently swallowed. `expanded` is already set to the new owner (line 20) before the fetch, so the UI shows an empty `OwnerDetail` with "Loading rounds…" indefinitely. Fix:**
```jsx
async function toggle(owner) {
  if (expanded === owner) { setExpanded(null); return }
  setExpanded(owner)
  if (!ownerMovies[owner]) {
    try {
      const data = await api.owner(owner)
      setOwnerMovies((prev) => ({ ...prev, [owner]: data.movies }))
    } catch (e) {
      setExpanded(null)           // collapse back
      // optionally surface error state per-owner
    }
  }
}
```

`frontend/src/components/Leaderboard.jsx:22: 🟠 Warning: api.owner() called with no error handling in toggle — a network failure leaves the panel stuck on "Loading rounds…" with no user feedback.`

---

**frontend/src/components/OwnerDetail.jsx:13: 🟠 Warning: `m.total` is rendered as-is when `m.imdb !== null`. Because `total` is a stored `float`, a value like `12.0` displays as `12` (JS coerces it) but a value like `-18` already has the right sign. The positive-total branch does `+${m.total}` which works for integers but for a stored float `46.5` would render as `+46.5` — acceptable. The real issue is `m.total === 0` falls into the else branch and renders as `0` with no prefix, which is fine. No code change needed for correctness, but consider `toFixed(1)` for visual consistency across all score displays.**

`frontend/src/components/OwnerDetail.jsx:13: 🟠 Warning: m.total rendered without toFixed — float scores like 46.5 display inconsistently versus integer-valued totals; add .toFixed(1) or a shared formatter.`

---

**backend/app/storage.py:5: 🟠 Warning: `DATA_PATH` is computed at import time relative to `__file__`. This is correct in the standard uvicorn launch pattern, but if the module is ever imported from a test or a script in a different working directory, the path resolution is still correct because it uses `Path(__file__).resolve()`. However, there is no validation that the file or its parent directory actually exists at startup. Fix: add a startup check (FastAPI `@app.on_event("startup")`) that verifies `DATA_PATH.exists()` and logs a warning if not.**

`backend/app/storage.py:5: 🟠 Warning: no startup validation that DATA_PATH exists — the first request reveals the missing file as a 500, not a clear startup error.`

---

**backend/app/main.py:12-14: 🟠 Warning: `allow_credentials` is not explicitly set. With `allow_origins=["*"]`, browsers will not send cookies or `Authorization` headers cross-origin anyway (the wildcard origin blocks credentialed requests per CORS spec). But if the origin is later tightened to a specific domain, forgetting to also add `allow_credentials=True` will silently break any future authentication mechanism. Fix: explicitly set `allow_credentials=False` now so the intent is clear, and add a comment that it must change to `True` alongside origin-tightening if cookies/auth are added.**

`backend/app/main.py:10-14: 🟠 Warning: allow_credentials not set explicitly — future auth implementation will require both origin tightening and allow_credentials=True; the current omission makes this easy to forget.`

---

## Info Findings

**backend/app/models.py:15-16: 🔵 Info: `bo_rank` and `awards` fields exist in the Pydantic model and are `null` in all 30 data records. No endpoint, frontend component, or scoring logic reads or writes these fields. They are dead schema weight until implemented. Fix: remove them from `Movie` and the JSON records, or add a comment marking them as planned.**

`backend/app/models.py:15-16: 🔵 Info: bo_rank and awards fields defined in model and JSON but unused by any code or UI — dead schema fields.`

---

**backend/app/models.py:17: 🔵 Info: `who_watched: list[str] = []` uses a mutable default. Pydantic v2 handles this correctly (it creates a new list per instance), unlike plain Python dataclasses, so this is not a runtime bug. However, it is a well-known Python anti-pattern and readers unfamiliar with Pydantic v2 may flag it. Fix: use `who_watched: list[str] = Field(default_factory=list)` to make the intent explicit.**

`backend/app/models.py:17: 🔵 Info: mutable default list[] for who_watched — safe in Pydantic v2 but use Field(default_factory=list) to be explicit.`

---

**backend/app/services/tmdb.py:52: 🔵 Info: `"imdb_id": None` is hard-coded in the return dict with a comment noting it could be fetched via `/movie/{id}/external_ids`. Every enriched movie therefore has `imdb_id: null` in its enrichment response. This is a documented stub; either remove the key from the response to avoid confusion or fetch it as the comment suggests.**

`backend/app/services/tmdb.py:52: 🔵 Info: imdb_id is always None in enrichment response — a caller inspecting the response will see a key that suggests data is present when it is always null.`

---

**frontend/src/components/Leaderboard.jsx:37: 🔵 Info: the `onKeyDown` handler calls `toggle(owner)` for both Enter and Space but does not call `e.preventDefault()`. Pressing Space on a focusable element with `role="button"` normally triggers the default browser scroll behaviour. Fix: add `e.preventDefault()` before calling `toggle(owner)` for the Space key.**

`frontend/src/components/Leaderboard.jsx:37: 🔵 Info: Space keydown on role="button" ticket rows does not call e.preventDefault() — pressing Space scrolls the page instead of (or in addition to) toggling the panel.`

---

**frontend/vite.config.js:9: 🔵 Info: the dev-server proxy target `http://localhost:8000` is hardcoded. If the backend port changes or a reviewer runs it on a different port, the proxy silently fails and all API calls return Vite's own 404. Fix: read the port from an environment variable or `.env` file: `target: process.env.VITE_API_URL ?? 'http://localhost:8000'`.**

`frontend/vite.config.js:9: 🔵 Info: backend proxy target is hardcoded to localhost:8000 — no way to override without editing the config file.`

---

## Overall Health Score: 4/10

The application is readable and structurally simple, which are genuine positives. However, six critical defects make it unsafe to deploy as-is:

- A non-atomic write can permanently destroy the data file.
- An unguarded dict access crashes the primary endpoint on malformed data.
- The API key leaks into server logs on every enrichment call.
- Caller-supplied body fields can silently corrupt stored record identity.
- No file-error handling means any I/O problem brings down every endpoint.
- Wildcard CORS on an unauthenticated write API is a public deployment blocker.

None of these require architectural changes — each is a 3-10 line fix. The codebase would reach a defensible 7/10 after addressing all Critical and Warning findings.

<!-- refreshed: 2026-07-08 -->
# Architecture

**Analysis Date:** 2026-07-08

## System Overview

```text
┌──────────────────────────────────────────────────────────────┐
│                    Browser (React SPA)                        │
│                  `frontend/src/`                              │
│                                                              │
│   App.jsx → Leaderboard.jsx → OwnerDetail.jsx               │
│                   │                                          │
│             api.js (fetch wrapper)                           │
└──────────────────────┬───────────────────────────────────────┘
                       │  HTTP /api/* (proxied by Vite dev server
                       │  or direct in production)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python)                         │
│              `backend/app/main.py`                           │
│                                                              │
│   GET /api/leaderboard                                       │
│   GET /api/owners/{owner}                                    │
│   GET /api/rounds/{n}                                        │
│   GET /api/movies                                            │
│   PUT /api/movies/{owner}/{round}                            │
│   POST /api/movies/{owner}/{round}/enrich                    │
└──────────┬───────────────────────┬───────────────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────┐    ┌──────────────────────────────────────┐
│  storage.py      │    │  services/                           │
│  (JSON R/W +     │    │  tmdb.py  →  TMDB API (external)    │
│  leaderboard     │    │  critic_scores_stub.py (no-op)       │
│  aggregation)    │    └──────────────────────────────────────┘
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  league_data.json│
│  `backend/data/` │
└──────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `App` | Root component; fetches leaderboard on mount; renders layout frame | `frontend/src/App.jsx` |
| `FilmStrip` | Purely decorative sprocket-strip element, no state | `frontend/src/App.jsx` |
| `Leaderboard` | Renders ranked ticket rows; owns expand/collapse state and lazy-loads per-owner detail | `frontend/src/components/Leaderboard.jsx` |
| `OwnerDetail` | Displays round-by-round movie rows for one owner | `frontend/src/components/OwnerDetail.jsx` |
| `api` object | Thin `fetch` wrapper; base path `/api`; throws on non-OK responses | `frontend/src/api.js` |
| `main.py` | FastAPI app; all route definitions; CORS middleware | `backend/app/main.py` |
| `storage.py` | File I/O with thread lock; `compute_leaderboard` aggregation logic | `backend/app/storage.py` |
| `models.py` | Pydantic `Movie` and `LeagueData` schemas | `backend/app/models.py` |
| `tmdb.py` | Async TMDB REST client; budget/gross enrichment | `backend/app/services/tmdb.py` |
| `critic_scores_stub.py` | Stub for future RT/Letterboxd scraping; always returns `None` | `backend/app/services/critic_scores_stub.py` |

## Pattern Overview

**Overall:** Thin REST API backed by a single JSON file, consumed by a client-rendered React SPA.

**Key Characteristics:**
- No database — `backend/data/league_data.json` is the sole persistent store
- All scoring fields (rating_score, financial_score, penalties, etc.) are stored as pre-computed values, not derived on read
- Frontend fetches only what it needs: leaderboard summary up front, per-owner detail on demand (lazy)
- No frontend routing library — the entire UI is a single page with inline expand/collapse
- No authentication — all endpoints are public

## Layers

**Frontend Presentation Layer:**
- Purpose: Render read-only league standings; allow drill-down per owner
- Location: `frontend/src/`
- Contains: React components, fetch abstraction, global CSS
- Depends on: Backend REST API via `/api` prefix
- Used by: End users in browser

**API Layer:**
- Purpose: Expose league data as JSON; validate writes with Pydantic; handle TMDB enrichment
- Location: `backend/app/main.py`
- Contains: FastAPI route handlers
- Depends on: `storage.py`, `models.py`, `services/`
- Used by: Frontend SPA

**Storage Layer:**
- Purpose: Serialize/deserialize the JSON data file; compute aggregated leaderboard totals
- Location: `backend/app/storage.py`
- Contains: `load_data`, `save_data`, `compute_leaderboard`
- Depends on: `backend/data/league_data.json`
- Used by: Route handlers in `main.py`

**Services Layer:**
- Purpose: Encapsulate calls to external APIs
- Location: `backend/app/services/`
- Contains: `tmdb.py` (live), `critic_scores_stub.py` (placeholder)
- Depends on: `TMDB_API_KEY` environment variable; `httpx` async client
- Used by: `POST /api/movies/{owner}/{round}/enrich` route

## Data Flow

### Primary Read Path (leaderboard page load)

1. Browser mounts `App`, `useEffect` fires → `api.leaderboard()` → `GET /api/leaderboard` (`frontend/src/App.jsx:20`)
2. FastAPI calls `load_data()` to read `league_data.json` then `compute_leaderboard(data)` (`backend/app/main.py:19-21`)
3. `compute_leaderboard` iterates all movie entries, accumulates per-owner totals, sorts by total descending, injects `rank` field (`backend/app/storage.py:22-41`)
4. JSON array of ranked owner objects returned to browser; `App` calls `setRows`, re-renders with `Leaderboard` component (`frontend/src/App.jsx:21`)

### Owner Drill-down Path (expand a ticket)

1. User clicks a ticket row → `Leaderboard.toggle(owner)` (`frontend/src/components/Leaderboard.jsx:15`)
2. If movies for that owner not yet cached: `api.owner(name)` → `GET /api/owners/{owner}` (`frontend/src/api.js:11`)
3. Backend filters `data["movies"]` to that owner, sorts by round, returns array (`backend/app/main.py:25-30`)
4. Result stored in `ownerMovies` dict keyed by name (client-side cache); `OwnerDetail` renders the round rows (`frontend/src/components/Leaderboard.jsx:22-24`)

### Enrichment Path (TMDB data fill)

1. Client (or manual curl) sends `POST /api/movies/{owner}/{round}/enrich` (`backend/app/main.py:58`)
2. Backend looks up the movie entry, calls `tmdb.fetch_movie_financials(title)` (`backend/app/services/tmdb.py:20`)
3. TMDB search → movie details fetch → budget/gross extracted and converted to millions
4. Matching entry updated in-memory and written back to `league_data.json` via `save_data` (`backend/app/main.py:69-71`)

### Write Path (manual score update)

1. `PUT /api/movies/{owner}/{round_number}` with full `Movie` JSON body (`backend/app/main.py:47`)
2. Pydantic validates incoming body against `Movie` model (`backend/app/models.py:4`)
3. Matching entry in `data["movies"]` replaced; `save_data` writes atomically under thread lock (`backend/app/storage.py:16-18`)

**State Management:**
- Frontend: local React state only. `App` holds `rows` (leaderboard array) and `error`. `Leaderboard` holds `expanded` (currently open owner name) and `ownerMovies` (dict of fetched detail arrays). No external state library.
- Backend: stateless per-request. Shared mutable state is the JSON file, protected by a `threading.Lock` in `storage.py`.

## Key Abstractions

**`Movie` Pydantic model:**
- Purpose: Canonical shape for a single round entry; used for both storage and API request validation
- Location: `backend/app/models.py`
- Pattern: Pydantic v2 `BaseModel`; all score fields default to `0` or `None` to represent "not yet entered"

**`compute_leaderboard` function:**
- Purpose: The only aggregation in the system — collapses per-movie rows into per-owner standings
- Location: `backend/app/storage.py:22`
- Pattern: Pure function over the loaded data dict; no side effects

**`api` object (frontend):**
- Purpose: Single point of contact between UI components and backend; encapsulates base URL and error handling
- Location: `frontend/src/api.js`
- Pattern: Plain object with async methods wrapping `fetch`

## Entry Points

**Frontend:**
- Location: `frontend/src/main.jsx`
- Triggers: Vite serves `frontend/index.html`; browser executes `<script type="module" src="/src/main.jsx">`
- Responsibilities: Creates React root, renders `<App />` in StrictMode

**Backend:**
- Location: `backend/app/main.py` (the `app` FastAPI instance)
- Triggers: `uvicorn app.main:app --reload --port 8000`
- Responsibilities: Registers all routes and CORS middleware

## Architectural Constraints

- **Threading:** Python backend is single-process; concurrency is handled by uvicorn's async event loop. Sync route handlers (all except `enrich`) are run in a thread pool by FastAPI. The `threading.Lock` in `storage.py` guards the JSON file against concurrent writes.
- **Global state:** `DATA_PATH` and `_lock` are module-level singletons in `backend/app/storage.py`. No other shared mutable state on the backend.
- **Scoring formulas:** Scores are NOT computed by the backend. `rating_score`, `financial_score`, `penalties`, and `watch_points` are stored values copied from a spreadsheet. The `total` field is likewise pre-computed. `compute_leaderboard` only sums stored values.
- **No authentication:** All API endpoints are unauthenticated. CORS is `allow_origins=["*"]`.
- **Circular imports:** None detected.

## Anti-Patterns

### Scores stored, not computed

**What happens:** `rating_score`, `financial_score`, `penalties`, `watch_points`, and `total` are stored verbatim in `league_data.json` and summed by `compute_leaderboard`. No formula lives in code.

**Why it's wrong:** Editing a raw score field (e.g., `imdb`) does not automatically update `total`. A `PUT` to update `imdb` requires manually recalculating and re-submitting all derived score fields, or the leaderboard shows stale totals.

**Do this instead:** Implement scoring formulas in `backend/app/storage.py` (or a new `backend/app/scoring.py`) so that `compute_leaderboard` (or a post-save hook) derives all score fields from the raw inputs (`imdb`, `letterboxd`, `rt_crit`, `rt_aud`, `budget`, `gross`, `roi`, `who_watched`).

### Wide-open CORS

**What happens:** `allow_origins=["*"]` in `backend/app/main.py:11` permits any origin.

**Why it's wrong:** Once the frontend is deployed to a fixed URL, any site can call the write endpoints (`PUT`, `POST`).

**Do this instead:** Set `allow_origins` to the exact deployed frontend origin (noted in the comment on line 11 itself).

## Error Handling

**Strategy:** Backend raises `HTTPException` for 404s; all other errors propagate as 500s. Frontend catches fetch errors and sets an `error` state that shows a single banner message.

**Patterns:**
- Backend: `raise HTTPException(status_code=404, detail="...")` in route handlers when owner/round/movie not found (`backend/app/main.py:28, 39, 55, 72`)
- Frontend: `.catch((e) => setError(e.message))` in `App.useEffect`; no per-component error handling beyond the loading state in `OwnerDetail`

## Cross-Cutting Concerns

**Logging:** None — no logging framework is configured on the backend. Uvicorn access logs go to stdout.
**Validation:** Pydantic v2 on write path only (`PUT /api/movies/...`). Read paths return raw dict data without re-validation.
**Authentication:** Not implemented.

---

*Architecture analysis: 2026-07-08*

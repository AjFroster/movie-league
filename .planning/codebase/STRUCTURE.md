# Codebase Structure

**Analysis Date:** 2026-07-08

## Directory Layout

```
movie-league/
├── backend/                    # Python FastAPI server
│   ├── app/                    # Application package
│   │   ├── __init__.py         # Empty package marker
│   │   ├── main.py             # FastAPI app instance + all route definitions
│   │   ├── models.py           # Pydantic data models (Movie, LeagueData)
│   │   ├── storage.py          # JSON file I/O and leaderboard aggregation
│   │   └── services/           # External API integrations
│   │       ├── __init__.py     # Empty package marker
│   │       ├── tmdb.py         # TMDB REST client (budget/gross enrichment)
│   │       └── critic_scores_stub.py  # Placeholder for RT/Letterboxd scraping
│   ├── data/
│   │   └── league_data.json    # Sole persistent data store (owners + movie entries)
│   └── requirements.txt        # Python dependencies
├── frontend/                   # React SPA (Vite)
│   ├── index.html              # HTML shell; mounts React root, loads Google Fonts
│   ├── package.json            # npm manifest and scripts
│   ├── vite.config.js          # Vite config: React plugin, dev proxy to :8000
│   └── src/
│       ├── main.jsx            # React entry point; createRoot + StrictMode wrapper
│       ├── App.jsx             # Root component: layout frame, leaderboard fetch
│       ├── api.js              # Fetch wrapper with /api base path
│       ├── styles.css          # Global CSS (design tokens, all component styles)
│       └── components/
│           ├── Leaderboard.jsx # Ranked ticket list; expand/collapse state
│           └── OwnerDetail.jsx # Per-owner round-by-round breakdown
├── .planning/
│   └── codebase/               # GSD codebase map documents
└── README.md                   # Project overview and run instructions
```

## Directory Purposes

**`backend/app/`:**
- Purpose: The entire Python application package
- Contains: Route handlers, data models, storage logic, service clients
- Key files: `main.py` (routes), `storage.py` (I/O + aggregation), `models.py` (schemas)

**`backend/app/services/`:**
- Purpose: Isolate calls to third-party APIs from route logic
- Contains: `tmdb.py` (live async HTTP client), `critic_scores_stub.py` (no-op stubs)
- Key note: Only `tmdb.py` is wired into a real route. `critic_scores_stub.py` is imported in `main.py` but its functions are never called from any route yet.

**`backend/data/`:**
- Purpose: Filesystem-based persistence; acts as the "database"
- Contains: `league_data.json` — the single source of truth for all league state
- Generated: No — manually curated, written to by `save_data()` on updates
- Committed: Yes — data is part of the repo

**`frontend/src/`:**
- Purpose: All React source code
- Contains: Entry point, root component, API client, component tree, styles
- Key files: `main.jsx` (mount), `App.jsx` (root), `api.js` (HTTP), `styles.css` (all styles)

**`frontend/src/components/`:**
- Purpose: Reusable UI components below `App`
- Contains: `Leaderboard.jsx`, `OwnerDetail.jsx`
- Key note: All styling is in `styles.css` — no CSS modules, no styled-components

## Key File Locations

**Entry Points:**
- `frontend/src/main.jsx`: React mount point — `ReactDOM.createRoot` on `#root`
- `frontend/index.html`: HTML shell loaded by Vite; references `src/main.jsx`
- `backend/app/main.py`: FastAPI `app` object; run via `uvicorn app.main:app`

**Configuration:**
- `frontend/vite.config.js`: Vite plugin setup and dev-server proxy (`/api` → `http://localhost:8000`)
- `frontend/package.json`: npm scripts (`dev`, `build`, `preview`), React 18 + Vite dependencies
- `backend/requirements.txt`: Python dependencies — FastAPI 0.115, uvicorn, httpx, Pydantic v2

**Core Logic:**
- `backend/app/storage.py`: `load_data()`, `save_data()`, `compute_leaderboard()` — all data access goes through here
- `backend/app/models.py`: `Movie` Pydantic model defines the canonical shape of every data record
- `backend/app/main.py`: All six API endpoints defined here

**Data:**
- `backend/data/league_data.json`: JSON object with `owners` (list of strings) and `movies` (list of Movie objects)

**Styles:**
- `frontend/src/styles.css`: Single stylesheet for the entire frontend; uses CSS custom properties defined in `:root`

**External Service:**
- `backend/app/services/tmdb.py`: Async TMDB integration; requires `TMDB_API_KEY` env var

## Naming Conventions

**Files:**
- Python modules: `snake_case.py`
- React components: `PascalCase.jsx`
- Non-component JS: `camelCase.js` (e.g., `api.js`)
- Config files: lowercase (`vite.config.js`, `requirements.txt`, `package.json`)

**Directories:**
- All lowercase, hyphenated where needed: `movie-league/`, `node_modules/`
- Python package directories use standard `snake_case`: `app/`, `services/`, `data/`

## Where to Add New Code

**New API endpoint:**
- Add route handler to `backend/app/main.py`
- If new data shape is needed, extend `backend/app/models.py`
- If the endpoint reads/writes data, go through `storage.py` functions

**New external service integration:**
- Create `backend/app/services/my_service.py` following the pattern in `tmdb.py`
- Import and call from the relevant route in `main.py`

**New React component:**
- Add `frontend/src/components/MyComponent.jsx`
- Add corresponding CSS classes directly to `frontend/src/styles.css` (no separate CSS files per component)
- Import into the parent component that uses it

**New API method (frontend):**
- Add a method to the `api` object in `frontend/src/api.js`

**Scoring formula changes:**
- Implement in `backend/app/storage.py` — specifically inside or called from `compute_leaderboard`, or in a new `compute_scores(movie)` helper. See ARCHITECTURE.md for context on why formulas are not currently computed.

**New data field on Movie:**
- Add the field to the `Movie` class in `backend/app/models.py`
- Add the field with a default value to existing entries in `backend/data/league_data.json`

## Special Directories

**`backend/data/`:**
- Purpose: Runtime data storage
- Generated: No (manually curated)
- Committed: Yes — `league_data.json` is the authoritative data file

**`.planning/codebase/`:**
- Purpose: GSD codebase map documents for AI-assisted planning
- Generated: Yes, by the GSD mapper
- Committed: Typically yes

---

*Structure analysis: 2026-07-08*

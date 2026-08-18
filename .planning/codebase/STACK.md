# Technology Stack

**Analysis Date:** 2026-07-08

## Languages

**Primary:**
- Python 3.11+ (required per README) / 3.12.3 (installed) - Backend API and data logic
- JavaScript (ES Modules) - Frontend React application

**Secondary:**
- JSX - React component templates (`frontend/src/components/`, `frontend/src/App.jsx`)
- JSON - Data persistence format (`backend/data/league_data.json`)
- CSS - Styling (`frontend/src/styles.css`)

## Runtime

**Environment:**
- Backend: Python 3.11+ (README minimum), 3.12.3 installed
- Frontend: Node 18+ (README minimum), 24.15.0 installed

**Package Manager:**
- Backend: pip (standard)
- Frontend: npm 11.12.1
- Lockfile: Not detected in repository (no `package-lock.json` committed; `requirements.txt` pins exact versions)

## Frameworks

**Core Backend:**
- FastAPI 0.115.0 - REST API framework, serves leaderboard and movie data
- Uvicorn 0.30.6 (`[standard]` extras) - ASGI server, runs the FastAPI app
- Pydantic 2.9.2 - Data validation and serialization for request/response models

**Core Frontend:**
- React 18.3.1 - UI component framework
- React DOM 18.3.1 - DOM rendering layer

**Build/Dev:**
- Vite 5.4.1 - Frontend dev server and build tool (`frontend/vite.config.js`)
- @vitejs/plugin-react 4.3.1 - Vite plugin for JSX/React fast refresh

**Testing:**
- Not detected - no test framework configured in either backend or frontend

## Key Dependencies

**Critical:**
- `httpx` 0.27.2 - Async HTTP client used in `backend/app/services/tmdb.py` for TMDB API calls
- `fastapi` 0.115.0 - Entire backend API surface depends on this
- `pydantic` 0.9.2 - Model validation for `Movie` and `LeagueData` in `backend/app/models.py`

**Infrastructure:**
- `uvicorn[standard]` 0.30.6 - Production-capable ASGI server (includes `websockets`, `httptools`, etc. via `[standard]` extra)

## Configuration

**Environment:**
- `TMDB_API_KEY` - Optional; read via `os.environ.get("TMDB_API_KEY")` in `backend/app/services/tmdb.py`. When absent the enrichment endpoint silently no-ops.
- No `.env` files detected in the repository; the variable is expected to be exported in the shell before starting the backend.

**Build:**
- `frontend/vite.config.js` - Configures dev server on port 5173, proxies `/api` to `http://localhost:8000`
- `backend/requirements.txt` - Pinned Python dependencies (no `pyproject.toml` or `setup.py`)
- `frontend/package.json` - Frontend dependencies; `"type": "module"` enables ES Modules

## Data Storage

**Primary:**
- Flat JSON file at `backend/data/league_data.json` — single source of truth for all league data
- Reads and writes protected by a `threading.Lock` in `backend/app/storage.py`
- No database (SQL or NoSQL) is used

## Platform Requirements

**Development:**
- Python 3.11+ with pip
- Node 18+ with npm
- Backend on `:8000`, frontend dev server on `:5173` (Vite proxy handles `/api` routing)

**Production (documented intent, not yet implemented):**
- Backend: Any host running a long-lived Python process (Fly.io, Render, VPS); JSON file needs a persisted volume
- Frontend: Static build via `npm run build` → `dist/` folder; deploy to Netlify / Vercel / Cloudflare Pages

---

*Stack analysis: 2026-07-08*

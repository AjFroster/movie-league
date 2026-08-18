# External Integrations

**Analysis Date:** 2026-07-08

## APIs & External Services

**Movie Metadata:**
- The Movie Database (TMDB) - Fetches `budget` and `revenue` (gross) for movie entries
  - SDK/Client: `httpx` 0.27.2 (async HTTP, no official TMDB SDK)
  - Base URL: `https://api.themoviedb.org/3`
  - Endpoints used: `/search/movie` (title search) and `/movie/{id}` (detail fetch)
  - Auth: `TMDB_API_KEY` environment variable (passed as `?api_key=` query param)
  - Implementation: `backend/app/services/tmdb.py`
  - Triggered by: `POST /api/movies/{owner}/{round_number}/enrich`
  - Graceful degradation: if `TMDB_API_KEY` is unset, `fetch_movie_financials()` returns `None` immediately and the app continues with manually-entered data

## Stubbed / Planned Integrations (Not Yet Implemented)

**Rotten Tomatoes:**
- Fields: `rt_crit` (critic score), `rt_aud` (audience score)
- Status: Stubbed — no public API exists; scraping hook defined but not implemented
- Stub file: `backend/app/services/critic_scores_stub.py` → `fetch_rt_scores()`
- Current approach: Manual entry via `PUT /api/movies/{owner}/{round_number}` or direct JSON edit

**Letterboxd:**
- Field: `letterboxd` (0-5 rating)
- Status: Stubbed — no public API exists; scraping hook defined but not implemented
- Stub file: `backend/app/services/critic_scores_stub.py` → `fetch_letterboxd_rating()`
- Current approach: Manual entry via `PUT /api/movies/{owner}/{round_number}` or direct JSON edit

## Data Storage

**Databases:**
- None — no SQL or NoSQL database is used
- All data persisted to `backend/data/league_data.json` (flat JSON file on local disk)

**File Storage:**
- Local filesystem only; `backend/app/storage.py` reads/writes `backend/data/league_data.json` with a threading lock

**Caching:**
- None detected

## Authentication & Identity

**Auth Provider:**
- None — the API has no authentication or authorization layer
- CORS is set to `allow_origins=["*"]` in `backend/app/main.py` (noted in code as needing to be tightened for production)

## Monitoring & Observability

**Error Tracking:**
- None detected

**Health Check:**
- `GET /api/health` endpoint returns `{"status": "ok"}` — suitable for uptime monitors or load balancer health checks (`backend/app/main.py`)

**Logs:**
- Uvicorn default request logging only; no structured application logging configured

## CI/CD & Deployment

**Hosting:**
- Not configured — README documents intent: backend on Fly.io / Render / VPS, frontend on Netlify / Vercel / Cloudflare Pages

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:**
- None are strictly required; the app runs fully without any env vars using manual data entry

**Optional env vars:**
- `TMDB_API_KEY` - Enables the `/enrich` endpoint to auto-fill budget and gross from TMDB. Set via `export TMDB_API_KEY=your_key_here` before starting the backend. Without it, the enrich endpoint returns `{"movie": ..., "tmdb_match": false}` and makes no external calls.

**Secrets location:**
- No `.env` files present in the repository; secrets are expected to be injected via shell environment before process start

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Frontend → Backend Communication

- Frontend calls backend exclusively through relative `/api` paths (no hardcoded backend URL)
- In development: Vite dev server (`frontend/vite.config.js`) proxies `/api/*` → `http://localhost:8000`
- In production: the static build expects `/api` to be reverse-proxied or rewritten to the deployed backend URL by the hosting platform
- HTTP client: native browser `fetch` API (`frontend/src/api.js`) — no axios or other HTTP library

---

*Integration audit: 2026-07-08*

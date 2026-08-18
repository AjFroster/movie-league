# Fantasy Movie League

A leaderboard app for tracking your friend group's fantasy movie league.

## Architecture

- **`backend/`** — FastAPI, serves the league data as JSON and computes the leaderboard.
  Data lives in `backend/data/league_data.json` — no database, just a file.
- **`frontend/`** — React (Vite). Landing page is the ranked leaderboard; tap/click an
  owner to expand their round-by-round picks.

## Running locally

**Backend** (needs Python 3.11+):
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (needs Node 18+):
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — it proxies `/api` calls to the backend on :8000.

## Auto-fetching data

Budget and gross can be auto-filled from TMDB (free API key, no scraping):

1. Get a key at https://www.themoviedb.org/settings/api
2. `export TMDB_API_KEY=your_key_here` before starting the backend
3. `POST /api/movies/{owner}/{round}/enrich` will look up the title and fill in
   `budget`/`gross` if TMDB has a match

RT Critic/Audience and Letterboxd scores have no public API — `backend/app/services/
critic_scores_stub.py` is a stubbed-out hook for whenever you wire up scraping
yourself. Until then, edit those fields directly in `league_data.json` or via the
`PUT /api/movies/{owner}/{round}` endpoint.

## Editing scores

`PUT /api/movies/{owner}/{round_number}` with a full movie JSON body updates that
entry (and persists it to the JSON file). There's no scoring-formula code here yet —
your rating/financial/penalty/watch-point numbers are stored as-is from your
spreadsheet; wire up the formulas in `app/storage.py` if you want them computed
instead of entered by hand.

## Deploying later

- Backend: any host that runs a long-lived Python process (Fly.io, Render, a small VPS).
  Swap the JSON file for a persisted volume or mounted disk.
- Frontend: build with `npm run build` and serve the `dist/` folder from
  Netlify/Vercel/Cloudflare Pages, pointing `/api` at your deployed backend URL.

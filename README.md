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

Ratings and financials can be filled in from two free APIs. Nothing is fetched until you
ask for it — there is no scheduler and no refresh-on-page-load.

### 1. Get two free API keys

| Key | Where | Free tier | Supplies |
|-----|-------|-----------|----------|
| `TMDB_API_KEY` | https://www.themoviedb.org/settings/api | ~100k/day | `budget`, `gross`, and the IMDb ID used for the OMDb lookup |
| `OMDB_API_KEY` | https://www.omdbapi.com/apikey.aspx | 1,000/day | `imdb` (the real IMDb rating) and `rt_crit` (Rotten Tomatoes critics) |

### 2. Put them in `backend/.env`

```bash
cp backend/.env.example backend/.env
# edit backend/.env and paste your keys
```

`backend/.env` is gitignored — never commit it. The backend also strips API keys out of its
own error messages, so a failed request will not echo your key back in a response or a log.

### 3. Trigger enrichment

One film:
```bash
curl -X POST http://localhost:8000/api/movies/Andrew/1/enrich
```

Every film:
```bash
curl -X POST http://localhost:8000/api/enrich-all
```

| Query param | Default | Applies to | Meaning |
|-------------|---------|------------|---------|
| `force=true` | `false` | both | Overwrite hand-entered values, and bypass the cache |
| `max_calls=N` | `60` | `/api/enrich-all` | Hard ceiling on outbound API calls for this run (1–200) |

Example — cap a bulk run at 20 calls:
```bash
curl -X POST http://localhost:8000/api/enrich-all?max_calls=20
```

### What gets filled in

| Field | Source |
|-------|--------|
| `imdb` | OMDb `imdbRating` — the real IMDb rating |
| `rt_crit` | OMDb `Ratings[]` → Rotten Tomatoes critics |
| `budget`, `gross` | TMDB (worldwide revenue, not domestic) |
| `roi` | computed as `gross / budget` |
| `rt_aud`, `letterboxd` | **manual only** — no free API exists for either |
| `bo_rank`, `awards` | not fetched |

### Your hand-entered numbers are safe

Each movie row carries a `sources` object recording where every value came from:

- **`manual`** — you typed it. Enrichment never overwrites it without `?force=true`.
- **`fetched`** — an API wrote it. Refreshed freely.
- **`unknown`** — it predates this tracking and could be either. Refreshable, with the
  original number preserved under `legacy_value` so nothing is lost.

Anything you change via `PUT /api/movies/{owner}/{round}` is automatically marked `manual`.

### Caching

Responses are cached in `backend/data/api_cache.json` (gitignored), so re-running enrichment
costs zero API calls. Entries expire on a sliding scale — 30 days for films released over a
year ago, 7 days for recent releases, 24 hours for films with no match yet. `?force=true`
bypasses the cache.

### Enrichment does not change the standings

There is no scoring formula in this codebase. `rating_score`, `financial_score`, `penalties`,
`watch_points`, and `total` are entered by hand from your spreadsheet, and the leaderboard
only sums them. Enrichment updates the *inputs* — `imdb`, `rt_crit`, `budget`, `gross`, `roi`
— but recomputes no score, so your rankings will look identical after a run. Making scores
live means transcribing the spreadsheet formula into a `compute_movie_scores()` function;
that is tracked as `BACK-01` in `.planning/REQUIREMENTS.md`.

## Editing scores

`PUT /api/movies/{owner}/{round_number}` with a full movie JSON body updates that
entry (and persists it to the JSON file). There's no scoring-formula code here yet —
your rating/financial/penalty/watch-point numbers are stored as-is from your
spreadsheet; wire up the formulas in `app/storage.py` if you want them computed
instead of entered by hand. Any field you change this way is stamped `manual` in that
row's `sources` object, so a later enrichment run will leave it alone.

## Running the tests

`backend/.venv` was created with [uv](https://docs.astral.sh/uv/) and contains no `pip` — use
`uv` to install into it:

```bash
uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest backend/tests -q
```

The suite makes no network calls and needs no API keys: both provider modules are stubbed, and
`TMDB_API_KEY`/`OMDB_API_KEY` are stripped from the environment for every test.

## Deploying later

- Backend: any host that runs a long-lived Python process (Fly.io, Render, a small VPS).
  Swap the JSON file for a persisted volume or mounted disk.
- Frontend: build with `npm run build` and serve the `dist/` folder from
  Netlify/Vercel/Cloudflare Pages, pointing `/api` at your deployed backend URL.

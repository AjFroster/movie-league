# Fantasy Movie League

A leaderboard app for tracking your friend group's fantasy movie league.

## Architecture

- **`backend/`** — FastAPI with SQLAlchemy and Alembic. SQLite in WAL mode at
  `backend/data/league.db`; set `DATABASE_URL` to point it at Postgres instead.
- **`frontend/`** — React (Vite), plain CSS with design tokens, light and dark.

A league is created for a year with a named set of players, drafted in a snake, and scored
from ratings and box office as the season runs. Leagues are public or private: a public one
is readable by anyone including signed-out visitors, a private one 404s to a stranger
rather than confirming it exists.

## Running locally

**Backend** (3.12 is what CI runs):
```bash
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The migration is not optional on a fresh checkout: nothing creates the schema for you.

**Frontend** (Node 24 in CI):
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

Every route is scoped to a league. One film:
```bash
curl -X POST http://localhost:8000/api/leagues/1/movies/Andrew/1/enrich
```

Every film in that league:
```bash
curl -X POST http://localhost:8000/api/leagues/1/enrich-all
```

| Query param | Default | Applies to | Meaning |
|-------------|---------|------------|---------|
| `force=true` | `false` | both | Overwrite hand-entered values, and bypass the cache |
| `max_calls=N` | `60` | `/api/enrich-all` | Hard ceiling on outbound API calls for this run (1–200) |

Example — cap a bulk run at 20 calls:
```bash
curl -X POST http://localhost:8000/api/leagues/1/enrich-all?max_calls=20
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

Anything you change via `PUT /api/leagues/{id}/movies/{owner}/{round}` is marked `manual`.

### Caching

Responses are cached in `backend/data/api_cache.json` (gitignored), so re-running enrichment
costs zero API calls. Entries expire on a sliding scale — 30 days for films released over a
year ago, 7 days for recent releases, 24 hours for films with no match yet. `?force=true`
bypasses the cache.

### Where ratings come from

| Field | Source | Notes |
|---|---|---|
| `imdb`, `letterboxd`, `rt_crit`, `rt_aud` | **MDBList** | All four in one call. Free tier, 1,000 requests/day. |
| `budget`, `gross`, `release_date`, IMDb ID | TMDB | The IMDb ID is what makes the MDBList lookup exact rather than a title guess. |
| `imdb`, `rt_crit` | OMDb *(fallback)* | Only called when MDBList leaves one of them empty, so a complete MDBList response costs no extra request. |

MDBList replaced OMDb as the primary ratings source because OMDb carries no Letterboxd
rating and no RT audience score at all, and its RT critic coverage on recent releases is
patchy — on this league's 2026 slate it supplied RT for roughly a third of the films.
MDBList covered every film that had ratings anywhere.

Films with no ratings are simply unreleased; no source has data for them yet.

### Scoring

Scores are computed from the enrichment inputs by `backend/app/scoring.py`, so a run that
updates ratings or box office also updates the standings. Every score is derived — editing
one directly has no effect, because it is recomputed on the next write.

**Ratings** — each source scores independently and they stack:

| Source | 4 pts | 7 pts | 12 pts |
|---|---|---|---|
| IMDb | 7.5–7.9 | 8.0–8.4 | 8.5+ |
| Letterboxd | 3.5–3.9 | 4.0–4.4 | 4.5+ |
| RT Critics | 75–84 | 85–94 | 95+ |
| RT Audience | 75–84 | 85–94 | 95+ |

**Financials** — gross tier plus ROI tier:

| Worldwide gross ($M) | 50 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|
| Points | 1 | 3 | 5 | 7 | 9 |

| ROI (gross ÷ budget) | 2× | 3× | 5× | 10× |
|---|---|---|---|---|
| Points | 3 | 5 | 8 | 12 |

**Penalties** (they stack, so a film that recoups under 75% takes −25):

- ROI < 1.0 → −10, ROI < 0.75 → −15
- Letterboxd < 2.5 → −10
- RT Critics < 50% → −10

**Watch points** — points follow the *viewer*, not the owner:

- **+5** for watching a film you drafted
- **+1** for watching a film anyone else drafted

Both stack, so watching every film in a 30-film season is worth 6x5 + 24x1 = 54. A point
earned for watching someone else's pick lands on the watcher's standing, not the owner's,
so it is attributed league-wide by `compute_leaderboard` rather than stored on the row.
Tick viewers in the expanded film panel; it is trust-based, with no login.

`total` is the plain sum of the four. A field with no data scores nothing, and a film with
no recorded ROI is not treated as having failed to recoup.

## Editing scores

`PUT /api/leagues/{league_id}/movies/{owner}/{round_number}` with a full movie JSON body
updates that entry. Any field you change is stamped `manual` in that row's `sources`
object, so a later enrichment run leaves it alone.

The scores themselves are not editable, because they are not stored decisions — they are
recomputed from the inputs above on every write.

## Accounts

Optional. With no identity provider configured the app runs as a single local user, with
every permission check still enforced — and it refuses to start that way if either the
database or the CORS origin looks like a deployment, so the convenience cannot escape a
laptop.

To turn accounts on, set `VITE_CLERK_PUBLISHABLE_KEY` in `frontend/.env` and `CLERK_ISSUER`
in `backend/.env`. There is deliberately no flag that disables authorization; only the
source of identity changes.

## Running the tests

`backend/.venv` was created with [uv](https://docs.astral.sh/uv/) and contains no `pip` — use
`uv` to install into it:

```bash
uv pip install --python backend/.venv/bin/python -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest backend/tests -q
```

The suite makes no network calls and needs no API keys: the provider modules are stubbed,
and `TMDB_API_KEY`, `OMDB_API_KEY`, `MDBLIST_API_KEY` and `CLERK_*` are stripped from the
environment for every test. A test that only passes because of a key in your shell is a
broken test.

Four more layers run in CI, and locally:

| Layer | Command | What only it catches |
|---|---|---|
| Smoke | `cd backend && python -m scripts.smoke_test` | Migrations, uvicorn, CORS, JSON over the wire |
| Browser | `cd frontend && npm run test:e2e` | Anything that renders wrong while every assertion passes |
| Two players | `cd frontend && npm run test:e2e:multi` | One person's pick reaching another person's screen |
| Nightly | GitHub Actions | The real provider APIs, which the suite is forbidden from calling. Inert until the three provider keys are added as repo secrets |

## Deploying later

- Backend: any host that runs a long-lived Python process (Fly.io, Render, a small VPS).
  SQLite needs a persistent volume; without one the database is gone on every redeploy.
  `DATABASE_URL` points at Postgres instead, and nothing above the connection string
  changes.
- Frontend: build with `npm run build` and serve the `dist/` folder from
  Netlify/Vercel/Cloudflare Pages, pointing `/api` at your deployed backend URL.

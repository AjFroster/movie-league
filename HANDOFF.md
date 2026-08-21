# Movie League — Handoff

Written for a session starting cold. See `.planning/TODO.md` for what to do next and why.

## What this is

A fantasy movie league. Players draft upcoming films in a snake draft and score points from
ratings and box office. FastAPI + SQLAlchemy backend, React/Vite frontend, SQLite locally.

## Running it

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev            # http://localhost:5173
```

**There is no `pip` in this project** -- no system pip, no venv pip, no `ensurepip`. The venv
was created by `uv`:

```bash
uv pip install --python backend/.venv/bin/python <package>
backend/.venv/bin/python -m pytest backend/tests -q     # 405 tests
```

API keys live in `backend/.env` (gitignored): `TMDB_API_KEY` (v4 read token, Bearer),
`OMDB_API_KEY`, `MDBLIST_API_KEY`. `backend/.env.example` documents all three.

## Where the data is

SQLite at `backend/data/league.db`, four tables:

```
leagues    id, name, year, rounds, status, draft_order, settles_on, frozen_at, created_at
players    id, league_id -> leagues.id, name
entries    id, league_id, player_id, round, pick_number, tmdb_id, title, poster_path,
           + ratings / financials / derived scores / sources (JSON provenance)
watches    entry_id -> entries.id, player_id -> players.id
```

An **entry** is one drafted film on one player's roster; the pick and its scoring live on
one row because they describe the same thing.

Two constraints enforce rules application code used to get wrong:
- `UNIQUE(league_id, tmdb_id)` — a film cannot be drafted twice in a league (but may be in
  another, which is why two 2027 leagues can both hold *Avengers: Secret Wars*)
- `PK(entry_id, player_id)` — a watch is a row, so concurrent toggles cannot overwrite

`backend/data/league_data.json` is a **readable export, not the source of truth**.
`db/porting.py` round-trips losslessly in both directions.

**Schema changes go through Alembic** (`backend/migrations/`). `env.py` takes its URL from
the app, not `alembic.ini`, so the two cannot drift, and renders SQLite in batch mode since
SQLite cannot `ALTER` a column in place.

```bash
cd backend && .venv/bin/python -m alembic upgrade head
```

## Scoring

The commissioner's tier tables, transcribed in `app/scoring.py` and validated against every
hand-scored row before adoption.

- **Ratings** — IMDb / Letterboxd / RT Critics / RT Audience each score independently and
  stack: 4 / 7 / 12 points at rising thresholds.
- **Financials** — worldwide gross tier (1/3/5/7/9) plus ROI tier (3/5/8/12).
- **Penalties** stack: ROI < 1.0 is −10, < 0.75 a further −15, Letterboxd < 2.5 is −10,
  RT Critics < 50% is −10.
- **Watch points follow the viewer**, not the owner: +5 for a film you drafted, +1 for
  anyone else's. This crosses owners, so it is attributed league-wide in
  `repo.leaderboard`, and a row keeps only its owner's own-pick component.

Scores are always derived and recomputed on write. A stored score is a cached calculation,
never authoritative.

## Where ratings come from

| Field | Source |
|---|---|
| `imdb`, `letterboxd`, `rt_crit`, `rt_aud` | **MDBList** — all four in one call, 1,000/day free |
| `budget`, `gross`, `release_date`, IMDb ID, poster | TMDB |
| `imdb`, `rt_crit` | OMDb, *fallback only* when MDBList leaves them empty |

MDBList replaced OMDb as primary: OMDb carries no Letterboxd rating and no RT audience
score, and its RT critic coverage on 2026 releases was about one film in three.

Results are cached in `backend/data/api_cache.json`, keyed by **film** (`mdblist:tt1341338`),
deliberately not by league — a film's rating is a property of the film, so two leagues
holding the same title share one fetch.

## Things that will bite you

**Provenance protects hand-entered data.** Every field records `manual` / `fetched` /
`unknown`. Enrichment never overwrites `manual` without `force=True`, and `force` would
overwrite the 59 values that rule exists to protect. If cached payloads are stale, **drop
the stale cache entries and re-run normally** rather than forcing.

**Tests must never touch real data.** An autouse fixture in `conftest.py` points every test
at an in-memory database. It exists because a test run once wrote through to the real
`league.db` and rewrote the season. `tmp_league` seeds both JSON and DB for the same reason.

**Never put a raw exception in a response body.** `httpx` embeds the full request URL, and
OMDb/MDBList authenticate by query parameter, so an unredacted error leaks the key. Every
handler uses `redact_secrets(str(e))`, and `test_secret_hygiene.py` fails if that slips.

**TMDB search ranks by popularity, not recency.** A 2026 pick named "The Mummy" matched the
1999 film and took its $415M gross. `pool._pick_result` rejects hits before
`SEASON_FLOOR_YEAR` (2025), treating a too-old match as *no* match. Look films up by
`tmdb_id` where possible — the draft already recorded exactly which film was taken.

**Frozen leagues refuse enrichment** rather than silently skipping it, so a caller cannot
believe it refreshed a season that did not move.

## Current state

Branch `feature/league-draft`, 14 commits ahead of `master`, 405 tests passing.

Three leagues: **Movie League 2026** (30 picks, 21 scored), **Movie League 2027** (42 picks),
**Sequels Only 2027** (9 picks). All settle 31 December of their year — see the TODO's note
on why 2026's date is worth revisiting.

Screens: league list (rename inline, delete with confirmation, editable settle date),
create league, draft board (setup / drafting / complete / rejected pick), and standings with
score breakdowns, watch toggles, and posters.

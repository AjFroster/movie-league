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

**The venv has no `pip` and `uv` is not on PATH.** What works is the pip inside uv's managed
Python, pointed at the project venv -- it resolves wheels for 3.12, not for its own 3.10:

```bash
~/.local/share/uv/python/cpython-3.10.19-linux-x86_64-gnu/bin/pip \
    --python backend/.venv/bin/python install <package>
backend/.venv/bin/python -m pytest backend/tests -q     # 493 tests
```

Node is not on PATH either; it lives at `~/.nvm/versions/node/v24.15.0/bin`. `npx` resolves
to the *Windows* npm through /mnt/c and cannot see this filesystem, so run vite directly:

```bash
export PATH="$HOME/.nvm/versions/node/v24.15.0/bin:$PATH"
cd frontend && node node_modules/.bin/vite build
```

API keys live in `backend/.env` (gitignored): `TMDB_API_KEY` (v4 read token, Bearer),
`OMDB_API_KEY`, `MDBLIST_API_KEY`, and optionally `CLERK_ISSUER`. `backend/.env.example`
documents them; `frontend/.env.example` documents `VITE_CLERK_PUBLISHABLE_KEY`.

## Accounts

**There is no flag that turns authorization off.** A boolean guarding a "skip the checks"
branch is exactly what ends up enabled in production by accident, so `app/auth.py` has none.
The permission code always runs. Only *where identity comes from* changes:

| | Clerk unset | Clerk set |
|---|---|---|
| Identity | `LOCAL_USER_ID` (`"local"`), always | subject of a verified RS256 JWT |
| Sign-in UI | none | Clerk's, before the app renders |
| Ownership checks | run, and always match | run, and can fail |

Running without accounts is therefore not a special case in the permission code — it is a
database with one account in it.

`verify_startup_configuration()` runs at boot and **refuses to start** in local mode unless
the database is SQLite *and* `CORS_ORIGIN` is localhost. A deployment breaks both without
thinking about it, so unauthenticated access cannot quietly reach one.

Three tiers, in `app/auth.py`:

- **`require_creator`** — rename, settle date, pick timer, delete, freeze, start draft,
  enrich, hand-edit scores.
- **`require_actor(player)`** — make a pick, tick a watch. Allowed if you claimed that slot,
  **or the slot is unclaimed and you created the league**. That second clause is what keeps
  the single-laptop draft working: one person picks for everyone in the room. Once someone
  claims a slot the creator loses it — the pick clock covers a player who goes quiet.
- **`require_member`** — auto-pick. Any member's browser may ask, which is what lets a draft
  advance when the player on the clock has shut their laptop; the server re-checks its own
  deadline, so asking early achieves nothing.

### Visibility

`leagues.visibility` is `private` (default) or `public`, and governs **reading only** —
writing is always ownership-based, so publishing a league grants no ability to change it.

- **private** — members only: the creator plus anyone holding a slot
- **public** — anyone with the link, *including signed-out visitors*

A private league answers **404, not 403**. 403 would confirm it exists, which leaks the very
thing privacy is for; an outsider cannot tell a private league from one that never existed.

**Public leagues are browsable.** `GET /api/leagues` takes an optional identity and returns
your leagues plus every public one, each tagged `mine` and `is_creator` so the home screen
can group them and hide controls the viewer cannot use. A signed-out visitor gets the public
ones — the app renders for them, with sign-in as a side panel rather than a wall. Gating the
whole app behind a login made public leagues unreachable, which defeated having them.

`scope="mine"` is separate and used for backups: a public league you can *read* is not a
league you should be backing up.

Reads use `current_user_optional`, which returns `None` for a missing token so a public link
works signed-out — but a token that is *present and invalid* still 401s, so a forged token
can never be quietly downgraded to "anonymous".

**Archives stay members-only even for a public league.** Public grants the standings; an
archive additionally carries every account id that claimed a slot, which is not the same
thing and should not ride along with a shared link.

Slots are claimed with `POST /api/leagues/{id}/claim`. `players.user_id` is nullable and that
is the whole design: a commissioner names six players and drafts tonight, and the other five
claim their slots whenever they sign up.

## Where the data is

SQLite at `backend/data/league.db`, four tables:

```
leagues    id, name, year, rounds, status, draft_order, settles_on, frozen_at,
           created_at, pick_seconds, clock_started_at
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

## Backup and restore

Two JSON formats live in `db/porting.py`, and confusing them loses data:

| | `export_league` / `import_league` | `dump_archive` / `load_archive` |
|---|---|---|
| Shape | legacy `{owners, movies}` | `{format: "movie-league/1", leagues: [...]}` |
| Carries | scores and watchers only | **everything** |
| For | reading `league_data.json` | backup, restore, Postgres migration |

The legacy pair is lossless only *against a legacy file*. Exporting the real database
through it drops all 57 pick numbers, 80 poster paths, 22 watch timestamps, and every
league's name, year, settle date and timer — the format has nowhere to put them. Use it to
read `league_data.json`, never to back anything up.

Back up from the UI (**BACK UP** on the league list, or `↓` on one league) or directly:

```bash
curl -sO http://localhost:8000/api/export
```

Restore is a script rather than an endpoint, deliberately: it replaces league history, and
with no auth on the API an endpoint that could do that would be the worst hole in the app.

```bash
cd backend && .venv/bin/python -m scripts.restore backup.json [--replace] [--dry-run]
```

It refuses a non-empty database without `--replace`, and `--replace` writes a snapshot of
what it is about to delete before deleting it. Two things are deliberately **not** in an
archive: database ids (a restore assigns its own) and `clock_started_at` (live pick-clock
state — a restored draft starts a fresh clock rather than inheriting an expired deadline).

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

`master`, 493 tests passing.

Four leagues: **Movie League 2026** (30 entries, imported so no pick numbers), **Movie League
2027** (42 picks), **Sequels Only 2027** (9), **trish v andrew 2027** (6). All settle 31
December of their year — see the TODO's note on why 2026's date is worth revisiting. All on a
60-second pick clock.

Screens: league list (rename inline, delete with confirmation, editable settle date and pick
timer, export), create league, draft board (setup / drafting / complete / rejected pick, with
a server-authoritative clock that auto-picks on expiry), and standings with score breakdowns,
watch toggles, and posters.

`.planning/TODO.md` holds the staged roadmap: accounts (Clerk) → live draft (polling) →
hosting → Stripe in test mode, with the sequencing reasoning kept alongside.

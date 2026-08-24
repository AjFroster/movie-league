# Fantasy Movie League

A fantasy league for films. A group drafts upcoming releases in a snake draft, then scores
points as those films collect ratings and box office through the season.

Written for one friend group, and built as if it were not: every mutating endpoint is
authorized, every provider call is cached and redacted, and the whole season round-trips
through an archive.

## How it works

Someone creates a league for a year and names the players. The draftable pool is the most
popular theatrical releases of that year from TMDB, ranked by popularity rather than
filtered by it, because the scale is not comparable between a year that has released and
one that has not.

The draft is a snake: the order reverses each round, so whoever picks last also picks first
in the round that follows. Each player has a clock, and the server owns it. Everyone watches
the same board from their own device, kept current by polling with conditional GETs.

Scores come from three places. Ratings — IMDb, Letterboxd, Rotten Tomatoes — in tiers.
Financials — budget, gross, and the ratio between them. And watching: 5 points for watching
your own pick, 1 for watching someone else's, which is the part that makes people actually
watch the films.

## Stack

| | |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0, Alembic. SQLite with WAL locally; a connection string away from Postgres |
| Frontend | React 18, Vite 5, plain CSS with design tokens. Light and dark, following the device by default |
| Accounts | Clerk. RS256 tokens verified against JWKS. No flag disables authorization — without a provider the app runs as one local identity, and refuses to start that way anywhere that looks hosted |
| Providers | TMDB for the pool and posters, OMDb and MDBList for ratings and financials. All cached, all redacted from error paths |

## What exists

Leagues are public or private. A public one is readable by anyone, including signed-out
visitors, who see the standings and the draft board but no controls they cannot use. A
private one 404s rather than 403s, so its existence is not confirmed to a stranger.

Enrichment carries per-field provenance, and a manual edit is stamped so a later automatic
pass will not overwrite it. `GET /api/export` produces a whole-database archive that
`scripts/restore.py` reads back.

540 tests across five layers: unit and journey tests in process, a smoke test against a
real uvicorn on a real migrated database, browser tests, and a two-process test where two
people draft against one database from two browsers. CI runs all of them; `master` takes
pull requests only.

## Where things are

- `.planning/TODO.md` — the live roadmap and the reasoning behind its order
- `.planning/hosting.md` — where this runs, and what to set up to put it there
- `.planning/archive/` — the record of a milestone that finished in August 2026

Everything else is documented in comments beside the code it describes, which is the one
place documentation cannot drift away from its subject.

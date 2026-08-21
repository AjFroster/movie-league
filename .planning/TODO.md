# Backlog

Ordered by what unblocks what, not by size. Reasoning is kept with each item so a future
session does not have to rediscover why the order is what it is.

---

## Blocking anything public

### 1. Authentication — prerequisite for hosting, not a follow-up

There is currently **no authentication of any kind**. Eleven endpoints mutate data:

```
POST   /api/leagues                          create
PATCH  /api/leagues/{id}                     rename, settle date
DELETE /api/leagues/{id}                     delete league + all picks
POST   /api/leagues/{id}/freeze              settle / reopen
POST   /api/leagues/{id}/draft/start         randomize order
POST   /api/leagues/{id}/draft/pick          make a pick
POST   /api/leagues/{id}/enrich-all          spend API quota
POST   /api/enrich-all                       spend API quota
PUT    /api/movies/{owner}/{round}           hand-edit scores
POST   /api/movies/{owner}/{round}/watch     toggle a watch
POST   /api/movies/{owner}/{round}/enrich    spend API quota
```

On localhost this is fine. Hosted, anyone with the URL can delete a league, draft on
someone's behalf, or exhaust the OMDb free tier (1,000/day).

This is why accounts come **before** hosting rather than after.

Smallest useful shape: accounts own leagues; only members can pick; only the creator can
delete or settle. Watch toggles become "I watched this" rather than ticking someone else's
box, which is simpler *and* safer.

### 2. Export before hosting

`db/porting.py` round-trips a league to JSON losslessly and is well tested, but nothing in
the UI calls it. In practice there is no backup story: the entire league history is one
SQLite file. A one-click export is worth more than any feature on this list before data
goes near a cloud provider.

---

## The detail view (next session's stated starting point)

### 3. Cut the clutter from the expanded film panel

Biggest single win: **delete the CAMPAIGN TRACKER column.** It is hardcoded illustrative
text carried over from the original mockup, occupying a third of the width and labelled
"not live data". It is decoration presented as information.

Also worth reviewing:
- The stat strip duplicates numbers the breakdown table states directly beneath it.
- `LEAGUE OWNERSHIP` is one line of content in a full column.
- With those gone the panel could be two columns instead of three, which also fixes the
  cramped wrapping at narrower widths.

### 4. Delete `frontend/src/components/OwnerDetail.jsx`

Dead since the Phase 1 redesign. Imported nowhere, and references five CSS classes
(`blank`, `detail`, `round-num`, `round-row`, `round-total`) that no longer exist. It is
also the reason `.planning/codebase/ARCHITECTURE.md` describes a structure the app does not
have.

---

## Hosting and AWS

### 5. Deployment

Groundwork is done: SQLAlchemy makes the engine a connection string, and Alembic migrations
exist and are applied. What is genuinely new:

- **Secrets**: four API keys (`TMDB`, `OMDB`, `MDBLIST`, plus `DATABASE_URL`). They are in
  `backend/.env`, gitignored, and redacted from every error path -- that discipline must
  survive the move to a secrets manager.
- **Database**: RDS Postgres (~$15/mo) vs a managed Postgres on Fly/Railway. SQLite works
  fine on a single instance; it stops working the moment there are two.
- **Frontend**: `npm run build` produces a static `dist/` for any CDN. The `/api` proxy in
  `vite.config.js` is dev-only and needs replacing with a real origin.

Only revisit "SQLite vs Postgres" if multiple app instances become real. One small instance
handles this league comfortably.

---

## Quality of life, roughly in value order

### 6. ~~Undo a draft pick~~ — dropped, replaced by the pick clock

Shipped instead: a per-league pick timer that auto-picks the top available film when a
player's time runs out. Configurable at creation and editable later; 0 disables it.

### 7. Scheduled enrichment

Enrichment is manual and someone has to remember. With films releasing weekly through
December, a stale scoreboard is worse than an obviously empty one. Cheap once hosted, since
`enrich_all` is already paced, capped, cached, and safe to re-run.

Must skip frozen leagues -- `apply_documents` already refuses them.

### 8. "What changed" digest

Scores shift silently. *"Andrew gained 12 points this week -- Toy Story 5 crossed $1B"* is
what makes a league fun between drafts, and everything needed is already stored: provenance
carries `at` timestamps and every score is derived.

Needs a scores snapshot per refresh to diff against.

### 9. Mobile standings

The draft board is desktop-first by design (a group around one laptop) and that is correct.
Casual score-checking on a phone is a different job and is currently poor.

### 10. Small ones

- League names are not unique; two leagues can share a name. Rename exists, uniqueness does
  not.
- `bo_rank` and `awards` are in the schema and scored by nothing.
- The favicon 404s on every page load.

---

## Decisions the league needs to make (not code)

### The 2026 settle date

Per-league settle dates ship; 2026 is on its agreed **31 December**. The roster argues
against that date:

| Film | Opens | Box office by 31 Dec |
|---|---|---|
| Werwulf | 25 Dec | 6 days |
| Avengers: Doomsday | 16 Dec | 15 days |
| Dune Part 3 | 15 Dec | 16 days |
| **Narnia** | **11 Feb 2027** | **never -- locks at 0** |

Narnia is in the 2026 league but does not release in 2026 at all, so a strict year-end close
permanently zeroes one of Evan's six picks. Closing around **31 March 2027** would let the
December releases finish and give Narnia a few weeks. One-click change, entirely the
league's call.

### Illustrative widgets

`THIS WEEK` (sidebar) and `CAMPAIGN TRACKER` (film panel) are both hardcoded and labelled as
such. Decide whether to back them with real data or delete them. Item 3 assumes deletion.

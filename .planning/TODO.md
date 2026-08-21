# Backlog

Ordered by what unblocks what, not by size. Reasoning is kept with each item so a future
session does not have to rediscover why the order is what it is.

**Decided 21 Aug 2026** — the destination is a hosted, multi-device app with accounts, a
live draft, and a test-mode Stripe integration built to learn Stripe rather than to charge
anyone. Hosting provider is deliberately **not chosen yet**; stages 1-3 are host-agnostic on
purpose, and stage 4 explains what evidence to pick on.

---

## Why the order is what it is

Three pieces, three different relationships to hosting. Lumping them together is what makes
the sequencing feel harder than it is.

| Piece | Relative to hosting | Why |
|---|---|---|
| **Accounts** | **Required before** | 13 mutating endpoints, no auth. Hosted without it, anyone with the URL deletes a league or drains the 1,000/day MDBList quota. |
| **Live draft** | **Decide before, build either side** | The transport choice constrains the host. Polling runs anywhere; WebSockets rule out plain Lambda. Choosing polling *removes* the constraint. |
| **Stripe** | **Hard-blocked until both** | Cannot charge an identity that does not exist; webhooks need a stable public HTTPS URL. |

Auth is also *easier* before hosting, not merely required: it touches every endpoint and
every call in `api.js`. That belongs on a 30-second reload loop, not a 5-minute deploy loop.

**The multiplayer half that is already done.** The pick clock is server-authoritative, draft
state is derived from the pick list rather than a stored cursor, and `UNIQUE(league_id,
tmdb_id)` makes a double-pick a database error instead of a race. That is the part that is
hard to retrofit, and it exists. What remains is transport — how other screens find out — and
transport is swappable. Start with polling; earn WebSockets with a real complaint about lag.

---

## Stage 1 — Export ✅ done

Shipped: `GET /api/export`, `GET /api/leagues/{id}/export`, a BACK UP button on the league
list and a per-league `↓`, plus `scripts/restore.py`.

**The plan said "wire a button to `db/porting.py`". That was wrong, and worth recording why.**
`export_league` emits the legacy `{owners, movies}` shape, which cannot express a pick number,
a poster path, or any league setting. It round-trips *legacy JSON → DB → legacy JSON*
losslessly — which is what its test asserts and what the one-time migration needed — but as a
backup it would have silently dropped, across the four real leagues, **57 pick numbers, 80
poster paths, 22 watch timestamps, and every league's name, year, settle date and timer.**
A backup that cannot restore the drafts is worse than no backup, because it is trusted.

So the format came first. `dump_archive`/`load_archive` (`movie-league/1`) carry everything,
verified by the assertion the legacy suite never made: **DB → JSON → DB → JSON equality**,
against the real database.

Restore is a CLI, not an endpoint — it is rare, destructive, and there is still no auth in
front of the API. It is also the SQLite → Postgres path:

```bash
DATABASE_URL=postgresql+psycopg://... python -m alembic upgrade head
DATABASE_URL=postgresql+psycopg://... python -m scripts.restore backup.json
```

---

## Stage 2 — Accounts (2-3 days, local)

### 2. Clerk, not a hand-rolled session layer

**Clerk over Auth0** for this app: better React drop-ins, and backend verification is a JWT
check against a JWKS endpoint rather than an SDK. Free tier covers a league by orders of
magnitude. No passwords stored here at all.

### 3. The schema change that keeps today's app working

The critical design decision, because it decides whether accounts are additive or a rewrite:

```
leagues.owner_user_id   TEXT NULL     -- Clerk user id of the creator
players.user_id         TEXT NULL     -- Clerk user id, NULL = slot not yet claimed
```

**Both nullable, and `players.user_id` especially.** A commissioner types six names and drafts
that evening; the other five have not signed up and should not have to before the draft can
start. A slot gets *claimed* later via an invite link. This keeps the current flow intact and
makes accounts strictly additive.

`owner_user_id` nullable also means the four existing leagues survive the migration. Backfill
them to the first account created — one script, run once, before anything is hosted. Do not
leave them null and treat null as "anyone may edit"; that is the hole this stage exists to
close.

### 4. Three permission tiers, not one

```
any signed-in user   POST   /leagues                       create
league member        POST   /leagues/{id}/draft/pick       pick (must be on the clock)
                     POST   /leagues/{id}/.../watch        tick your OWN box only
creator only         PATCH  /leagues/{id}                  rename, settle date, pick_seconds
                     DELETE /leagues/{id}                  delete league + all picks
                     POST   /leagues/{id}/freeze           settle / reopen
                     POST   /leagues/{id}/draft/start      randomize order
                     POST   /leagues/{id}/enrich-all       spends API quota
                     POST   /enrich-all                    spends API quota
                     PUT    /movies/{owner}/{round}        hand-edit scores
```

Watch toggles become "I watched this" rather than ticking someone else's box — simpler *and*
safer. **Caveat:** an unclaimed player slot has nobody to tick it, so the creator needs an
override for unclaimed slots or a mid-season league goes stale.

The two legacy unscoped routes (`PUT /api/movies/...`, `POST /api/enrich-all`) are
league-agnostic and cannot be authorized cleanly. Retire them in this stage rather than
inventing a rule for them.

### 5. `api.js` needs one token injection point

Every call already funnels through `get` / `send` / `post`. That is three functions to change,
which is the whole reason this is cheap. Attach the Clerk bearer token there.

### 6. Test fixtures need an auth override

`conftest.py`'s autouse in-memory fixture already exists. Add a FastAPI dependency override
supplying a fake identity, plus at least one test per tier asserting a *non-member is refused*
— an auth test suite that only ever tests the happy path proves nothing.

---

## Stage 3 — Live draft (1-2 days, still local)

### 7. Poll `GET /leagues/{id}/draft`, do not reach for WebSockets

Two seconds, only while `status == drafting`, stopped on complete. Six players polling every
2s is nothing, and it runs on every host — which is exactly what keeps stage 4 open.

Add an `updated_at` or ETag so an unchanged poll is cheap. Without it this is a full board
serialization every 2 seconds per client for no reason.

### 8. Read-only board for everyone not on the clock

Today's board assumes the person looking at it is the person picking. Split that: the on-clock
player gets the pool and search, everyone else gets the board and the countdown.

### 9. Swallow the autopick 409

With N clients, all N fire `autopick` at expiry. The server re-checks its own clock and the
unique constraint protects the write, so exactly one wins — this is already correct, and it is
a **feature**: the draft advances even if the on-clock player's laptop is shut. Just stop the
other N-1 from rendering the resulting 409 as an error.

### 10. Test the actual failure modes

Not two tabs on one LAN. The real ones: mobile Safari backgrounding a tab mid-draft, a phone
moving WiFi → LTE, and two people tapping the same film inside the same second. The first two
need a hosted URL, so they land in stage 4 — write them down now so they are not forgotten.

---

## Stage 4 — Hosting (decide when stages 1-3 are done)

Deliberately deferred. Polling means the choice is no longer architecturally forced, so decide
it on cost and appetite instead:

- **Fly.io / Railway** — one command, managed Postgres, HTTPS included, ~$5-10/mo. Roughly a
  day of setup for an app this size.
- **AWS proper** (App Runner/ECS + RDS + Secrets Manager) — closer to a week, and worth it
  only if learning AWS is itself a goal. If this wins, revisit Cognito over Clerk to keep one
  console.
- **Lightsail / single EC2** — AWS-branded without the VPC and ECS tax. Fine until a second
  instance is needed, which for one league is never.

Groundwork already done: SQLAlchemy takes a connection string, Alembic migrations exist and
are applied, `npm run build` emits a static `dist/`.

Genuinely new work whichever wins:

- **Secrets** — `TMDB`, `OMDB`, `MDBLIST`, `DATABASE_URL`, plus Clerk's keys. They are in
  `backend/.env` today, gitignored, and redacted from every error path. **That redaction
  discipline must survive the move to a secrets manager** — see `test_secret_hygiene.py`.
- **CORS** — `main.py` reads a single `CORS_ORIGIN`. Real origin needed, and Clerk adds its
  own domains.
- **The `/api` proxy in `vite.config.js` is dev-only** and needs a real origin.
- **SQLite → Postgres** — only if a second instance becomes real. Item 1 is the migration.

---

## Stage 5 — Stripe, test mode only (1 day, self-contained)

### 11. Built to learn Stripe, never taken live

Scope follows from that: a Checkout session, a webhook, a boolean on the account. No Connect,
no payouts, no KYC.

**Payouts were considered and deliberately excluded.** Buy-ins with a payout to a winner is
money in and money out on a contest, and the fantasy-sports carve-outs are written around
athletic performance statistics — a box-office league is not obviously inside them, and state
law varies. Test mode sidesteps the question entirely. If this ever goes live, that question
gets answered by someone qualified *first*.

The three things actually worth learning here, all of which transfer to a real integration:

- **Webhook signature verification** — the endpoint is public; unverified webhooks are a
  forgery hole.
- **Idempotency** — Stripe retries. A webhook handler that grants something twice is the
  classic bug.
- **The webhook is the source of truth, not the success redirect.** Users close the tab.

---

## Quality of life, unblocked by any of the above

### 12. Scheduled enrichment

Manual today and someone has to remember. With films releasing weekly through December a stale
scoreboard is worse than an obviously empty one. Cheap once hosted — `enrich_all` is already
paced, capped, cached, and safe to re-run. Must skip frozen leagues; `apply_documents` already
refuses them.

### 13. "What changed" digest

*"Andrew gained 12 points this week — Toy Story 5 crossed $1B"* is what makes a league fun
between drafts, and everything needed is stored: provenance carries `at` timestamps and every
score is derived. Needs a scores snapshot per refresh to diff against.

Pairs naturally with accounts — once there are verified email addresses, this becomes the
weekly email that brings people back.

### 14. Mobile standings

The draft board is desktop-first by design (a group around one laptop) and that stays correct.
**Stage 3 changes the premise** — once people draft from phones, the board needs a phone
layout too, so consider these one job rather than two.

### 15. Small ones

- League names are not unique; two leagues can share a name. Rename exists, uniqueness does
  not. Accounts make this worse (whose namespace?) — decide during stage 2.
- `bo_rank` and `awards` are in the schema and scored by nothing.
- The favicon 404s on every page load; there is no `frontend/public/` at all.
- Stray `*:Zone.Identifier` files in `frontend/src/components/` — WSL artifacts from the
  original Windows copy. Delete them and gitignore the pattern.

---

## Decisions the league needs to make (not code)

### The 2026 settle date

Per-league settle dates ship; 2026 is on its agreed **31 December**. The roster argues against
that date:

| Film | Opens | Box office by 31 Dec |
|---|---|---|
| Werwulf | 25 Dec | 6 days |
| Avengers: Doomsday | 16 Dec | 15 days |
| Dune Part 3 | 15 Dec | 16 days |
| **Narnia** | **11 Feb 2027** | **never — locks at 0** |

Narnia is in the 2026 league but does not release in 2026 at all, so a strict year-end close
permanently zeroes one of Evan's six picks. Closing around **31 March 2027** would let the
December releases finish and give Narnia a few weeks. One-click change, entirely the league's
call.

### The `THIS WEEK` sidebar

`ThisWeekSidebar.jsx` is hardcoded and labels itself "Illustrative — not live data". Back it
with real data or delete it. The `CAMPAIGN TRACKER` column it used to sit beside is already
gone (`e3bde37`).

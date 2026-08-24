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
| **Stripe buy-ins** | **Hard-blocked until both** | Cannot charge an identity that does not exist; webhooks need a stable public HTTPS URL. |
| **Stripe tip jar** | **Blocked by neither** | A Payment Link is a URL Stripe hosts. No account, no webhook, no backend, no schema. Shipped. |

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

## Stage 2 — Accounts ✅ done

Clerk, wired so the app still runs with no Clerk account at all.

**No `AUTH_ENABLED` flag.** The permission code always runs; only the identity source
changes. Unconfigured, there is exactly one user (`LOCAL_USER_ID`), ownership is still
checked and simply always matches — so running without accounts is a database with one
account in it, not a branch that skips checks. `verify_startup_configuration()` refuses to
boot in that mode unless the database is SQLite *and* `CORS_ORIGIN` is localhost.

`players.user_id` is nullable and that is the design: name six players, draft tonight, and
the other five claim their slots whenever they sign up. An unclaimed slot is acted on by the
league creator — the single-laptop draft, unchanged. Once claimed, the creator loses it.

Every mutating route is guarded; see HANDOFF.md for the three tiers. 472 tests, most of them
denials, including a forged-signature token and a startup guard simulated against Postgres.

**Still needs your Clerk keys to run multi-user** — see "What is left in stage 2" below.

### Deviation from the plan, recorded

The plan said to retire `PUT /api/movies/{owner}/{round}` and `POST /api/enrich-all` rather
than "invent a rule" for them. They were authorized against the default league instead.
Retiring them means rewriting 46 test references and a live frontend fallback path, and
that is a *correctness* fix (they act on whichever league is newest, which is already wrong
with four leagues) rather than the *security* fix stage 2 is for. The hole is closed either
way. Retirement is item 15 below.

### What is left in stage 2

Nothing in code. One manual step, which needs your account:

1. Sign up at https://dashboard.clerk.com and create an application.
2. Copy the **Publishable key** into `frontend/.env` as `VITE_CLERK_PUBLISHABLE_KEY=pk_test_…`
3. Copy the **Frontend API URL** (the issuer) into `backend/.env` as `CLERK_ISSUER=…`
4. Restart both. A sign-in screen appears; your four existing leagues belong to `"local"`,
   so reassign them — `UPDATE leagues SET owner_user_id = '<your clerk user id>'` — or
   create fresh ones.

## Shipped since the roadmap was written

Not on the original plan, but done:

- **Public/private leagues**, browsable without an account. Closed a hole found on the way:
  `GET /api/export` had no authorization and returned every league in the database to
  anonymous callers.
- **Light/dark themes** with a single cycling toggle. Fixed a pre-existing contrast failure
  (dark `--text-faint` at 2.63:1, below the 3:1 floor, in 39 places).
- **CI and branch protection.** Backend tests, CSS coverage, frontend build, and a
  Conventional Commits check on PR titles. `master` takes PRs only.

### Process lesson worth keeping

Four separate silent failures happened in one session, each reporting success:

| What | Why it was silent |
|---|---|
| `str.replace` on absent text | a no-op returns the original string |
| PR merged into a stale base | GitHub reports MERGED regardless |
| `git add` on an unresolved conflict | `rebase --continue` accepts it |
| rebase auto-merge dropping a CSS block | no conflict, build still passes |

Two of the four are now caught mechanically (`check:css`, and asserting before/after in any
scripted edit). **Do not stack PRs** — the third failure came from that, and waiting one
round trip to branch from an updated `master` costs almost nothing.

---

## Stage 3 — Live draft ✅ done

The board keeps itself in step with everyone else's picks, and shows each viewer only what
they can act on.

**Polling, not a socket.** A conditional GET every two seconds while a draft runs, stopped
on complete, paused while the tab is hidden. `GET /leagues/{id}/draft` carries an ETag:
8,912 bytes becomes 0 on an unchanged poll, and a minute of a quiet six-player draft costs
27 KB rather than 1,567 KB. Bandwidth was never the point -- without change detection the
board rebuilds every two seconds and loses text selection, hover, and any open dropdown
mid-draft.

The tag is a hash of the payload rather than a stored counter, so there is no second place
to forget to update. `seconds_remaining` is excluded from it, or every poll would miss.

**The board says what each viewer may do.** The payload carries a `viewer` block --
`player`, `can_pick`, `is_member` -- computed server-side from the same rule
`require_actor` enforces. A browser that re-derived it would drift, and the drift would
show as buttons that 403.

Everyone sees the pool; only the person who can actually pick gets a DRAFT button. That
is the opposite of what this item originally said, which was "the on-clock player gets the
pool and search, everyone else gets the board and the countdown" -- the decision changed
during planning and the plan was not updated, so anyone implementing it as written would
have built the wrong thing.

**Auto-pick is member-only and its 409 is silent.** Every member's browser firing at once
is deliberate: the server re-checks its own deadline and exactly one write wins, which is
what advances a draft whose on-clock player has gone. The other N-1 get a 409, which is
the expected outcome rather than an error worth showing. Spectators do not ask at all --
public leagues are browsable now, so that is a real caller who would otherwise collect a
403 every time a clock ran out.

### Still owed from this stage

The failure modes that need a real network: mobile Safari backgrounding a tab mid-draft, a
phone moving WiFi to LTE, two people tapping the same film inside the same second. Tab
backgrounding is handled in code and untested; the rest cannot be tested honestly on a
laptop. They belong to stage 4 verification.

Browser tests cannot cover the read-only board either: local mode has exactly one user,
who is always the creator, so there is no second identity to be a spectator with. The
backend tests carry that coverage.

---

## Stage 4 — Hosting ▸ decided 22 Aug 2026

**Cloudflare Pages + Cloud Run + Neon.** The architecture, the console setup order and
the two traps are in [`hosting.md`](hosting.md); the prep is in the repo already.

The reasoning that produced that choice is below, kept because the next person to ask
"why not AWS" deserves the answer rather than the conclusion.

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

### 11a. Tip jar ✅ done

A `VITE_STRIPE_TIP_URL` Payment Link under the league list, absent from the DOM when unset.
Stripe hosts the payment page, so there is no publishable key in the bundle, no webhook to
verify, no redirect to trust and nothing about a payment stored here. Anonymous on purpose:
the app never learns who paid.

**The roadmap said Stripe was hard-blocked until accounts and hosting existed. That was
written about buy-ins and is wrong for a tip jar** -- a hosted link needs neither. It does
still want hosting to be *useful*, since nobody can reach the app to click it.

Real money brings back what test mode avoided: Stripe identity verification, a bank
account, and the fact that tips are taxable income rather than charitable donations. None
of that is code.

### 11b. Built to learn Stripe, never taken live

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

### 14b. Audit GET routes the way mutating ones were audited

`GET /api/export` returned **every league in the database** — owner ids, player names, all
of it — to any anonymous caller, from the day it shipped until visibility landed. The Stage 2
audit script only inspected non-GET routes, on the assumption that reads are harmless. A read
that returns the whole database is not.

Worth a pass over every remaining GET with that lens rather than trusting the method.

**One already found, and fixed.** `GET /api/pool-size` took no authentication and went
through no cache, so a single HTTP call made the server issue up to 25 TMDB requests, one
per page of a 500-film pool.

Two corrections to how that was first written here. MDBList is not involved: `pool.py`
calls TMDB and nothing else. And the exposure was never only `pool-size` — a public league
makes `GET /{league_id}/pool` reachable signed out by design, and it carries the same
amplification, so requiring an identity on one endpoint would have moved the problem
rather than solved it.

Hence both halves. `pool-size` now needs an identity, which costs nothing because the
create screen is unreachable signed out. And `fetch_pool` caches for six hours on a
*bucketed* size, so a caller walking `size=1..500` produces five cache entries for a year
instead of 500 misses.

### 15. Small ones

- League names are not unique; two leagues can share a name. Now that leagues are scoped to
  an owner this matters less — you only ever see your own — but two of *your* leagues can
  still share a name.
- `bo_rank` and `awards` are in the schema and scored by nothing.

**Cleared 22 Aug 2026.** The favicon: `frontend/public/` now holds a theme-aware SVG with
PNG fallbacks. The stray `*:Zone.Identifier` files: deleted, and the gitignore rule was
already there. The legacy unscoped `/api/movies/*` routes: already gone, removed with the
rest of the legacy surface in PR #9 — this entry outlived the work it described, which is
the argument for checking a backlog against the code before trusting it.

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

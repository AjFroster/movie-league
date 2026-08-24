# Stage 4 — hosting

**Decided:** Cloudflare Pages for the frontend, Cloud Run for the API, Neon for the
database. Free at this size, no sleeping database, and one origin from the browser's point
of view.

The alternatives were weighed in the roadmap. What settled it: the draft polls every few
seconds from several phones, so anything that sleeps for fifty seconds is disqualified, and
the free tiers here are permanent rather than a twelve-month trial.

---

## How the pieces fit

```mermaid
flowchart LR
    B["Browser<br/><small>phones, laptops</small>"]
    CF["Cloudflare Pages<br/><small>serves dist/<br/>proxies /api/*<br/>never sleeps</small>"]
    CR["Cloud Run<br/><small>FastAPI container<br/>scales to zero</small>"]
    N[("Neon<br/><small>Postgres<br/>auto-suspends</small>")]
    CK["Clerk<br/><small>accounts</small>"]
    P["TMDB · OMDb · MDBList<br/><small>film data</small>"]

    B -->|everything| CF
    CF -->|/api/*| CR
    B -.->|sign in, direct| CK
    CR -->|verify token, JWKS| CK
    CR -->|SQL over TLS| N
    CR -->|ratings, box office| P
```

**The browser talks to one origin.** Pages serves the built `dist/` and forwards `/api/*`
onward, so `api.js` keeps asking for a relative `/api` exactly as it does against the Vite
proxy in development. No code change, and no CORS preflight anywhere.

The dashed line is the one exception. Sign-in goes from the browser straight to Clerk and
never touches the API, which is why a sleeping Cloud Run cannot break signing in.

## Why the draft stays inside the free tier

```mermaid
sequenceDiagram
    participant B as Draft board (6 phones, every 3s)
    participant R as Cloud Run
    B->>R: GET /draft · If-None-Match "a3f9…"
    R-->>B: 304 · no body · nothing changed
    B->>R: GET /draft · If-None-Match "a3f9…"
    R-->>B: 200 + new ETag · someone picked
```

A ninety-minute draft with six people is roughly **11,000 requests**, against a free
allowance in the region of two million a month. Almost all of them take the 304 path: no
body, almost no CPU. Ten drafts a month would still leave the allowance barely touched.

## The cold start, which is the whole downside

Cloud Run and Neon both scale to zero. The first request after a quiet spell waits one to
two seconds while the container starts; every request after that is warm. It lands on
whoever opens the league list first and never during a draft, because a draft keeps the
container busy.

---

## What to set up, in this order

The order matters: each step produces something the next one needs.

### 1. Neon

1. Create a project at [neon.tech](https://neon.tech), region nearest you.
2. Copy the connection string.
3. **Change the scheme** from `postgresql://` to `postgresql+psycopg://` — SQLAlchemy picks
   its driver from that prefix, and the bare form reaches for psycopg2, which is not
   installed.

### 2. Apply the schema, once, from your laptop

Before anything is deployed, and never from inside the container:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://…neon.tech/…' .venv/bin/python -m alembic upgrade head
```

Cloud Run can start several instances at once, and several `alembic upgrade head` racing on
one database is how a schema ends up half-applied.

### 3. Clerk

1. In the Clerk dashboard, copy the **Frontend API URL** — that is `CLERK_ISSUER`.
2. Copy the **Publishable key** — that is `VITE_CLERK_PUBLISHABLE_KEY`.

A development instance works on any origin and is fine for a friend group. A production
instance wants a custom domain, which is the main argument for buying one.

### 4. Cloud Run

```bash
gcloud run deploy movie-league \
  --source backend \
  --region <your-region> \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2
```

`--min-instances 0` is what keeps the bill at zero; setting it to 1 buys away the cold start
and starts the meter. `--max-instances 2` is a ceiling on surprises, not a capacity plan.

Then set the configuration:

```bash
gcloud run services update movie-league --region <your-region> \
  --set-env-vars CLERK_ISSUER=https://…,CORS_ORIGIN=https://…pages.dev \
  --set-secrets DATABASE_URL=movie-league-db:latest,TMDB_API_KEY=tmdb:latest,OMDB_API_KEY=omdb:latest,MDBLIST_API_KEY=mdblist:latest
```

Copy the service URL it prints. That is `API_ORIGIN` for the next step.

### 5. Cloudflare Pages

1. Pages → connect to Git → this repository.
2. **Root directory** `frontend`, build command `npm run build`, output directory `dist`.
3. Environment variables:
   - `API_ORIGIN` — the Cloud Run URL, no trailing slash
   - `VITE_CLERK_PUBLISHABLE_KEY`
   - `VITE_STRIPE_TIP_URL` if you want the tip jar
4. Deploy, then put the resulting `*.pages.dev` URL into Cloud Run's `CORS_ORIGIN`.

### 6. Nightly enrichment, when you want it

Cloud Scheduler, three jobs free, one HTTP call to
`POST /api/leagues/{id}/enrich-all`. Needs a token, so it wants a service identity rather
than a bare cron.

---

## Where each setting lives

Build-time and runtime are not interchangeable, and confusing them is the most common way
this goes wrong. Anything named `VITE_*` is **baked into the bundle when Pages builds it** —
setting one on Cloud Run does nothing at all.

| Setting | Value | Set on |
|---|---|---|
| `DATABASE_URL` | Neon, with the `+psycopg` scheme | Cloud Run secret |
| `CLERK_ISSUER` | Clerk Frontend API URL | Cloud Run env |
| `CORS_ORIGIN` | The Pages URL | Cloud Run env |
| `TMDB_API_KEY`, `OMDB_API_KEY`, `MDBLIST_API_KEY` | provider keys | Cloud Run secret |
| `API_ORIGIN` | The Cloud Run URL | Pages env |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_…` | Pages **build** env |
| `VITE_STRIPE_TIP_URL` | Stripe Payment Link | Pages **build** env |

---

## Two things that will bite

**The container refuses to start without Clerk.** `auth._assert_local_mode_is_safe` will not
boot without an identity provider if either the database or the CORS origin looks like a
deployment. Here both are true, so deploying before `CLERK_ISSUER` is set is a crash loop
rather than an app:

```
Refusing to start: no identity provider is configured, so every request would be
treated as the same single local user, but DATABASE_URL is not SQLite and
CORS_ORIGIN is not a localhost origin.
```

That is the guard working. The alternative was an internet-facing app where every visitor is
the trusted local user.

**Migrate before the first boot, not after.** `init_db()` now returns immediately on
anything but SQLite, so the container will not build a schema behind Alembic's back — but
that means an unmigrated Neon database gives you a container that starts happily and fails
on its first query.

---

## Already prepared in the repo

- `backend/Dockerfile` and `.dockerignore` — listens on `$PORT`, runs uvicorn as PID 1 so
  deploys do not wait out the kill timeout, and does not run migrations.
- `backend/requirements.txt` — `psycopg[binary]` is back, having gone out with PR #16.
- `backend/app/db/session.py` — `init_db()` is SQLite-only, per above.
- `frontend/functions/api/[[path]].js` — the Pages Function that makes everything one
  origin. A `_redirects` rule cannot do this: its 200 rewrites resolve within the site, and
  reaching another host needs a Function.

## Deliberately not done

**No CI deploy step.** Cloudflare Pages already deploys on push once connected. Cloud Run
should stay manual until the first few deploys have been watched by a human.

**Nothing has verified this application on Postgres.** The suite, the smoke test and the
browser tests all run on SQLite. Branch `ci/postgres-parity` carries the job that would
prove it, closed unmerged; it is worth reviving before the first real season rather than
after.

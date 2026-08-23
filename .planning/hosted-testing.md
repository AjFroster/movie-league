# Testing against a hosted database

The worry: once the database lives on Fly or RDS, does a CI run that creates a league on
every pull request start polluting something real?

**No — because CI should never reach the hosted database at all.** The property worth
keeping from today's setup is not SQLite; it is that the database is created inside the
job and destroyed with the runner. That property survives the move to Postgres for free.

---

## The separate-table idea

The instinct is right and the mechanism is the wrong one. A parallel set of tables inside
the production database buys less separation than it looks like it does.

| Approach | Where a wrong connection string lands you | App changes | Migration histories |
|---|---|---|---|
| **Parallel tables** (`test_leagues`, …) | **Production rows.** You are already connected. | table naming in every model | one, written twice |
| **Separate schema** | Production, one `search_path` away | none | one, applied per schema |
| **Separate database, same server** | A different database. Production is unreachable on that connection. | none | one, applied per database |
| **Separate server** | Production is unreachable, full stop | none | one per server |

Three specific problems with parallel tables in this codebase:

- `models.py` hardcodes `__tablename__ = "leagues"`. A parallel set means either duplicate
  model classes or a table-name parameter threaded through — production code that carries
  test-awareness, in the layer where a mistake is most expensive.
- The Alembic revisions target `Base.metadata`. Two table sets means two histories that
  drift, or one that has to be written twice and verified twice. The missing baseline
  revision cost a day already; doubling that surface is the wrong direction.
- **Separation by string prefix is not separation.** A typo writes to `leagues`. The
  connection is still pointed at production, and every constraint that makes this app
  correct — `uq_film_per_league`, the cascades — would have to exist twice and stay in
  step.

**A separate database on the same server costs nothing extra**, needs no application
change (only `DATABASE_URL` moves), keeps one migration history, and can be enforced with
a role rather than a convention:

```sql
CREATE DATABASE league_staging;
CREATE ROLE league_staging LOGIN PASSWORD '…';
GRANT ALL PRIVILEGES ON DATABASE league_staging TO league_staging;
REVOKE CONNECT ON DATABASE league_prod FROM league_staging;   -- the part that matters
```

That last line is what makes it real. With it, a staging process holding a misconfigured
URL cannot read production even if it tries.

---

## The tiers

| Tier | Engine | Database | Identity | Runs |
|---|---|---|---|---|
| Unit and journey suite | SQLite `:memory:` | per test | local | every push |
| **Same suite on Postgres** | **Postgres 16 service container** | **per job, destroyed with the runner** | local | every PR |
| Smoke, browser, multiplayer | SQLite file | per job | local | every PR |
| **Post-deploy smoke** | **hosted Postgres** | **`league_staging`** | Clerk | after each staging deploy |
| Production | hosted Postgres | `league_prod` | Clerk | never written by a test |

Only one tier touches a hosted database, and it is not the per-PR one. A pull request
never creates a league anywhere but inside its own runner.

### Why the smoke and browser tiers stay on SQLite

`auth._assert_local_mode_is_safe` refuses to boot in local-identity mode against a
non-SQLite database. That guard is correct and worth keeping exactly as it is: it is the
thing standing between a misconfigured deploy and an internet-facing app where every
request is the same trusted user.

So those tiers keep SQLite, and the Postgres tier runs the suite in-process where no
server boots. The suite reads `TEST_DATABASE_URL`, a *separate* variable that
`database_url()` never sees — the guard is untouched rather than switched off.

Postgres and SQLite differ in SQL generation, type affinity, transaction isolation and
timezone handling. None of those live in uvicorn or in a browser, so nothing is lost.

---

## The staging tier, when a host is chosen

Deliberately not committed as a dormant workflow — an inert YAML file for an undecided
host is dead code, and this repo's standing rule is that code should speak. What it will
be, though, is short, because the pieces already exist.

**`scripts/smoke_test.py --base-url` already does the whole job.** It drives a real
deployment over HTTP, names every league it creates with `SMOKE_PREFIX`, and deletes them
in a `finally`. `--clean` sweeps anything a crashed run left behind. That is the
namespace-and-sweep pattern already written and already tested.

```yaml
# .github/workflows/deploy-staging.yml — after the deploy step
- name: Smoke the deployment
  working-directory: backend
  env:
    STAGING_URL: ${{ secrets.STAGING_URL }}
  run: python -m scripts.smoke_test --base-url "$STAGING_URL"

- name: Sweep anything a failed run left behind
  if: always()
  working-directory: backend
  env:
    STAGING_URL: ${{ secrets.STAGING_URL }}
  run: python -m scripts.smoke_test --base-url "$STAGING_URL" --clean
```

One thing genuinely missing: the smoke test runs unauthenticated today, which works
because local mode has one implicit user. Against a Clerk-backed staging app it needs a
bearer token — a long-lived test user's session, or a Clerk testing token. **That is the
one piece of new work in this tier**, and it is worth doing there rather than in the
browser tests, because staging is where the real auth path deserves exercising.

### Provisioning

```bash
# Fly.io — one Postgres cluster, two databases
fly postgres connect -a movie-league-db     # then the CREATE DATABASE block above
fly secrets set DATABASE_URL='postgres://league_staging:…@movie-league-db.flycast/league_staging' \
  -a movie-league-staging
```

```bash
# RDS — the same SQL. One instance holds both databases until there is a reason not to.
psql "$ADMIN_URL" -f staging-database.sql
aws secretsmanager create-secret --name league/staging/database-url --secret-string '…'
```

Neither needs a second instance. A second *database* is free; a second *server* is the
thing that costs money, and there is no reason for one until staging load is real.

---

## What is built now

- `psycopg[binary]` in `requirements.txt` — the driver has to exist before a hosted
  database can be pointed at.
- `TEST_DATABASE_URL` in `tests/conftest.py` — one suite, either engine. Postgres gets a
  session-scoped schema and a `TRUNCATE … RESTART IDENTITY CASCADE` per test, so tests
  that assume the first league is id 1 stay true.
- `backend-postgres` in `ci.yml` — the suite on Postgres 16, plus `alembic upgrade head`
  against an empty database and a `compare_metadata` drift check. Non-blocking until it
  has proved itself.
- `scripts/check_schema_drift.py` — asks whether the migrations build what the models
  describe. The suite cannot answer that, because it never runs the migrations.

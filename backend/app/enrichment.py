"""Enrichment engine: cached provider calls, the no-clobber merge, and the per-run call cap.

Deliberately NOT here: any scoring formula. RESEARCH section 3 -- rating_score,
financial_score, penalties, watch_points, and total are hand-entered from the user's
spreadsheet, and storage.compute_leaderboard only sums them. Phase 2 is a data-layer phase
by explicit user decision: enrichment updates imdb / rt_crit / budget / gross / roi and
nothing else, so league standings will not move. compute_movie_scores() is API-06 and is
blocked on the spreadsheet formula.

Layering: services/tmdb.py and services/omdb.py are pure HTTP clients. Caching, budgeting,
provenance, and error normalisation all live here, so there is exactly one place to reason
about "did this run cost an API call?" and "was this write allowed?".
"""
import asyncio
import os

import httpx

from . import provenance
from .redaction import ProviderError, redact_secrets
from .services import cache, omdb, tmdb

DEFAULT_MAX_CALLS = 60      # 30 rows x 2 providers = one full cold run
HARD_MAX_CALLS = 200        # ceiling for a caller-supplied cap; OMDb's free tier is 1,000/day
MAX_CALLS_PER_ENTRY = 2     # single-row enrich: at most one TMDB + one OMDb call
PACING_DELAY_SECONDS = 0.25

OUTCOME_CACHE = "cache"
OUTCOME_FETCHED = "fetched"
OUTCOME_MISS = "miss"
OUTCOME_CAPPED = "capped"
OUTCOME_NO_KEY = "no-key"
OUTCOME_NO_IMDB_ID = "skipped-no-imdb-id"
ERROR_PREFIX = "error: "


class CallBudget:
    """Hard ceiling on outbound provider calls for a single run.

    This is the mechanism behind ROADMAP success criterion 4: one accidental loop must not
    be able to exhaust OMDb's 1,000/day free quota.
    """

    def __init__(self, max_calls: int) -> None:
        self.max_calls = int(max_calls)
        self.used = 0

    def available(self) -> bool:
        return self.used < self.max_calls

    def spend(self) -> None:
        self.used += 1

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_calls


def _error(exc: Exception) -> str:
    """Normalise any provider failure into a redacted, reportable string."""
    return f"{ERROR_PREFIX}{redact_secrets(str(exc))}"


async def fetch_tmdb(title: str, *, budget: CallBudget, force: bool = False,
                     client: httpx.AsyncClient | None = None) -> tuple[dict | None, str]:
    """Cache-first TMDB lookup. Returns (payload, outcome)."""
    # Check the key first: tmdb returns None both for "no key" and for "no match", and
    # negative-caching a keyless run would blind the app for 24h after the key is added.
    if not os.environ.get("TMDB_API_KEY"):
        return None, OUTCOME_NO_KEY

    key = cache.make_key("tmdb", title=title)
    if not force:
        entry = cache.get(key)
        if entry is not None:
            return entry.get("payload"), OUTCOME_CACHE

    if not budget.available():
        return None, OUTCOME_CAPPED
    budget.spend()

    try:
        payload = await tmdb.fetch_movie_financials(title, client=client)
    except (httpx.HTTPError, ProviderError, ValueError) as e:
        return None, _error(e)

    cache.put(key, payload,
              cache.ttl_for((payload or {}).get("release_date"), matched=payload is not None))
    return payload, OUTCOME_FETCHED if payload else OUTCOME_MISS


async def fetch_omdb(imdb_id: str, *, release_date: str | None, budget: CallBudget,
                     force: bool = False,
                     client: httpx.AsyncClient | None = None) -> tuple[dict | None, str]:
    """Cache-first OMDb lookup, keyed on the exact IMDb ID TMDB supplied.

    `release_date` comes from the TMDB payload -- OMDb is not asked for it, and the two
    providers' entries for the same film should expire on the same schedule.
    """
    if not os.environ.get("OMDB_API_KEY"):
        return None, OUTCOME_NO_KEY

    key = cache.make_key("omdb", imdb_id=imdb_id)
    if not force:
        entry = cache.get(key)
        if entry is not None:
            return entry.get("payload"), OUTCOME_CACHE

    if not budget.available():
        return None, OUTCOME_CAPPED
    budget.spend()

    try:
        payload = await omdb.fetch_ratings(imdb_id, client=client)
    except (httpx.HTTPError, ProviderError, ValueError) as e:
        return None, _error(e)

    cache.put(key, payload, cache.ttl_for(release_date, matched=payload is not None))
    return payload, OUTCOME_FETCHED if payload else OUTCOME_MISS


def compute_roi(entry: dict, *, force: bool = False) -> bool:
    """roi = gross / budget, subject to the same no-clobber rule as every other field.

    Supersedes main.py's `_compute_roi`, which wrote unconditionally.
    """
    budget_m, gross_m = entry.get("budget"), entry.get("gross")
    if isinstance(budget_m, bool) or isinstance(gross_m, bool):
        return False
    if not isinstance(budget_m, (int, float)) or not isinstance(gross_m, (int, float)):
        return False
    if budget_m <= 0:
        return False
    if not provenance.can_write(entry, "roi", force=force):
        return False
    entry["roi"] = round(gross_m / budget_m, 3)
    provenance.set_source(entry, "roi", provenance.FETCHED, provider="derived")
    return True


async def enrich_entry(entry: dict, *, budget: CallBudget, force: bool = False,
                       tmdb_client: httpx.AsyncClient | None = None,
                       omdb_client: httpx.AsyncClient | None = None) -> dict:
    """Merge provider data into `entry` in place. Returns a per-row report."""
    report = {
        "owner": entry.get("owner"), "round": entry.get("round"), "movie": entry.get("movie"),
        "tmdb": "", "omdb": "", "updated": [], "protected": [], "errors": [],
    }

    financials, report["tmdb"] = await fetch_tmdb(
        entry.get("movie") or "", budget=budget, force=force, client=tmdb_client)
    if report["tmdb"].startswith(ERROR_PREFIX):
        report["errors"].append(report["tmdb"])

    imdb_id = (financials or {}).get("imdb_id")
    release_date = (financials or {}).get("release_date")
    if imdb_id:
        ratings, report["omdb"] = await fetch_omdb(
            imdb_id, release_date=release_date, budget=budget, force=force, client=omdb_client)
        if report["omdb"].startswith(ERROR_PREFIX):
            report["errors"].append(report["omdb"])
    else:
        ratings, report["omdb"] = None, OUTCOME_NO_IMDB_ID

    # `imdb` is sourced from OMDb's imdbRating ONLY. TMDB's vote_average is a different
    # number on the same 0-10 scale (HANDOFF.md line 43) and is never written here.
    candidates = (
        ("budget", (financials or {}).get("budget_millions"), "tmdb"),
        ("gross", (financials or {}).get("gross_millions"), "tmdb"),
        ("imdb", (ratings or {}).get("imdb"), "omdb"),
        ("rt_crit", (ratings or {}).get("rt_crit"), "omdb"),
    )
    for field, value, provider in candidates:
        if value is None:
            continue
        if provenance.apply_fetched(entry, field, value, provider=provider, force=force):
            report["updated"].append(field)
        else:
            report["protected"].append(field)

    if compute_roi(entry, force=force):
        report["updated"].append("roi")

    return report


async def enrich_all(data: dict, *, force: bool = False, max_calls: int = DEFAULT_MAX_CALLS,
                     delay: float = PACING_DELAY_SECONDS, sleep=asyncio.sleep,
                     tmdb_client: httpx.AsyncClient | None = None,
                     omdb_client: httpx.AsyncClient | None = None) -> dict:
    """Enrich every row in `data["movies"]` in place and return a run summary.

    Rows are processed strictly sequentially with a delay between them -- concurrency (a
    fan-out that gathers every row's coroutine at once) is never used here. That, plus the
    CallBudget, is the rate discipline from RESEARCH section 5: a bulk run is bounded both
    in requests-per-second and in total requests, so it cannot exhaust OMDb's 1,000/day
    free quota by accident.

    `sleep` is injectable purely so tests can assert the pacing happened without actually
    waiting; production callers use the default.
    """
    budget = CallBudget(max_calls)
    reports = []
    for entry in data.get("movies", []):
        reports.append(await enrich_entry(
            entry, budget=budget, force=force,
            tmdb_client=tmdb_client, omdb_client=omdb_client))
        await sleep(delay)
    return {
        "movies_processed": len(reports),
        "api_calls_used": budget.used,
        "max_calls": budget.max_calls,
        "cap_reached": budget.exhausted,
        "forced": force,
        "fields_updated": sum(len(r["updated"]) for r in reports),
        "fields_protected": sum(len(r["protected"]) for r in reports),
        "errors": [e for r in reports for e in r["errors"]],
        "reports": reports,
    }

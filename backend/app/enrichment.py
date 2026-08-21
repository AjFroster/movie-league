"""Enrichment engine: cached provider calls, the no-clobber merge, and the per-run call cap.

Deliberately NOT here: the scoring formula, which lives in scoring.py. This module's job
ends at populating imdb / rt_crit / budget / gross / roi; callers recompute scores from
those values afterwards. Keeping the two apart means enrichment can be tested without
reasoning about scoring, and the formula can change without touching provider code.

Layering: services/tmdb.py and services/omdb.py are pure HTTP clients. Caching, budgeting,
provenance, and error normalisation all live here, so there is exactly one place to reason
about "did this run cost an API call?" and "was this write allowed?".
"""
import asyncio
import os
import re

import httpx

from . import provenance
from .redaction import ProviderError, redact_secrets
from .services import cache, mdblist, omdb, tmdb

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


async def fetch_mdblist(imdb_id: str, *, release_date: str | None, budget: CallBudget,
                        force: bool = False,
                        client: httpx.AsyncClient | None = None) -> tuple[dict | None, str]:
    """Cache-first MDBList lookup, keyed on the exact IMDb ID TMDB supplied."""
    if not os.environ.get("MDBLIST_API_KEY"):
        return None, OUTCOME_NO_KEY

    key = cache.make_key("mdblist", imdb_id=imdb_id)
    if not force:
        entry = cache.get(key)
        if entry is not None:
            return entry.get("payload"), OUTCOME_CACHE

    if not budget.available():
        return None, OUTCOME_CAPPED
    budget.spend()

    try:
        payload = await mdblist.fetch_ratings(imdb_id, client=client)
    except (httpx.HTTPError, ProviderError, ValueError) as e:
        return None, _error(e)

    cache.put(key, payload, cache.ttl_for(release_date, matched=payload is not None))
    return payload, OUTCOME_FETCHED if payload else OUTCOME_MISS


def _norm(title: str | None) -> str:
    """Loose title key for match comparison: case, spacing and punctuation insensitive."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


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
    value = round(gross_m / budget_m, 3)
    # No-op guard: re-deriving the identical value is not an update. Without this, a
    # keyless run (zero API calls, nothing fetched) still rewrites league_data.json for
    # every row that already has budget/gross -- churning provenance timestamps and
    # relabelling `unknown` as `fetched`, which asserts an origin we cannot actually know.
    # Skip only once a provenance record exists, so a first pass still stamps one and
    # every run after that is a true no-op.
    if not force and entry.get("roi") == value and provenance.get_source(entry, "roi"):
        return False
    entry["roi"] = value
    provenance.set_source(entry, "roi", provenance.FETCHED, provider="derived")
    return True


async def enrich_entry(entry: dict, *, budget: CallBudget, force: bool = False,
                       tmdb_client: httpx.AsyncClient | None = None,
                       omdb_client: httpx.AsyncClient | None = None,
                       mdblist_client: httpx.AsyncClient | None = None) -> dict:
    """Merge provider data into `entry` in place. Returns a per-row report."""
    report = {
        "owner": entry.get("owner"), "round": entry.get("round"), "movie": entry.get("movie"),
        "tmdb": "", "omdb": "", "mdblist": "", "matched_title": None,
        "updated": [], "protected": [], "errors": [],
    }

    # A round with no pick yet is normal mid-season. Without this guard the empty title
    # reaches cache.make_key, which raises ValueError and 500s the entire bulk run over one
    # blank row.
    if not (entry.get("movie") or "").strip():
        report["tmdb"] = report["omdb"] = "skipped-no-title"
        return report

    financials, report["tmdb"] = await fetch_tmdb(
        entry.get("movie") or "", budget=budget, force=force, client=tmdb_client)
    if report["tmdb"].startswith(ERROR_PREFIX):
        report["errors"].append(report["tmdb"])

    report["matched_title"] = (financials or {}).get("title")
    # Passed back on the document so the store can persist them; they are identity and
    # artwork rather than scoring inputs, so they bypass the no-clobber rule.
    if financials:
        entry.setdefault("tmdb_id", None)
        entry["tmdb_id"] = entry.get("tmdb_id") or financials.get("tmdb_id")
        if financials.get("poster_path"):
            entry["poster_path"] = financials["poster_path"]

    imdb_id = (financials or {}).get("imdb_id")
    release_date = (financials or {}).get("release_date")
    ratings: dict = {}
    if imdb_id:
        # MDBList first: it carries all four rating inputs, where OMDb has no Letterboxd or
        # RT audience score at all and only patchy RT critics on recent releases.
        primary, report["mdblist"] = await fetch_mdblist(
            imdb_id, release_date=release_date, budget=budget, force=force,
            client=mdblist_client)
        if report["mdblist"].startswith(ERROR_PREFIX):
            report["errors"].append(report["mdblist"])
        ratings.update(primary or {})

        # OMDb is a fallback, not a second opinion: it is only called when MDBList left one
        # of the fields it can supply empty, so a complete MDBList response costs no extra
        # request and MDBList's value is never overwritten by OMDb's.
        if not all(ratings.get(f) is not None for f in ("imdb", "rt_crit")):
            secondary, report["omdb"] = await fetch_omdb(
                imdb_id, release_date=release_date, budget=budget, force=force,
                client=omdb_client)
            if report["omdb"].startswith(ERROR_PREFIX):
                report["errors"].append(report["omdb"])
            for field, value in (secondary or {}).items():
                ratings.setdefault(field, value)
        else:
            report["omdb"] = "skipped-mdblist-complete"
    else:
        report["mdblist"] = report["omdb"] = OUTCOME_NO_IMDB_ID

    # `imdb` is the real IMDb rating from MDBList or OMDb. TMDB's vote_average is a
    # different number on the same 0-10 scale (HANDOFF.md line 43) and is never written.
    ratings_provider = "mdblist" if report["mdblist"] in (OUTCOME_FETCHED, OUTCOME_CACHE) else "omdb"
    candidates = (
        ("budget", (financials or {}).get("budget_millions"), "tmdb"),
        ("gross", (financials or {}).get("gross_millions"), "tmdb"),
        ("imdb", ratings.get("imdb"), ratings_provider),
        ("rt_crit", ratings.get("rt_crit"), ratings_provider),
        ("rt_aud", ratings.get("rt_aud"), ratings_provider),
        ("letterboxd", ratings.get("letterboxd"), ratings_provider),
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
        # Rows TMDB could not match are the ones needing a human: either the title differs
        # from TMDB's ("Super Girl" vs "Supergirl") or every hit predates the season floor.
        # They are left untouched, so surfacing them here is the only signal you get --
        # without this you would have to scan every per-row report to find them.
        "unmatched": [{"owner": r["owner"], "round": r["round"], "movie": r["movie"]}
                      for r in reports if r["tmdb"] == "miss" and r["movie"]],
        # Matches whose TMDB title differs from the entered one. Most are benign and
        # correct ("Dune Part 3" -> "Dune: Part Three"), but this is also where a genuine
        # mis-match hides: the query "Werewolf" matched the unrelated "Werewolf Game".
        # Requiring exact titles would reject 9 correct matches to catch that 1, so these
        # are flagged for a human glance rather than rejected.
        "review": [{"owner": r["owner"], "round": r["round"], "movie": r["movie"],
                    "matched_title": r["matched_title"]}
                   for r in reports
                   if r["matched_title"] and _norm(r["matched_title"]) != _norm(r["movie"])],
        "errors": [e for r in reports for e in r["errors"]],
        "reports": reports,
    }

"""The draftable movie pool: a year's most anticipated theatrical releases, from TMDB.

"Every movie coming out in 2026" is 31,065 titles once you count every short, festival entry
and regional release -- not a board anyone can draft from. The pool is therefore the top N by
TMDB popularity, which surfaces the films a league would actually argue over.

Popularity is used as a *ranking*, never as a threshold: the scale is not comparable across
years, because films still years out have barely any marketing behind them. In August 2026
the top 2026 film scored 1819 and the top 2027 film scored 22. A cutoff tuned to one year
would empty the other. Vote count is worse still -- unreleased films have none, so filtering
on it returns nothing at all for a future year.
"""
import os
import time
from threading import Lock

import httpx

from ..redaction import ProviderError, redact_secrets

TMDB_BASE = "https://api.themoviedb.org/3"
PAGE_SIZE = 20                 # TMDB's fixed discover page size
DEFAULT_POOL_SIZE = 300
MAX_POOL_SIZE = 500
# 3 = theatrical, 2 = limited theatrical. Excludes the direct-to-streaming long tail that
# makes up most of the 31k.
RELEASE_TYPES = "2|3"
# w185 is the smallest TMDB size that still reads as a poster in a list row. The full URL
# is built here rather than in the client so the CDN host lives in one place.
IMAGE_BASE = "https://image.tmdb.org/t/p/w185"

# A 500-film pool is 25 TMDB requests, so one HTTP call to this server can cost 25 upstream.
# Public leagues make `/{id}/pool` reachable signed-out by design, which leaves that
# amplification open to anyone. Caching bounds it: a repeat ask for a year costs nothing.
#
# In process rather than the JSON cache the enrichment path uses. That file is read and
# rewritten whole on every get, and a 300-film pool living in it would slow down every
# per-film lookup that shares it. The cost is that a reload empties this -- acceptable for
# TMDB discover, which is rate-limited rather than capped like OMDb's daily budget.
POOL_TTL = 6 * 3600            # the popularity ranking moves over weeks, not hours
_POOL_BUCKET = 100
_pool_cache: dict[tuple[int, int], tuple[float, list[dict]]] = {}
_pool_lock = Lock()


def _bucket(size: int) -> int:
    """Round a requested size up to the next 100.

    Keying on the exact size would let a caller walk size=1..500 and miss every time, which
    is the amplification the cache exists to stop. Five buckets a year is a bound.
    """
    return min(MAX_POOL_SIZE, -(-max(1, size) // _POOL_BUCKET) * _POOL_BUCKET)


def _cached(year: int, size: int) -> list[dict] | None:
    with _pool_lock:
        entry = _pool_cache.get((year, size))
    if entry is None or time.time() - entry[0] >= POOL_TTL:
        return None
    return entry[1]


def _remember(year: int, size: int, films: list[dict]) -> None:
    with _pool_lock:
        _pool_cache[(year, size)] = (time.time(), films)


def clear_cache() -> None:
    """Drop everything. For tests, and for anyone who needs a year re-fetched now."""
    with _pool_lock:
        _pool_cache.clear()


def _api_key() -> str | None:
    return os.environ.get("TMDB_API_KEY")


def summarize(result: dict) -> dict | None:
    """Trim a TMDB discover result to what a draft board needs."""
    # `is None` rather than falsiness: an id of 0 is a valid integer, and dropping it
    # silently would remove a film from the board with no trace.
    if not isinstance(result, dict):
        return None
    if result.get("id") is None or not str(result.get("title") or "").strip():
        return None
    return {
        "tmdb_id": result["id"],
        "title": result["title"],
        "release_date": result.get("release_date") or None,
        "poster_path": result.get("poster_path") or None,
        "poster_url": (f"{IMAGE_BASE}{result['poster_path']}"
                       if result.get("poster_path") else None),
        "overview": (result.get("overview") or "")[:400] or None,
        "popularity": round(result.get("popularity") or 0, 1),
    }


async def fetch_pool(year: int, *, size: int = DEFAULT_POOL_SIZE,
                     client: httpx.AsyncClient | None = None) -> list[dict]:
    """The `size` most popular theatrical releases of `year`, most anticipated first.

    Returns [] when no API key is configured, matching the other providers: no key and no
    results are both "nothing to show", and the caller decides how to say so.
    """
    key = _api_key()
    if not key:
        return []
    if not isinstance(year, int) or not (1900 <= year <= 2100):
        raise ValueError(f"implausible year: {year!r}")
    size = max(1, min(int(size), MAX_POOL_SIZE))
    # Fetch and cache a whole bucket, then hand back the slice that was asked for.
    want = _bucket(size)
    cached = _cached(year, want)
    if cached is not None:
        return cached[:size]

    headers = {"Authorization": f"Bearer {key}"}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=20)
    films: list[dict] = []
    seen: set[int] = set()
    try:
        pages = -(-want // PAGE_SIZE)          # ceiling division
        for page in range(1, pages + 1):
            response = await client.get(
                f"{TMDB_BASE}/discover/movie",
                params={"primary_release_year": year, "sort_by": "popularity.desc",
                        "with_release_type": RELEASE_TYPES, "page": page,
                        "language": "en-US"},
                headers=headers)
            response.raise_for_status()
            results = response.json().get("results") or []
            if not results:
                break                           # ran past the end of the catalogue
            for raw in results:
                film = summarize(raw)
                # TMDB can repeat a title across pages when popularity shifts mid-walk;
                # a duplicate in the pool would be draftable twice.
                if film and film["tmdb_id"] not in seen:
                    seen.add(film["tmdb_id"])
                    films.append(film)
    except httpx.HTTPError as e:
        raise ProviderError(f"tmdb discover failed: {redact_secrets(str(e))}") from None
    finally:
        if owns_client:
            await client.aclose()

    # Not under the lock: a threading lock must not be held across an await, and two
    # requests racing on a cold year cost one duplicate fetch, not a correctness problem.
    _remember(year, want, films[:want])
    return films[:size]


async def search(query: str, *, year: int | None = None, limit: int = 20,
                 client: httpx.AsyncClient | None = None) -> list[dict]:
    """Title search, so a deep cut outside the top N is still draftable."""
    key = _api_key()
    if not key or not (query or "").strip():
        return []

    headers = {"Authorization": f"Bearer {key}"}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        params = {"query": query.strip(), "language": "en-US", "page": 1}
        if year:
            params["primary_release_year"] = year
        response = await client.get(f"{TMDB_BASE}/search/movie", params=params,
                                    headers=headers)
        response.raise_for_status()
        films = [f for f in (summarize(r) for r in response.json().get("results") or []) if f]
        return films[:limit]
    except httpx.HTTPError as e:
        raise ProviderError(f"tmdb search failed: {redact_secrets(str(e))}") from None
    finally:
        if owns_client:
            await client.aclose()

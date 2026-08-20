"""Persistent JSON cache for outbound provider calls (TMDB, OMDb).

Why a file and not an in-process dict: the dict is lost on every `uvicorn --reload`,
which would re-burn OMDb's 1,000/day free quota on each restart. Why not SQLite: this is
a ~60-entry key/value store, and the project's entire storage model is already
"flat JSON file + threading.Lock + atomic os.replace" (app/storage.py). This module
reuses that exact pattern rather than introducing a second persistence style.

One deliberate divergence from app/storage.py: a missing or corrupt cache file is NOT an
error here. league_data.json is the source of truth, so storage.load_data() raises 503
when it cannot be read. This cache is disposable derived data, so load_cache() returns {}
and the caller simply re-fetches. Failing closed on a cache would take the API down for
no reason.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "api_cache.json"
_lock = Lock()

TTL_RELEASED = 30 * 24 * 3600  # released > 1 year ago: financials final, ratings stable
TTL_RECENT = 7 * 24 * 3600     # released within the last year: still moving
TTL_NEGATIVE = 24 * 3600       # no match, unreleased, or undated: negative cache

STATUS_HIT = "hit"
STATUS_MISS = "miss"

_RECENT_WINDOW_DAYS = 365


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _normalize_title(title: str) -> str:
    return " ".join(str(title).lower().split())


def make_key(provider: str, *, imdb_id: str | None = None,
             title: str | None = None, year: int | None = None) -> str:
    """`{provider}:{imdb_id}` when an IMDb ID is known (stable and exact), otherwise
    `{provider}:title:{normalized title}:{year or empty}`."""
    if imdb_id:
        return f"{provider}:{imdb_id}"
    if not title:
        raise ValueError("make_key requires either imdb_id or title")
    return f"{provider}:title:{_normalize_title(title)}:{year if year is not None else ''}"


def ttl_for(release_date: str | None, *, matched: bool) -> int:
    """Tiered TTL from RESEARCH section 5. Unmatched, unreleased, or undated entries all
    get the 24h negative TTL so they are retried tomorrow rather than in a month."""
    if not matched or not release_date:
        return TTL_NEGATIVE
    try:
        released = datetime.strptime(str(release_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return TTL_NEGATIVE
    days = (datetime.now(tz=timezone.utc) - released).days
    if days < 0:
        return TTL_NEGATIVE
    if days > _RECENT_WINDOW_DAYS:
        return TTL_RELEASED
    return TTL_RECENT


def load_cache() -> dict:
    """Read the whole cache. Missing or corrupt file -> {} (see module docstring)."""
    with _lock:
        try:
            with open(CACHE_PATH, "r") as f:
                loaded = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
    return loaded if isinstance(loaded, dict) else {}


def save_cache(cache: dict) -> None:
    """Atomic write, same pattern as app/storage.save_data."""
    with _lock:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
        os.replace(tmp, CACHE_PATH)


def get(key: str, *, now: float | None = None) -> dict | None:
    """Return the cache entry if present and unexpired, else None.

    A returned entry with `payload is None` and `status == "miss"` is a *negative* cache
    hit -- the provider was asked and had nothing. Callers must treat that differently
    from a None return, which means "never asked, or the answer expired".
    """
    entry = load_cache().get(key)
    if not isinstance(entry, dict):
        return None
    ts = _now() if now is None else now
    try:
        fetched_at = datetime.fromisoformat(entry["fetched_at"]).timestamp()
        ttl = float(entry["ttl_seconds"])
    except (KeyError, TypeError, ValueError):
        return None
    if ts - fetched_at >= ttl:
        return None
    return entry


def put(key: str, payload: dict | None, ttl_seconds: int, *, now: float | None = None) -> dict:
    """Write an entry. `payload=None` records a negative (miss) result."""
    ts = _now() if now is None else now
    entry = {
        "fetched_at": _iso(ts),
        "expires_at": _iso(ts + ttl_seconds),
        "ttl_seconds": int(ttl_seconds),
        "status": STATUS_HIT if payload else STATUS_MISS,
        "payload": payload,
    }
    cache = load_cache()
    cache[key] = entry
    save_cache(cache)
    return entry

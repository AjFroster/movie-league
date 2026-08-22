"""MDBList: the only free source that carries all four of the league's rating inputs.

OMDb supplies the real IMDb rating and, patchily, a Rotten Tomatoes critic score -- on this
league's 2026 slate it returned RT for roughly a third of the films and never an audience
score or a Letterboxd rating at all. MDBList aggregates imdb, letterboxd, tomatoes (critics)
and popcorn (audience) into one response, and covered every rated film in the league.

Free tier is 1,000 requests/day, which is ample for a 30-film league fetched behind a cache.
Get a key from https://mdblist.com Preferences and set MDBLIST_API_KEY.

Like OMDb, MDBList authenticates by query parameter, so its key travels in the URL and any
unredacted error text would leak it. Every failure here raises a redacted ProviderError.
"""
import math
import os
import re

import httpx

from ..redaction import ProviderError, redact_secrets

MDBLIST_BASE = "https://api.mdblist.com"
IMDB_ID_RE = re.compile(r"^tt\d{7,10}$")

# MDBList's source names for the four inputs the league scores on. "popcorn" is Rotten
# Tomatoes' audience popcornmeter -- not an obvious name, hence the mapping.
SOURCE_MAP = {
    "imdb": "imdb",
    "letterboxd": "letterboxd",
    "tomatoes": "rt_crit",
    "popcorn": "rt_aud",
}

# Plausible ranges per field. A value outside these is a schema surprise, not data, and is
# dropped rather than written into the league file.
FIELD_RANGES = {
    "imdb": (0.0, 10.0),
    "letterboxd": (0.0, 5.0),
    "rt_crit": (0.0, 100.0),
    "rt_aud": (0.0, 100.0),
}


def _api_key() -> str | None:
    return os.environ.get("MDBLIST_API_KEY")


def _clean(field: str, value) -> float | None:
    """Coerce a rating to a float inside its expected range, else None."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value):                      # NaN
        return None
    low, high = FIELD_RANGES[field]
    if not (low <= value <= high):
        return None
    return round(float(value), 2)


def parse_mdblist_payload(data) -> dict | None:
    """Pull the four league inputs out of an MDBList response.

    Returns None when the payload carries no usable rating at all, so the caller can cache
    it as a negative result rather than storing a row of nulls.
    """
    if not isinstance(data, dict):
        return None
    out: dict[str, float] = {}
    for entry in data.get("ratings") or []:
        if not isinstance(entry, dict):
            continue
        field = SOURCE_MAP.get(entry.get("source"))
        if field is None:
            continue
        cleaned = _clean(field, entry.get("value"))
        if cleaned is not None:
            out[field] = cleaned
    return out or None


async def fetch_ratings(imdb_id: str, *,
                        client: httpx.AsyncClient | None = None) -> dict | None:
    """Ratings for one IMDb ID, or None for "no key" / "no record" / "nothing rated yet".

    Raises ValueError for a malformed IMDb ID and ProviderError for any transport or HTTP
    failure, always with the key redacted and with `from None` so the original exception --
    which carries the unredacted URL -- cannot surface through traceback chaining.
    """
    if not isinstance(imdb_id, str) or not IMDB_ID_RE.match(imdb_id):
        raise ValueError(f"malformed IMDb ID: {imdb_id!r}")

    key = _api_key()
    if not key:
        return None

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        response = await client.get(f"{MDBLIST_BASE}/imdb/movie/{imdb_id}",
                                    params={"apikey": key})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return parse_mdblist_payload(response.json())
    except httpx.HTTPError as e:
        raise ProviderError(f"mdblist request failed: {redact_secrets(str(e))}") from None
    except ValueError as e:
        # json() on a non-JSON body. The response text may echo the query string.
        raise ProviderError(f"mdblist returned invalid JSON: {redact_secrets(str(e))}") from None
    finally:
        if owns_client:
            await client.aclose()

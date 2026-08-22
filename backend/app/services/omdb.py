"""OMDb lookups for the IMDb rating and the Rotten Tomatoes critic score.

Free key (1,000/day) at https://www.omdbapi.com/apikey.aspx as OMDB_API_KEY. Returns None
with no key configured, so the app keeps working on hand-entered data.

Two things here are security-load-bearing:

1. Lookup is by IMDb ID, never by title. A fuzzy title match could silently attach another
   film's ratings to a row, so it is designed out rather than mitigated.
2. OMDb has no header auth, so the key rides in the query string and httpx embeds the full
   URL in its exceptions. Every failure path raises ProviderError (redacted in __init__)
   with `from None`, so the unredacted original is never chained into the traceback.

`gross` deliberately comes from TMDB instead: OMDb's BoxOffice is domestic-US only.
"""
import math
import os
import re

import httpx

from ..redaction import ProviderError

OMDB_BASE = "https://www.omdbapi.com/"
IMDB_ID_RE = re.compile(r"^tt\d{7,10}$")
RT_SOURCE_NAME = "Rotten Tomatoes"
_TIMEOUT_SECONDS = 10


def _api_key() -> str | None:
    return os.environ.get("OMDB_API_KEY")


def _parse_rating_10(value) -> float | None:
    """'9.3' -> 9.3. 'N/A', None, bools, non-scalars, NaN, or anything outside 0-10 -> None."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        rating = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(rating) or not (0.0 <= rating <= 10.0):
        return None
    return round(rating, 1)


def _parse_percent(value) -> float | None:
    """'89%' -> 89.0. Unparseable, NaN, or outside 0-100 -> None."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        percent = float(str(value).strip().rstrip("%").strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(percent) or not (0.0 <= percent <= 100.0):
        return None
    return round(percent, 1)


def _extract_rt_crit(ratings) -> float | None:
    """Pull the Rotten Tomatoes critic percentage out of OMDb's Ratings[] array."""
    if not isinstance(ratings, list):
        return None
    for item in ratings:
        if isinstance(item, dict) and item.get("Source") == RT_SOURCE_NAME:
            return _parse_percent(item.get("Value"))
    return None


def parse_omdb_payload(data) -> dict | None:
    """Pure translation of an OMDb response body into our field names.

    Kept separate from the HTTP call so the whole parse matrix is testable with zero
    network and no API key. Every value is type- and range-checked here, because this is
    the boundary where untrusted third-party JSON becomes data we write into
    league_data.json.
    """
    if not isinstance(data, dict) or data.get("Response") != "True":
        return None
    imdb_id = data.get("imdbID")
    return {
        "imdb_id": imdb_id if isinstance(imdb_id, str) and IMDB_ID_RE.match(imdb_id) else None,
        "imdb": _parse_rating_10(data.get("imdbRating")),
        "rt_crit": _extract_rt_crit(data.get("Ratings")),
    }


async def fetch_ratings(imdb_id: str, *, client: httpx.AsyncClient | None = None) -> dict | None:
    """Return {'imdb_id', 'imdb', 'rt_crit'} for an IMDb ID, or None.

    None means either "no API key configured" or "OMDb has no record" -- both are cached by
    the caller as a negative result. Raises ValueError for a malformed IMDb ID and
    ProviderError (message already redacted) for any transport or HTTP failure.

    `client` exists for dependency injection in tests; production callers omit it.
    """
    if not isinstance(imdb_id, str) or not IMDB_ID_RE.match(imdb_id):
        raise ValueError(f"invalid IMDb id: {imdb_id!r}")

    key = _api_key()
    if not key:
        return None

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    try:
        response = await client.get(OMDB_BASE, params={"i": imdb_id, "apikey": key})
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise ProviderError(str(e), provider="omdb") from None
    except ValueError as e:
        raise ProviderError(f"omdb returned a non-JSON body: {e}", provider="omdb") from None
    finally:
        if owns_client:
            await client.aclose()

    return parse_omdb_payload(data)

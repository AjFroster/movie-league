"""
TMDB lookups for the fields that DO have a public API: budget, gross (revenue), the
release_date that feeds the cache's TTL tiering, and the imdb_id that services/omdb.py
uses to fetch the real IMDb rating and Rotten Tomatoes critic score by exact ID.

Get a free API key at https://www.themoviedb.org/settings/api and set it as
the TMDB_API_KEY environment variable. Until a key is set, these functions
return None so the rest of the app keeps working with manually-entered data.
"""
import os
import re
from decimal import ROUND_HALF_UP, Decimal

import httpx

TMDB_BASE = "https://api.themoviedb.org/3"
_IMDB_ID_RE = re.compile(r"^tt\d{7,10}$")
_RELEASE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _api_key() -> str | None:
    return os.environ.get("TMDB_API_KEY")


def _millions(value) -> float | None:
    """Raw dollars -> millions, matching the spreadsheet's units. 0/negative/bad -> None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value <= 0:
        return None
    return round(value / 1_000_000, 2)


def _vote_average(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or not (0.0 < value <= 10.0):
        return None
    # Plain round(value, 1) uses banker's rounding on the *binary* float, which
    # mis-rounds e.g. 7.35 -> 7.3 instead of 7.4 because 7.35 is not exactly
    # representable in binary floating point (it is actually ~7.349999999999996).
    # Decimal(str(value)) recovers the intended decimal digits before rounding.
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _imdb_id(value) -> str | None:
    return value if isinstance(value, str) and _IMDB_ID_RE.match(value) else None


def _release_date(value) -> str | None:
    """TMDB sends "" for unreleased films; the cache needs None to pick its 24h TTL tier."""
    return value if isinstance(value, str) and _RELEASE_DATE_RE.match(value) else None


async def fetch_movie_financials(title: str, year: int | None = None, *,
                                 client: httpx.AsyncClient | None = None) -> dict | None:
    """Search TMDB for a title and return budget/gross/release_date/imdb_id if found.

    Returns None if no API key is configured or no match is found.
    Budget/revenue from TMDB are in raw dollars; we convert to millions to
    match the spreadsheet's existing units.

    `client` exists for dependency injection in tests; production callers omit it.
    """
    key = _api_key()
    if not key:
        return None

    headers = {"Authorization": f"Bearer {key}"}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        params = {"query": title}
        if year:
            params["year"] = year
        search = await client.get(f"{TMDB_BASE}/search/movie", params=params, headers=headers)
        search.raise_for_status()
        results = search.json().get("results", [])
        if not results:
            return None

        movie_id = results[0]["id"]
        details = await client.get(f"{TMDB_BASE}/movie/{movie_id}", headers=headers)
        details.raise_for_status()
        d = details.json()

        return {
            "tmdb_id": movie_id,
            "budget_millions": _millions(d.get("budget")),
            "gross_millions": _millions(d.get("revenue")),
            # WARNING: vote_average is TMDB's community rating, NOT the IMDb rating. It is
            # returned for reference only. Writing it into the `imdb` field is the accuracy
            # bug recorded in HANDOFF.md line 43; `imdb` is sourced from omdb.py.
            "vote_average": _vote_average(d.get("vote_average")),
            "imdb_id": _imdb_id(d.get("imdb_id")),
            "release_date": _release_date(d.get("release_date")),
        }
    finally:
        if owns_client:
            await client.aclose()

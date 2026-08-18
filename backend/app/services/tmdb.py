"""
TMDB lookups for the fields that DO have a public API: IMDb rating (via
TMDB's external_ids + a secondary OMDb call, or TMDB's own vote_average),
budget, and gross (revenue).

Get a free API key at https://www.themoviedb.org/settings/api and set it as
the TMDB_API_KEY environment variable. Until a key is set, these functions
return None so the rest of the app keeps working with manually-entered data.
"""
import os
import httpx

TMDB_BASE = "https://api.themoviedb.org/3"


def _api_key() -> str | None:
    return os.environ.get("TMDB_API_KEY")


async def fetch_movie_financials(title: str, year: int | None = None) -> dict | None:
    """Search TMDB for a title and return budget/gross (in millions) if found.

    Returns None if no API key is configured or no match is found.
    Budget/revenue from TMDB are in raw dollars; we convert to millions to
    match the spreadsheet's existing units.
    """
    key = _api_key()
    if not key:
        return None

    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=10) as client:
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

        budget = d.get("budget") or 0
        revenue = d.get("revenue") or 0
        vote_avg = d.get("vote_average")
        return {
            "tmdb_id": movie_id,
            "budget_millions": round(budget / 1_000_000, 2) if budget else None,
            "gross_millions": round(revenue / 1_000_000, 2) if revenue else None,
            "vote_average": round(vote_avg, 1) if vote_avg else None,
            "imdb_id": d.get("imdb_id"),
        }

"""Placeholder for the two rating fields that still have no free API.

As of Phase 2, `rt_crit` (Rotten Tomatoes CRITIC score) is fetched for real by
services/omdb.py -- OMDb exposes it in its Ratings[] array. What remains genuinely
unavailable is the Rotten Tomatoes AUDIENCE score and the Letterboxd rating: Letterboxd's
API is request-only with no guaranteed approval, and scraping either site is against ToS
and was rejected in HANDOFF.md. Both stay manual entry.

These functions are not called by any endpoint.
"""


async def fetch_rt_scores(title: str, year: int | None = None) -> dict | None:
    """Return {'rt_aud': int} once implemented -- rt_crit now has a real source in omdb.py.
    Currently a no-op."""
    return None


async def fetch_letterboxd_rating(title: str, year: int | None = None) -> float | None:
    """Return a 0-5 Letterboxd rating once implemented. Currently a no-op."""
    return None

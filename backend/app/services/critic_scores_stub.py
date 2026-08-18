"""
Rotten Tomatoes and Letterboxd have no public API. This is a stub so the rest
of the pipeline has a consistent shape to call into whenever scraping (or a
future data source) gets wired up. Until then, these two fields stay manual
entry in the app.
"""


async def fetch_rt_scores(title: str, year: int | None = None) -> dict | None:
    """Return {'rt_crit': int, 'rt_aud': int} once implemented. Currently a no-op."""
    return None


async def fetch_letterboxd_rating(title: str, year: int | None = None) -> float | None:
    """Return a 0-5 Letterboxd rating once implemented. Currently a no-op."""
    return None

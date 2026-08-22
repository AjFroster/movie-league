"""Do the providers still return what this code reads?

Every other test in this suite fakes the providers, which is right -- a unit test should
not depend on someone else's uptime. The cost is that nothing notices when TMDB renames a
field or MDBList drops a rating source. The failure would surface as scores quietly going
missing, weeks later, with no error anywhere.

These make real calls with real keys. They are excluded from the default run (see
pytest.ini) and run nightly, because they need secrets, spend quota, and can fail for
reasons that have nothing to do with the commit under test.

    pytest -m provider_contract

Each test asserts the exact shape a parser depends on, not merely that a request
succeeded. A 200 carrying a renamed field is the failure worth catching.
"""
import os

import pytest

from app.services import mdblist, omdb, tmdb

pytestmark = pytest.mark.provider_contract

# Released long ago, enormous, and never leaving any database: its ids and ratings are as
# stable as this kind of fixture gets.
STABLE_FILM = "The Shawshank Redemption"
STABLE_IMDB_ID = "tt0111161"
STABLE_YEAR = 1994


@pytest.fixture(autouse=True)
def real_keys(monkeypatch):
    """Undo conftest's key-stripping. Without keys these skip rather than fail."""
    present = {}
    for name in ("TMDB_API_KEY", "OMDB_API_KEY", "MDBLIST_API_KEY"):
        value = os.environ.get(f"REAL_{name}") or _from_dotenv(name)
        if value:
            monkeypatch.setenv(name, value)
            present[name] = value
    if not present:
        pytest.skip("no provider keys configured")
    return present


def _from_dotenv(name):
    """Read backend/.env directly: conftest has already stripped these from the process."""
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def needs(real_keys, name):
    if name not in real_keys:
        pytest.skip(f"{name} not configured")


# ---------------------------------------------------------------------------
# TMDB -- budget, gross, release_date, imdb_id, poster
# ---------------------------------------------------------------------------

async def test_tmdb_still_returns_the_financial_fields(real_keys):
    needs(real_keys, "TMDB_API_KEY")
    # The season floor would reject a 1994 film, so query the layer beneath it.
    monkey = tmdb.SEASON_FLOOR_YEAR
    tmdb.SEASON_FLOOR_YEAR = 1900
    try:
        found = await tmdb.fetch_movie_financials(STABLE_FILM, year=STABLE_YEAR)
    finally:
        tmdb.SEASON_FLOOR_YEAR = monkey

    assert found is not None, "TMDB found nothing for a film it has always had"
    for field in ("tmdb_id", "title", "budget_millions", "gross_millions",
                  "imdb_id", "release_date", "poster_path"):
        assert field in found, f"TMDB response no longer yields {field}"

    assert found["imdb_id"] == STABLE_IMDB_ID, "the imdb_id link OMDb depends on has moved"
    assert found["budget_millions"] and found["budget_millions"] > 0
    assert found["gross_millions"] and found["gross_millions"] > 0
    assert found["release_date"].startswith("1994")


# ---------------------------------------------------------------------------
# OMDb -- imdb rating, rt_crit (fallback only, but still relied on)
# ---------------------------------------------------------------------------

async def test_omdb_still_returns_a_ratings_array(real_keys):
    needs(real_keys, "OMDB_API_KEY")
    ratings = await omdb.fetch_ratings(STABLE_IMDB_ID)

    assert ratings is not None, "OMDb returned nothing for a stable IMDb id"
    assert "imdb" in ratings and ratings["imdb"] is not None
    assert 0 < ratings["imdb"] <= 10, f"imdb out of range: {ratings['imdb']}"


async def test_omdbs_rotten_tomatoes_source_is_still_named_that(real_keys):
    """The parser matches on the literal string "Rotten Tomatoes"."""
    needs(real_keys, "OMDB_API_KEY")
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(omdb.OMDB_BASE, params={
            "i": STABLE_IMDB_ID, "apikey": os.environ["OMDB_API_KEY"]})
    payload = response.json()

    sources = {r.get("Source") for r in payload.get("Ratings") or []}
    assert omdb.RT_SOURCE_NAME in sources, (
        f"OMDb no longer labels Rotten Tomatoes as {omdb.RT_SOURCE_NAME!r}; "
        f"it now sends {sources}")


# ---------------------------------------------------------------------------
# MDBList -- the primary source for all four rating inputs
# ---------------------------------------------------------------------------

async def test_mdblist_still_returns_every_source_we_map(real_keys):
    """The one most likely to break silently.

    MDBList supplies all four rating inputs, and each arrives under a source name this code
    matches on. "popcorn" for the Rotten Tomatoes audience score is not a name anyone would
    guess, and it going away would drop rt_aud from every enrichment with no error.
    """
    needs(real_keys, "MDBLIST_API_KEY")
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{mdblist.MDBLIST_BASE}/imdb/movie/{STABLE_IMDB_ID}",
            params={"apikey": os.environ["MDBLIST_API_KEY"]})
    assert response.status_code == 200, f"MDBList said {response.status_code}"
    payload = response.json()

    assert "ratings" in payload, "MDBList no longer returns a `ratings` array"
    sources = {r.get("source") for r in payload["ratings"]}
    missing = set(mdblist.SOURCE_MAP) - sources
    assert not missing, (
        f"MDBList no longer sends {sorted(missing)}; SOURCE_MAP maps "
        f"{sorted(mdblist.SOURCE_MAP)} and the response carries {sorted(s for s in sources if s)}")


async def test_mdblist_values_are_in_the_ranges_we_accept(real_keys):
    """FIELD_RANGES silently drops anything outside them, so a unit change is invisible."""
    needs(real_keys, "MDBLIST_API_KEY")
    ratings = await mdblist.fetch_ratings(STABLE_IMDB_ID)
    assert ratings, "MDBList returned nothing for a stable IMDb id"

    for field, value in ratings.items():
        if value is None or field not in mdblist.FIELD_RANGES:
            continue
        low, high = mdblist.FIELD_RANGES[field]
        assert low <= value <= high, (
            f"{field}={value} is outside {low}-{high}; either the scale changed or the "
            "range is wrong, and enrichment is dropping the value either way")


async def test_mdblist_supplies_the_two_fields_nothing_else_can(real_keys):
    """letterboxd and rt_aud have no fallback. If MDBList stops sending them, they are gone."""
    needs(real_keys, "MDBLIST_API_KEY")
    ratings = await mdblist.fetch_ratings(STABLE_IMDB_ID)
    for field in ("letterboxd", "rt_aud"):
        assert field in ratings, f"MDBList no longer yields {field}, which has no fallback"

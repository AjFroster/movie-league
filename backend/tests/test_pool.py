"""Tests for the draftable movie pool.

All stubbed -- no network, no key (conftest strips TMDB_API_KEY). The behaviours worth
pinning are the ones that would quietly corrupt a draft: a duplicate film in the pool is
draftable twice, and a malformed result with no id cannot be picked at all.
"""
import httpx
import pytest

from app.redaction import ProviderError
from app.services import pool


def _film(i, **over):
    base = {"id": i, "title": f"Film {i}", "release_date": "2026-05-01",
            "poster_path": f"/p{i}.jpg", "overview": "words", "popularity": 100.0 - i}
    base.update(over)
    return base


def _pages(*pages):
    """Serve successive discover pages, then empty."""
    def handler(request):
        page = int(dict(request.url.params).get("page", 1))
        results = pages[page - 1] if page <= len(pages) else []
        return httpx.Response(200, json={"results": results})
    return handler


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

def test_summarize_keeps_only_what_a_draft_board_needs():
    assert pool.summarize(_film(1)) == {
        "tmdb_id": 1, "title": "Film 1", "release_date": "2026-05-01",
        "poster_path": "/p1.jpg", "poster_url": f"{pool.IMAGE_BASE}/p1.jpg",
        "overview": "words", "popularity": 99.0,
    }


@pytest.mark.parametrize("raw", [
    {}, None, "junk", {"id": 5}, {"title": "No id"}, {"id": None, "title": "x"},
])
def test_unusable_results_are_dropped(raw):
    """An entry with no id could be rendered but never drafted."""
    assert pool.summarize(raw) is None


def test_blank_optional_fields_become_none_not_empty_strings():
    film = pool.summarize(_film(1, release_date="", poster_path="", overview=""))
    assert film["release_date"] is None and film["poster_path"] is None
    assert film["overview"] is None
    # No artwork must be None rather than a URL pointing at nothing, so the client can
    # render its placeholder instead of a broken image.
    assert film["poster_url"] is None


def test_long_overviews_are_truncated():
    assert len(pool.summarize(_film(1, overview="x" * 5000))["overview"]) == 400


# ---------------------------------------------------------------------------
# fetch_pool
# ---------------------------------------------------------------------------

async def test_no_key_returns_an_empty_pool(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    def handler(request):
        raise AssertionError("must not call TMDB without a key")

    async with _client(handler) as client:
        assert await pool.fetch_pool(2026, client=client) == []


async def test_pool_pages_until_it_has_enough(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    pages = [[_film(i) for i in range(p * 20, p * 20 + 20)] for p in range(3)]
    async with _client(_pages(*pages)) as client:
        films = await pool.fetch_pool(2026, size=50, client=client)
    assert len(films) == 50
    assert films[0]["tmdb_id"] == 0


async def test_pool_stops_early_when_the_catalogue_runs_out(monkeypatch):
    """A future year has far fewer titles than the requested size."""
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    async with _client(_pages([_film(i) for i in range(5)])) as client:
        films = await pool.fetch_pool(2027, size=300, client=client)
    assert len(films) == 5


async def test_duplicates_across_pages_are_collapsed(monkeypatch):
    """TMDB can repeat a title as popularity shifts mid-walk; a dupe is draftable twice."""
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    page1 = [_film(1), _film(2)]
    page2 = [_film(2), _film(3)]
    async with _client(_pages(page1, page2)) as client:
        films = await pool.fetch_pool(2026, size=40, client=client)
    assert [f["tmdb_id"] for f in films] == [1, 2, 3]


async def test_pool_size_is_clamped(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [_film(calls["n"])]})

    async with _client(handler) as client:
        await pool.fetch_pool(2026, size=99999, client=client)
    assert calls["n"] <= -(-pool.MAX_POOL_SIZE // pool.PAGE_SIZE)


@pytest.mark.parametrize("year", ["2026", None, 1200, 3000, 1.5])
async def test_implausible_years_are_rejected(monkeypatch, year):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    async with _client(_pages([])) as client:
        with pytest.raises(ValueError):
            await pool.fetch_pool(year, client=client)


async def test_http_failure_raises_a_redacted_provider_error(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET777")
    async with _client(lambda r: httpx.Response(401, json={})) as client:
        with pytest.raises(ProviderError) as excinfo:
            await pool.fetch_pool(2026, client=client)
    assert "SUPERSECRET777" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

async def test_search_returns_summaries(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    async with _client(lambda r: httpx.Response(200, json={"results": [_film(9)]})) as client:
        assert (await pool.search("dune", client=client))[0]["tmdb_id"] == 9


@pytest.mark.parametrize("query", ["", "   ", None])
async def test_blank_search_does_not_call_the_api(monkeypatch, query):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")

    def handler(request):
        raise AssertionError("must not search on a blank query")

    async with _client(handler) as client:
        assert await pool.search(query, client=client) == []


async def test_search_failure_is_redacted(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET777")
    async with _client(lambda r: httpx.Response(500, json={})) as client:
        with pytest.raises(ProviderError) as excinfo:
            await pool.search("dune", client=client)
    assert "SUPERSECRET777" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# the cache, which is what bounds the amplification
# ---------------------------------------------------------------------------

async def test_a_second_ask_for_the_same_year_costs_nothing_upstream(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [_film(calls["n"])]})

    async with _client(handler) as client:
        first = await pool.fetch_pool(2026, size=20, client=client)
        after_first = calls["n"]
        second = await pool.fetch_pool(2026, size=20, client=client)

    assert second == first
    assert calls["n"] == after_first, "the second call went back to TMDB"


async def test_sizes_in_one_bucket_share_a_cache_entry(monkeypatch):
    """The property that makes the cache a defence rather than a convenience.

    Keyed on the exact size, a caller walking size=1..500 would miss every time and each
    miss would cost up to 25 TMDB requests. Rounding to a bucket caps a year at five
    entries no matter what sizes are asked for.
    """
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [_film(i) for i in range(20)]})

    async with _client(handler) as client:
        await pool.fetch_pool(2026, size=1, client=client)
        cost = calls["n"]
        for size in range(2, 101):
            await pool.fetch_pool(2026, size=size, client=client)

    assert calls["n"] == cost, f"{calls['n'] - cost} extra requests across one bucket"


async def test_a_smaller_ask_is_sliced_from_the_cached_bucket(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    async with _client(_pages([_film(i) for i in range(20)])) as client:
        await pool.fetch_pool(2026, size=100, client=client)
        few = await pool.fetch_pool(2026, size=3, client=client)
    assert [f["tmdb_id"] for f in few] == [0, 1, 2]


async def test_the_cache_expires(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [_film(calls["n"])]})

    async with _client(handler) as client:
        await pool.fetch_pool(2026, size=20, client=client)
        cost = calls["n"]
        monkeypatch.setattr(pool, "POOL_TTL", -1)   # everything is already stale
        await pool.fetch_pool(2026, size=20, client=client)

    assert calls["n"] == cost * 2, "an expired entry was served anyway"


async def test_different_years_do_not_share_an_entry(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SENTINEL")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"results": [_film(calls["n"])]})

    async with _client(handler) as client:
        a = await pool.fetch_pool(2026, size=20, client=client)
        cost = calls["n"]
        b = await pool.fetch_pool(2027, size=20, client=client)

    assert a != b
    assert calls["n"] == cost * 2, "one year was served from another year's entry"

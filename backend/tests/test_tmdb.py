"""Network-free tests for the TMDB financials client.

Every HTTP-touching test drives fetch_movie_financials through an injected
httpx.MockTransport whose handler branches on request.url.path -- no test here touches
the network or requires a real TMDB_API_KEY (the autouse `no_real_api_keys` fixture in
conftest.py strips both provider keys from the environment before every test).
"""
import inspect

import httpx
import pytest

from app.services import tmdb


SEARCH_RESULT = {"results": [{"id": 42}]}


def _details(**overrides):
    base = {
        "budget": 170_000_000,
        "revenue": 700_000_000,
        "vote_average": 7.35,
        "imdb_id": "tt0111161",
        "release_date": "2026-05-22",
    }
    base.update(overrides)
    return base


def _make_handler(details_body):
    def handler(request):
        if request.url.path.endswith("/search/movie"):
            return httpx.Response(200, json=SEARCH_RESULT)
        return httpx.Response(200, json=details_body)
    return handler


# ---------------------------------------------------------------------------
# Full round-trip via MockTransport
# ---------------------------------------------------------------------------

async def test_fetch_movie_financials_full_round_trip_includes_release_date(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    transport = httpx.MockTransport(_make_handler(_details()))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await tmdb.fetch_movie_financials("The Shawshank Redemption", client=client)

    assert result == {
        "tmdb_id": 42,
        "budget_millions": 170.0,
        "gross_millions": 700.0,
        "vote_average": 7.4,
        "imdb_id": "tt0111161",
        "release_date": "2026-05-22",
    }


async def test_release_date_none_when_empty_string(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(release_date=""))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["release_date"] is None


async def test_release_date_none_when_null(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(release_date=None))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["release_date"] is None


async def test_release_date_none_when_non_string(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(release_date=20260522))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["release_date"] is None


async def test_imdb_id_none_when_empty_string(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(imdb_id=""))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["imdb_id"] is None


async def test_imdb_id_none_when_malformed(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(imdb_id="not-an-id"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["imdb_id"] is None


@pytest.mark.parametrize("bad_budget", [0, -5, None])
async def test_budget_millions_none_for_bad_values(monkeypatch, bad_budget):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(budget=bad_budget))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["budget_millions"] is None


async def test_vote_average_none_when_out_of_range(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")
    handler = _make_handler(_details(vote_average=11))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("X", client=client)
    assert result["vote_average"] is None


async def test_no_key_returns_none_without_building_request():
    # no_real_api_keys fixture already stripped TMDB_API_KEY
    assert await tmdb.fetch_movie_financials("X") is None


async def test_zero_search_results_returns_none(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")

    def handler(request):
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await tmdb.fetch_movie_financials("Nonexistent Film", client=client)
    assert result is None


async def test_failing_response_raises_http_status_error_not_provider_error(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRET456")

    def handler(request):
        return httpx.Response(401, json={"status_message": "Invalid API key"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await tmdb.fetch_movie_financials("X", client=client)


def test_client_is_an_injectable_keyword_parameter():
    assert "client" in inspect.signature(tmdb.fetch_movie_financials).parameters


# ---------------------------------------------------------------------------
# Private numeric parsers -- direct unit coverage
# ---------------------------------------------------------------------------

def test_millions_valid_value():
    assert tmdb._millions(170_000_000) == 170.0


@pytest.mark.parametrize("bad", [0, -5, "170", True, None, float("nan")])
def test_millions_invalid(bad):
    assert tmdb._millions(bad) is None


@pytest.mark.parametrize("value,expected", [(7.35, 7.4), (10, 10.0), (0.1, 0.1)])
def test_vote_average_valid(value, expected):
    assert tmdb._vote_average(value) == expected


@pytest.mark.parametrize("bad", [0, -1, 11, "7.4", True, None, float("nan")])
def test_vote_average_invalid(bad):
    assert tmdb._vote_average(bad) is None


@pytest.mark.parametrize("value", ["tt0111161", "tt12345678", "tt123456789", "tt1234567890"])
def test_imdb_id_valid(value):
    assert tmdb._imdb_id(value) == value


@pytest.mark.parametrize("bad", ["", None, "0111161", "ttabc1234", 123, True])
def test_imdb_id_invalid(bad):
    assert tmdb._imdb_id(bad) is None


@pytest.mark.parametrize("value", ["2026-05-22", "2026-05-22T00:00:00"])
def test_release_date_valid(value):
    assert tmdb._release_date(value) == value


@pytest.mark.parametrize("bad", ["", None, "May 22, 2026", 20260522, True])
def test_release_date_invalid(bad):
    assert tmdb._release_date(bad) is None


# ---------------------------------------------------------------------------
# Cross-module integration: release_date feeds cache.ttl_for's tiering
# ---------------------------------------------------------------------------

def test_release_date_feeds_cache_ttl_tiering():
    from app.services import cache
    assert cache.ttl_for(tmdb._release_date(""), matched=True) == cache.TTL_NEGATIVE
    assert cache.ttl_for(tmdb._release_date("2001-04-01"), matched=True) == cache.TTL_RELEASED

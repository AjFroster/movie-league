"""TestClient endpoint coverage for the rewired single-entry /enrich, the
provenance-stamping PUT, and (Task 2) the bulk POST /api/enrich-all.

Two things this module exists to prove, per 02-RESEARCH.md section 4 and the verified
OMDb-key-in-URL leak this plan closes:

1. Hand-entered (`manual`) values are never silently overwritten by enrichment unless
   the caller passes `?force=true`.
2. No HTTP response body -- 200 or 502 -- can ever contain a provider API key, even
   though OMDb has no header auth and puts its key in the query string.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import enrichment, provenance
from app.main import app
from app.services import cache, omdb, tmdb

TMDB_PAYLOAD = {"tmdb_id": 1, "budget_millions": 170.0, "gross_millions": 100.5,
                "vote_average": 9.9, "imdb_id": "tt0111161", "release_date": "2001-04-01"}
OMDB_PAYLOAD = {"imdb_id": "tt0111161", "imdb": 6.1, "rt_crit": 54.0}


@pytest.fixture
def api(tmp_league, tmp_cache, monkeypatch):
    """A TestClient wired to throwaway data, a throwaway cache, and fake providers."""
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    calls = {"tmdb": 0, "omdb": 0}

    async def fake_tmdb(title, year=None, *, client=None):
        calls["tmdb"] += 1
        return dict(TMDB_PAYLOAD)

    async def fake_omdb(imdb_id, *, client=None):
        calls["omdb"] += 1
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)
    with TestClient(app) as client:
        yield client, calls


# ---------------------------------------------------------------------------
# Task 1: single-entry POST /enrich
# ---------------------------------------------------------------------------

def test_enrich_fills_an_empty_row(api):
    client, calls = api
    response = client.post("/api/movies/Liam/2/enrich")
    assert response.status_code == 200
    body = response.json()
    assert {"movie", "report", "api_calls_used"}.issubset(body.keys())
    movie = body["movie"]
    assert movie["budget"] == TMDB_PAYLOAD["budget_millions"]
    assert movie["gross"] == TMDB_PAYLOAD["gross_millions"]
    assert movie["imdb"] == OMDB_PAYLOAD["imdb"]
    assert movie["rt_crit"] == OMDB_PAYLOAD["rt_crit"]
    assert movie["roi"] == round(
        TMDB_PAYLOAD["gross_millions"] / TMDB_PAYLOAD["budget_millions"], 3)
    assert body["api_calls_used"] == 2
    assert calls == {"tmdb": 1, "omdb": 1}


def test_enrich_second_call_is_served_from_cache(api):
    client, calls = api
    first = client.post("/api/movies/Liam/2/enrich")
    assert first.status_code == 200
    second = client.post("/api/movies/Liam/2/enrich")
    assert second.status_code == 200
    assert second.json()["api_calls_used"] == 0


def test_enrich_protects_a_manual_field(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["rt_crit"] = 71.0
    put_response = client.put("/api/movies/Liam/2", json=movie)
    assert put_response.status_code == 200
    assert put_response.json()["sources"]["rt_crit"]["origin"] == "manual"

    response = client.post("/api/movies/Liam/2/enrich")
    assert response.status_code == 200
    body = response.json()
    assert body["movie"]["rt_crit"] == 71.0
    assert "rt_crit" in body["report"]["protected"]


def test_enrich_force_overwrites_manual_field(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["rt_crit"] = 71.0
    client.put("/api/movies/Liam/2", json=movie)

    response = client.post("/api/movies/Liam/2/enrich?force=true")
    assert response.status_code == 200
    body = response.json()
    assert body["movie"]["rt_crit"] == OMDB_PAYLOAD["rt_crit"]
    assert "rt_crit" in body["report"]["updated"]


def test_enrich_missing_entry_returns_404(api):
    client, calls = api
    response = client.post("/api/movies/Nobody/9/enrich")
    assert response.status_code == 404


def test_enrich_imdb_is_sourced_from_omdb_never_tmdb_vote_average(api):
    client, calls = api
    response = client.post("/api/movies/Liam/2/enrich")
    movie = response.json()["movie"]
    assert movie["imdb"] == OMDB_PAYLOAD["imdb"]
    assert movie["imdb"] != TMDB_PAYLOAD["vote_average"]


def test_no_response_body_ever_contains_the_api_key(tmp_league, tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")

    async def fake_tmdb(title, year=None, *, client=None):
        return dict(TMDB_PAYLOAD)

    async def exploding_omdb(imdb_id, *, client=None):
        # Reproduce a real OMDb 401: httpx embeds the full URL, key included, in str(exc).
        def handler(request):
            return httpx.Response(401, json={"Response": "False", "Error": "Invalid API key!"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            response = await c.get("https://www.omdbapi.com/",
                                   params={"i": imdb_id, "apikey": "SUPERSECRET123"})
            response.raise_for_status()

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", exploding_omdb)

    with TestClient(app) as client:
        # Path A: the error is carried inside a 200 run report.
        ok = client.post("/api/movies/Liam/2/enrich")
        assert ok.status_code == 200
        assert "SUPERSECRET123" not in ok.text

        # Path B: the error escapes to the 502 handler.
        async def exploding_entry(entry, *, budget, force=False, tmdb_client=None,
                                  omdb_client=None):
            raise httpx.ConnectError(
                "failed for url 'https://www.omdbapi.com/?i=tt1&apikey=SUPERSECRET123'")

        monkeypatch.setattr(enrichment, "enrich_entry", exploding_entry)
        bad = client.post("/api/movies/Liam/2/enrich")
        assert bad.status_code == 502
        assert "SUPERSECRET123" not in bad.text


# ---------------------------------------------------------------------------
# Task 1: PUT /api/movies/{owner}/{round} provenance stamping
# ---------------------------------------------------------------------------

def test_put_stamps_changed_field_as_manual(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["imdb"] = 8.8
    response = client.put("/api/movies/Liam/2", json=movie)
    assert response.status_code == 200
    assert response.json()["sources"]["imdb"]["origin"] == "manual"


def test_put_leaves_unrelated_field_provenance_untouched(api):
    client, calls = api
    client.post("/api/movies/Liam/2/enrich")  # populate budget/gross/imdb/rt_crit as "fetched"
    fetched = client.get("/api/movies").json()[0]
    budget_source_before = dict(fetched["sources"]["budget"])

    # Change an unrelated, non-enrichable field only.
    fetched["rt_aud"] = 55.0
    response = client.put("/api/movies/Liam/2", json=fetched)
    assert response.status_code == 200
    assert response.json()["sources"]["budget"] == budget_source_before


def test_put_forged_sources_body_has_no_effect(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["imdb"] = 3.3
    # Forge a claim that this hand-edited value is actually machine-fetched.
    movie["sources"] = {
        "imdb": {"origin": "fetched", "provider": "omdb", "at": "2020-01-01T00:00:00Z"}}
    response = client.put("/api/movies/Liam/2", json=movie)
    assert response.status_code == 200
    assert response.json()["sources"]["imdb"]["origin"] == "manual"


def test_put_derives_roi_from_budget_and_gross(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["budget"] = 100.0
    movie["gross"] = 250.0
    response = client.put("/api/movies/Liam/2", json=movie)
    assert response.status_code == 200
    body = response.json()
    assert body["roi"] == 2.5
    assert body["sources"]["roi"]["origin"] == "manual"


def test_put_explicit_roi_is_kept_and_stamped_manual(api):
    client, calls = api
    movie = client.get("/api/movies").json()[0]
    movie["budget"] = 100.0
    movie["gross"] = 250.0
    movie["roi"] = 9.99  # explicit, deliberately different from the derived 2.5
    response = client.put("/api/movies/Liam/2", json=movie)
    assert response.status_code == 200
    body = response.json()
    assert body["roi"] == 9.99
    assert body["sources"]["roi"]["origin"] == "manual"

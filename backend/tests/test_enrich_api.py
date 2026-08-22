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
from app.services import cache, mdblist, omdb, tmdb

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

    async def fake_mdblist(imdb_id, *, client=None):
        calls["mdblist"] = calls.get("mdblist", 0) + 1
        return {"imdb": 6.1, "rt_crit": 54.0}

    monkeypatch.setenv("MDBLIST_API_KEY", "MDBSENTINEL")
    monkeypatch.setattr(mdblist, "fetch_ratings", fake_mdblist)
    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)
    with TestClient(app) as client:
        yield client, calls, tmp_league


# ---------------------------------------------------------------------------
# Task 1: single-entry POST /enrich
# ---------------------------------------------------------------------------

def test_enrich_fills_an_empty_row(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
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
    assert calls == {"tmdb": 1, "omdb": 0, "mdblist": 1}


def test_enrich_second_call_is_served_from_cache(api):
    client, calls, league = api
    first = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
    assert first.status_code == 200
    second = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
    assert second.status_code == 200
    assert second.json()["api_calls_used"] == 0


def test_enrich_protects_a_manual_field(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["rt_crit"] = 71.0
    put_response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)
    assert put_response.status_code == 200
    assert put_response.json()["sources"]["rt_crit"]["origin"] == "manual"

    response = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
    assert response.status_code == 200
    body = response.json()
    assert body["movie"]["rt_crit"] == 71.0
    assert "rt_crit" in body["report"]["protected"]


def test_enrich_force_overwrites_manual_field(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["rt_crit"] = 71.0
    client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)

    response = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich?force=true")
    assert response.status_code == 200
    body = response.json()
    assert body["movie"]["rt_crit"] == OMDB_PAYLOAD["rt_crit"]
    assert "rt_crit" in body["report"]["updated"]


def test_enrich_missing_entry_returns_404(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/movies/Nobody/9/enrich")
    assert response.status_code == 404


def test_enrich_imdb_is_sourced_from_omdb_never_tmdb_vote_average(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
    movie = response.json()["movie"]
    assert movie["imdb"] == OMDB_PAYLOAD["imdb"]
    assert movie["imdb"] != TMDB_PAYLOAD["vote_average"]


def test_no_response_body_ever_contains_the_api_key(tmp_league, tmp_cache, monkeypatch):
    league = tmp_league
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

    async def partial_mdblist(imdb_id, *, client=None):
        # Deliberately incomplete: a missing rt_crit forces the OMDb fallback to run,
        # which is the whole point here -- OMDb is where the key can leak.
        return {"imdb": 6.1}

    monkeypatch.setenv("MDBLIST_API_KEY", "MDBSENTINEL")
    monkeypatch.setattr(mdblist, "fetch_ratings", partial_mdblist)
    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", exploding_omdb)

    with TestClient(app) as client:
        # Path A: the error is carried inside a 200 run report.
        ok = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
        assert ok.status_code == 200
        assert "SUPERSECRET123" not in ok.text

        # Path B: the error escapes to the 502 handler.
        async def exploding_entry(entry, *, budget, force=False, tmdb_client=None,
                                  omdb_client=None):
            raise httpx.ConnectError(
                "failed for url 'https://www.omdbapi.com/?i=tt1&apikey=SUPERSECRET123'")

        monkeypatch.setattr(enrichment, "enrich_entry", exploding_entry)
        bad = client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")
        assert bad.status_code == 502
        assert "SUPERSECRET123" not in bad.text


# ---------------------------------------------------------------------------
# Task 1: PUT /api/movies/{owner}/{round} provenance stamping
# ---------------------------------------------------------------------------

def test_put_stamps_changed_field_as_manual(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["imdb"] = 8.8
    response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)
    assert response.status_code == 200
    assert response.json()["sources"]["imdb"]["origin"] == "manual"


def test_put_leaves_unrelated_field_provenance_untouched(api):
    client, calls, league = api
    client.post(f"/api/leagues/{league}/movies/Liam/2/enrich")  # populate budget/gross/imdb/rt_crit as "fetched"
    fetched = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    budget_source_before = dict(fetched["sources"]["budget"])

    # Change an unrelated, non-enrichable field only.
    fetched["rt_aud"] = 55.0
    response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=fetched)
    assert response.status_code == 200
    assert response.json()["sources"]["budget"] == budget_source_before


def test_put_forged_sources_body_has_no_effect(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["imdb"] = 3.3
    # Forge a claim that this hand-edited value is actually machine-fetched.
    movie["sources"] = {
        "imdb": {"origin": "fetched", "provider": "omdb", "at": "2020-01-01T00:00:00Z"}}
    response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)
    assert response.status_code == 200
    assert response.json()["sources"]["imdb"]["origin"] == "manual"


def test_put_derives_roi_from_budget_and_gross(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["budget"] = 100.0
    movie["gross"] = 250.0
    response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)
    assert response.status_code == 200
    body = response.json()
    assert body["roi"] == 2.5
    assert body["sources"]["roi"]["origin"] == "manual"


def test_put_explicit_roi_is_kept_and_stamped_manual(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["budget"] = 100.0
    movie["gross"] = 250.0
    movie["roi"] = 9.99  # explicit, deliberately different from the derived 2.5
    response = client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)
    assert response.status_code == 200
    body = response.json()
    assert body["roi"] == 9.99
    assert body["sources"]["roi"]["origin"] == "manual"


# ---------------------------------------------------------------------------
# Task 2: bulk POST /api/enrich-all
# ---------------------------------------------------------------------------

def test_enrich_all_returns_run_summary(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/enrich-all")
    assert response.status_code == 200
    body = response.json()
    expected_keys = {"movies_processed", "api_calls_used", "max_calls", "cap_reached",
                      "forced", "fields_updated", "fields_protected", "reports"}
    assert expected_keys.issubset(body.keys())


def test_enrich_all_persists_results(api):
    client, calls, league = api
    client.post(f"/api/leagues/{league}/enrich-all")
    movies = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"]
    assert movies[0]["budget"] == TMDB_PAYLOAD["budget_millions"]
    assert movies[0]["imdb"] == OMDB_PAYLOAD["imdb"]


def test_enrich_all_second_run_costs_zero_calls(api):
    client, calls, league = api
    client.post(f"/api/leagues/{league}/enrich-all")
    second = client.post(f"/api/leagues/{league}/enrich-all")
    assert second.json()["api_calls_used"] == 0


def test_enrich_all_force_true_reports_forced(api):
    client, calls, league = api
    client.post(f"/api/leagues/{league}/enrich-all")
    response = client.post(f"/api/leagues/{league}/enrich-all?force=true")
    assert response.status_code == 200
    assert response.json()["forced"] is True


def test_enrich_all_max_calls_two_caps_the_run(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/enrich-all?max_calls=2")
    assert response.status_code == 200
    body = response.json()
    assert body["api_calls_used"] == 2
    assert body["cap_reached"] is True
    assert calls == {"tmdb": 1, "omdb": 0, "mdblist": 1}


@pytest.mark.parametrize("bad", [0, -1, 99999])
def test_max_calls_is_clamped_before_any_outbound_call(api, bad):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/enrich-all?max_calls={bad}")
    assert response.status_code == 422
    assert calls == {"tmdb": 0, "omdb": 0}


def test_enrich_all_max_calls_non_numeric_returns_422(api):
    client, calls, league = api
    response = client.post(f"/api/leagues/{league}/enrich-all?max_calls=abc")
    assert response.status_code == 422


def test_enrichment_never_moves_the_standings(api):
    client, _calls, league = api

    # Prime the row once so `imdb` is already non-null going into the measured run.
    # storage.compute_leaderboard's *pre-existing* `rounds_played` counter (unrelated to
    # this plan, unmodified since the repo's initial commit) increments whenever a row's
    # `imdb` is not None -- so measuring straight from an all-empty row would flip
    # rounds_played 0->1 on the very first enrichment, which is a real (and, outside a
    # test, desirable) leaderboard diff, but it is not one of the five score fields
    # (total/rating_score/financial_score/penalties/watch_points) RESEARCH.md section 3
    # and this plan's locked "data layer only" decision actually protect. Priming first
    # holds rounds_played steady across the measured before/after pair, so this test
    # isolates exactly the guarantee it names: enrichment does not move the standings.
    client.post(f"/api/leagues/{league}/enrich-all")

    before = client.get(f"/api/leagues/{league}/leaderboard").json()
    summary = client.post(f"/api/leagues/{league}/enrich-all?force=true").json()
    after = client.get(f"/api/leagues/{league}/leaderboard").json()

    assert summary["movies_processed"] >= 1
    assert summary["fields_updated"] >= 1        # data really did change
    assert before == after                        # ...but no score did


def test_enrich_all_counts_protected_manual_fields(api):
    client, calls, league = api
    movie = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    movie["rt_crit"] = 71.0
    client.put(f"/api/leagues/{league}/movies/Liam/2", json=movie)

    response = client.post(f"/api/leagues/{league}/enrich-all")
    assert response.status_code == 200
    body = response.json()
    assert body["fields_protected"] >= 1

    after = client.get(f"/api/leagues/{league}/owners/Liam").json()["movies"][0]
    assert after["rt_crit"] == 71.0

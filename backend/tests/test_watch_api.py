"""Tests for POST /api/movies/{owner}/{round}/watch.

These cover the scoring and input validation. Authorisation is covered in test_auth.py:
the caller must be the person being ticked, or the league's creator acting for a slot
nobody has claimed. This fixture is the latter -- the local identity creates the league
and every slot is unclaimed, which is the single-laptop case.
"""
import pytest
from fastapi.testclient import TestClient

from app.db.porting import import_league
from app.main import app


@pytest.fixture
def client(never_touch_the_real_database):
    """A TestClient backed by a throwaway database, never the real one."""
    data = {"owners": ["Ann", "Bob", "Cal"], "movies": [
        {"owner": "Ann", "round": 1, "movie": "Alpha", "imdb": 8.0, "letterboxd": None,
         "rt_crit": None, "rt_aud": None, "budget": None, "gross": None, "roi": None,
         "bo_rank": None, "awards": None, "who_watched": [], "rating_score": 7,
         "financial_score": 0, "penalties": 0, "penalty_notes": "", "watch_points": 0,
         "total": 7, "sources": {}},
        {"owner": "Bob", "round": 1, "movie": "Beta", "imdb": None, "letterboxd": None,
         "rt_crit": None, "rt_aud": None, "budget": None, "gross": None, "roi": None,
         "bo_rank": None, "awards": None, "who_watched": [], "rating_score": 0,
         "financial_score": 0, "penalties": 0, "penalty_notes": "", "watch_points": 0,
         "total": 0, "sources": {}},
    ]}
    # never_touch_the_real_database (conftest, autouse) already redirected the app at a
    # throwaway database and handed back its session factory; just seed it.
    from app.auth import LOCAL_USER_ID
    with never_touch_the_real_database() as s:
        seeded = import_league(s, data, name="Test", year=2026)
        seeded.owner_user_id = LOCAL_USER_ID
        s.commit()
        league_id = seeded.id
    return TestClient(app), league_id


def _board(client, league):
    rows = client.get(f"/api/leagues/{league}/leaderboard").json()
    return {r["owner"]: r for r in rows}


def test_owner_watching_own_pick_earns_five_on_the_row(client):
    client, league = client
    r = client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Ann", "watched": True})
    assert r.status_code == 200
    assert r.json()["movie"]["watch_points"] == 5
    assert r.json()["movie"]["total"] == 12          # 7 rating + 5 watch
    assert _board(client, league)["Ann"]["total"] == 12


def test_other_player_watching_earns_one_for_themselves_not_the_owner(client):
    client, league = client
    client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    board = _board(client, league)
    assert board["Bob"]["total"] == 1                # Bob earned it
    assert board["Bob"]["other_watch_points"] == 1
    assert board["Ann"]["total"] == 7                # Ann's row is unmoved
    assert board["Ann"]["watch_points"] == 0


def test_points_stack_across_own_and_others_picks(client):
    client, league = client
    client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Ann", "watched": True})
    client.post(f"/api/leagues/{league}/movies/Bob/1/watch", json={"viewer": "Ann", "watched": True})
    board = _board(client, league)
    assert board["Ann"]["own_watch_points"] == 5
    assert board["Ann"]["other_watch_points"] == 1
    assert board["Ann"]["total"] == 7 + 5 + 1


def test_unwatching_removes_the_points_again(client):
    client, league = client
    client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    assert _board(client, league)["Bob"]["total"] == 1
    client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Bob", "watched": False})
    assert _board(client, league)["Bob"]["total"] == 0


def test_toggling_on_twice_does_not_double_count(client):
    client, league = client
    for _ in range(3):
        client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    assert client.get(f"/api/leagues/{league}/owners/Ann").json()["movies"][0]["who_watched"] == ["Bob"]
    assert _board(client, league)["Bob"]["total"] == 1


def test_unwatching_someone_who_never_watched_is_a_no_op(client):
    client, league = client
    r = client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Cal", "watched": False})
    assert r.status_code == 200
    assert r.json()["movie"]["who_watched"] == []


def test_watchers_are_stored_in_league_order_not_click_order(client):
    client, league = client
    """A stable order keeps the stored file from churning as people toggle."""
    for viewer in ("Cal", "Ann", "Bob"):
        client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": viewer, "watched": True})
    assert client.get(f"/api/leagues/{league}/owners/Ann").json()["movies"][0]["who_watched"] == \
        ["Ann", "Bob", "Cal"]


def test_unknown_player_is_rejected(client):
    client, league = client
    r = client.post(f"/api/leagues/{league}/movies/Ann/1/watch", json={"viewer": "Nobody", "watched": True})
    assert r.status_code == 422


def test_unknown_movie_is_404(client):
    client, league = client
    r = client.post(f"/api/leagues/{league}/movies/Ann/99/watch", json={"viewer": "Bob", "watched": True})
    assert r.status_code == 404


def test_response_carries_a_fresh_breakdown_and_leaderboard(client):
    client, league = client
    """The UI updates from this response, so it must not need a follow-up fetch."""
    body = client.post(f"/api/leagues/{league}/movies/Ann/1/watch",
                       json={"viewer": "Ann", "watched": True}).json()
    watch_row = [r for r in body["movie"]["breakdown"] if r["label"] == "Owner watched"][0]
    assert watch_row["value"] == "Yes" and watch_row["points"] == 5
    assert {r["owner"] for r in body["leaderboard"]} == {"Ann", "Bob", "Cal"}


def test_a_watch_is_recorded_against_the_named_league(client):
    client, league = client
    """The legacy route acts on whichever league is current, which is wrong as soon as you
    are looking at an older season -- it would write to the newest league and 422."""
    r = client.post("/api/leagues/1/movies/Ann/1/watch",
                    json={"viewer": "Bob", "watched": True})
    assert r.status_code == 200
    board = {x["owner"]: x for x in r.json()["leaderboard"]}
    assert board["Bob"]["other_watch_points"] == 1


def test_a_watch_against_an_unknown_league_is_404(client):
    client, league = client
    r = client.post("/api/leagues/999/movies/Ann/1/watch",
                    json={"viewer": "Bob", "watched": True})
    assert r.status_code == 404


def test_a_watch_naming_a_player_from_another_league_is_rejected(client):
    client, league = client
    r = client.post("/api/leagues/1/movies/Ann/1/watch",
                    json={"viewer": "Stranger", "watched": True})
    assert r.status_code == 422

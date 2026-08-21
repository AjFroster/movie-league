"""Tests for POST /api/movies/{owner}/{round}/watch.

The endpoint is trust-based by design -- there is no login, and any player can tick any
other player -- so these tests cover the input validation that does exist rather than
authorisation, which does not.
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
    maker = never_touch_the_real_database
    with maker() as s:
        import_league(s, data, name="Test", year=2026)
        s.commit()
    return TestClient(app)


def _board(client):
    return {r["owner"]: r for r in client.get("/api/leaderboard").json()}


def test_owner_watching_own_pick_earns_five_on_the_row(client):
    r = client.post("/api/movies/Ann/1/watch", json={"viewer": "Ann", "watched": True})
    assert r.status_code == 200
    assert r.json()["movie"]["watch_points"] == 5
    assert r.json()["movie"]["total"] == 12          # 7 rating + 5 watch
    assert _board(client)["Ann"]["total"] == 12


def test_other_player_watching_earns_one_for_themselves_not_the_owner(client):
    client.post("/api/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    board = _board(client)
    assert board["Bob"]["total"] == 1                # Bob earned it
    assert board["Bob"]["other_watch_points"] == 1
    assert board["Ann"]["total"] == 7                # Ann's row is unmoved
    assert board["Ann"]["watch_points"] == 0


def test_points_stack_across_own_and_others_picks(client):
    client.post("/api/movies/Ann/1/watch", json={"viewer": "Ann", "watched": True})
    client.post("/api/movies/Bob/1/watch", json={"viewer": "Ann", "watched": True})
    board = _board(client)
    assert board["Ann"]["own_watch_points"] == 5
    assert board["Ann"]["other_watch_points"] == 1
    assert board["Ann"]["total"] == 7 + 5 + 1


def test_unwatching_removes_the_points_again(client):
    client.post("/api/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    assert _board(client)["Bob"]["total"] == 1
    client.post("/api/movies/Ann/1/watch", json={"viewer": "Bob", "watched": False})
    assert _board(client)["Bob"]["total"] == 0


def test_toggling_on_twice_does_not_double_count(client):
    for _ in range(3):
        client.post("/api/movies/Ann/1/watch", json={"viewer": "Bob", "watched": True})
    assert client.get("/api/owners/Ann").json()["movies"][0]["who_watched"] == ["Bob"]
    assert _board(client)["Bob"]["total"] == 1


def test_unwatching_someone_who_never_watched_is_a_no_op(client):
    r = client.post("/api/movies/Ann/1/watch", json={"viewer": "Cal", "watched": False})
    assert r.status_code == 200
    assert r.json()["movie"]["who_watched"] == []


def test_watchers_are_stored_in_league_order_not_click_order(client):
    """A stable order keeps the stored file from churning as people toggle."""
    for viewer in ("Cal", "Ann", "Bob"):
        client.post("/api/movies/Ann/1/watch", json={"viewer": viewer, "watched": True})
    assert client.get("/api/owners/Ann").json()["movies"][0]["who_watched"] == \
        ["Ann", "Bob", "Cal"]


def test_unknown_player_is_rejected(client):
    r = client.post("/api/movies/Ann/1/watch", json={"viewer": "Nobody", "watched": True})
    assert r.status_code == 422


def test_unknown_movie_is_404(client):
    r = client.post("/api/movies/Ann/99/watch", json={"viewer": "Bob", "watched": True})
    assert r.status_code == 404


def test_response_carries_a_fresh_breakdown_and_leaderboard(client):
    """The UI updates from this response, so it must not need a follow-up fetch."""
    body = client.post("/api/movies/Ann/1/watch",
                       json={"viewer": "Ann", "watched": True}).json()
    watch_row = [r for r in body["movie"]["breakdown"] if r["label"] == "Owner watched"][0]
    assert watch_row["value"] == "Yes" and watch_row["points"] == 5
    assert {r["owner"] for r in body["leaderboard"]} == {"Ann", "Bob", "Cal"}

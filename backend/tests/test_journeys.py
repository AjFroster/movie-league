"""Whole journeys over HTTP, from an empty database to a finished season.

The draft rules are covered thoroughly in test_repo_draft.py, but those call Python
functions directly. These drive the same behaviour through the API the browser uses, which
is the layer where routing, serialisation, permissions and transactions actually meet.

Each test reads as a story on purpose: if one breaks, the failing line says which step of
a real user's day stopped working.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

from .helpers import act_as

COMMISSIONER = "user_commissioner"
FRIEND = "user_friend"
STRANGER = "user_stranger"


@pytest.fixture
def client(never_touch_the_real_database):
    with TestClient(app) as c:
        act_as(COMMISSIONER)
        yield c
    app.dependency_overrides.clear()


def create_league(client, **overrides):
    body = {"name": "Journey 2027", "year": 2027, "players": ["Ann", "Bob"],
            "rounds": 2, "pick_seconds": 0, "visibility": "private", **overrides}
    made = client.post("/api/leagues", json=body)
    assert made.status_code == 201, made.text
    return made.json()["league_id"]


def draft_everything(client, league, *, start_at=1):
    """Pick for whoever is on the clock until the board is full. Returns the pick order."""
    order = []
    for n in range(start_at, 100):
        state = client.get(f"/api/leagues/{league}/draft").json()
        if state["on_the_clock"] is None:
            break
        player = state["on_the_clock"]["player"]
        made = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": player, "tmdb_id": 1000 + n,
                                 "title": f"Film {n}", "poster_path": f"/p{n}.jpg"})
        assert made.status_code == 200, f"pick {n} for {player}: {made.text}"
        order.append(player)
    return order


# ---------------------------------------------------------------------------
# the whole thing
# ---------------------------------------------------------------------------

def test_a_season_from_creation_to_standings(client):
    """Create, draft every slot, read the table, put the season to bed."""
    league = create_league(client)

    setup = client.get(f"/api/leagues/{league}/draft").json()
    assert setup["status"] == "setup"
    assert setup["on_the_clock"] is None, "nobody is on the clock before the draft opens"

    started = client.post(f"/api/leagues/{league}/draft/start")
    assert started.status_code == 200
    assert started.json()["status"] == "drafting"
    assert len(started.json()["order"]) == 2

    order = draft_everything(client, league)
    assert len(order) == 4, "two players, two rounds"

    done = client.get(f"/api/leagues/{league}/draft").json()
    assert done["status"] == "complete"
    assert done["picks_made"] == done["total_picks"] == 4

    table = client.get(f"/api/leagues/{league}/leaderboard").json()
    assert {row["owner"] for row in table} == {"Ann", "Bob"}
    assert all(row["total"] == 0 for row in table), "nothing is scored until enrichment runs"

    rosters = client.get(f"/api/leagues/{league}/owners/Ann").json()
    assert len(rosters["movies"]) == 2

    settled = client.post(f"/api/leagues/{league}/freeze")
    assert settled.status_code == 200
    assert settled.json()["frozen_at"] is not None

    assert client.delete(f"/api/leagues/{league}").status_code == 204
    assert client.get(f"/api/leagues/{league}/draft").status_code == 404


def test_the_draft_snakes_over_the_wire(client):
    """Round 2 runs backwards. Proven through HTTP, not just in the repo layer."""
    league = create_league(client, players=["Ann", "Bob", "Cal"], rounds=2)
    client.post(f"/api/leagues/{league}/draft/start")

    order = draft_everything(client, league)
    assert len(order) == 6
    assert order[:3] == list(reversed(order[3:])), f"not a snake: {order}"


def test_a_watch_moves_the_standings(client):
    """The scoring rule the league actually cares about, end to end."""
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")
    draft_everything(client, league)

    before = {r["owner"]: r["total"] for r in
              client.get(f"/api/leagues/{league}/leaderboard").json()}

    watched = client.post(f"/api/leagues/{league}/movies/Ann/1/watch",
                          json={"viewer": "Ann", "watched": True})
    assert watched.status_code == 200

    after = {r["owner"]: r["total"] for r in
             client.get(f"/api/leagues/{league}/leaderboard").json()}
    assert after["Ann"] == before["Ann"] + 5, "own pick, own watch, +5"
    assert after["Bob"] == before["Bob"], "and nobody else moves"


# ---------------------------------------------------------------------------
# more than one person
# ---------------------------------------------------------------------------

def test_a_friend_claims_a_slot_and_takes_over_their_picks(client):
    """The handover the nullable user_id exists for."""
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")

    act_as(FRIEND)
    claimed = client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    assert claimed.status_code == 200

    # The commissioner can still act for Bob, who is unclaimed.
    act_as(COMMISSIONER)
    state = client.get(f"/api/leagues/{league}/draft").json()
    on_clock = state["on_the_clock"]["player"]
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 555, "title": "X"})
    if on_clock == "Ann":
        assert response.status_code == 403, "Ann belongs to the friend now"
        act_as(FRIEND)
        response = client.post(f"/api/leagues/{league}/draft/pick",
                               json={"player": "Ann", "tmdb_id": 555, "title": "X"})
    assert response.status_code == 200


def test_a_stranger_cannot_touch_the_draft(client):
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]

    act_as(STRANGER)
    assert client.get(f"/api/leagues/{league}/draft").status_code == 404
    assert client.post(f"/api/leagues/{league}/draft/pick",
                       json={"player": on_clock, "tmdb_id": 9, "title": "Nope"}).status_code == 403
    assert client.post(f"/api/leagues/{league}/draft/start").status_code == 403
    assert client.delete(f"/api/leagues/{league}").status_code == 403


def test_a_public_season_is_readable_by_a_signed_out_visitor(client):
    league = create_league(client, visibility="public")
    client.post(f"/api/leagues/{league}/draft/start")
    draft_everything(client, league)

    act_as(None)
    assert client.get(f"/api/leagues/{league}/draft").json()["status"] == "complete"
    assert len(client.get(f"/api/leagues/{league}/leaderboard").json()) == 2
    assert client.post(f"/api/leagues/{league}/freeze").status_code == 401


# ---------------------------------------------------------------------------
# the things that go wrong
# ---------------------------------------------------------------------------

def test_the_same_film_cannot_be_taken_twice(client):
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")

    first = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]
    client.post(f"/api/leagues/{league}/draft/pick",
                json={"player": first, "tmdb_id": 42, "title": "Taken"})

    second = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]
    clash = client.post(f"/api/leagues/{league}/draft/pick",
                        json={"player": second, "tmdb_id": 42, "title": "Taken"})
    assert clash.status_code == 409
    assert "already" in clash.json()["detail"].lower()


def test_picking_out_of_turn_is_refused(client):
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")
    state = client.get(f"/api/leagues/{league}/draft").json()
    waiting = next(p for p in state["order"] if p != state["on_the_clock"]["player"])

    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": waiting, "tmdb_id": 7, "title": "Early"})
    assert response.status_code == 409


def test_a_finished_draft_takes_no_more_picks(client):
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")
    draft_everything(client, league)

    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": "Ann", "tmdb_id": 999, "title": "Too late"})
    assert response.status_code == 409


def test_deleting_a_league_takes_its_picks_with_it(client, never_touch_the_real_database):
    from app.db.models import Entry
    league = create_league(client)
    client.post(f"/api/leagues/{league}/draft/start")
    draft_everything(client, league)

    with never_touch_the_real_database() as session:
        assert session.query(Entry).filter(Entry.league_id == league).count() == 4

    client.delete(f"/api/leagues/{league}")

    with never_touch_the_real_database() as session:
        assert session.query(Entry).filter(Entry.league_id == league).count() == 0

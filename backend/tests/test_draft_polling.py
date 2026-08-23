"""ETag on the draft board, which is what makes polling cheap."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

from .helpers import act_as

OWNER = "user_owner"


@pytest.fixture
def client(never_touch_the_real_database):
    with TestClient(app) as c:
        act_as(OWNER)
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def league(client):
    made = client.post("/api/leagues", json={
        "name": "Poll", "year": 2027, "players": ["Ann", "Bob"], "rounds": 1,
        "pick_seconds": 0, "visibility": "private"})
    assert made.status_code == 201, made.text
    league_id = made.json()["league_id"]
    client.post(f"/api/leagues/{league_id}/draft/start")
    return league_id


def test_a_board_carries_an_etag(client, league):
    response = client.get(f"/api/leagues/{league}/draft")
    assert response.status_code == 200
    assert response.headers["etag"].startswith('W/"')


def test_an_unchanged_board_answers_304(client, league):
    """The whole point: a poll that finds nothing sends no body."""
    first = client.get(f"/api/leagues/{league}/draft")
    again = client.get(f"/api/leagues/{league}/draft",
                       headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


def test_the_etag_is_stable_across_repeated_reads(client, league):
    tags = {client.get(f"/api/leagues/{league}/draft").headers["etag"] for _ in range(3)}
    assert len(tags) == 1, "an unstable tag makes every poll a miss"


def test_a_pick_changes_the_etag(client, league):
    before = client.get(f"/api/leagues/{league}/draft")
    on_clock = before.json()["on_the_clock"]["player"]
    client.post(f"/api/leagues/{league}/draft/pick",
                json={"player": on_clock, "tmdb_id": 77, "title": "Something"})

    after = client.get(f"/api/leagues/{league}/draft",
                       headers={"If-None-Match": before.headers["etag"]})
    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]
    assert after.json()["picks_made"] == 1


def test_the_ticking_clock_does_not_change_the_etag(never_touch_the_real_database):
    """seconds_remaining changes on every request by definition.

    Including it would make every poll a miss and the ETag pointless -- the browser counts
    down locally from clock_started_at anyway.
    """
    from app.routes_leagues import _etag
    base = {"picks_made": 3, "status": "drafting", "seconds_remaining": 42}
    assert _etag(base) == _etag({**base, "seconds_remaining": 7})


def test_a_stale_etag_gets_the_full_board(client, league):
    response = client.get(f"/api/leagues/{league}/draft",
                          headers={"If-None-Match": 'W/"not-a-real-tag"'})
    assert response.status_code == 200
    assert response.json()["league_id"] == league


def test_a_304_still_carries_the_etag(client, league):
    """Without it the client has nothing to send on the next poll."""
    first = client.get(f"/api/leagues/{league}/draft")
    again = client.get(f"/api/leagues/{league}/draft",
                       headers={"If-None-Match": first.headers["etag"]})
    assert again.headers["etag"] == first.headers["etag"]


def test_a_stranger_still_cannot_poll_a_private_board(client, league):
    act_as("user_stranger")
    assert client.get(f"/api/leagues/{league}/draft").status_code == 404


def test_a_signed_out_visitor_can_read_a_public_league_pool(client, league):
    """The asymmetry this PR fixes: the board was readable and the pool was not."""
    act_as(OWNER)
    client.patch(f"/api/leagues/{league}", json={"visibility": "public"})
    act_as(None)
    assert client.get(f"/api/leagues/{league}/draft").status_code == 200
    # No TMDB key in tests, so the pool answers 503 rather than 401 -- the point is that
    # it is no longer an authentication failure.
    assert client.get(f"/api/leagues/{league}/pool").status_code != 401


# ---------------------------------------------------------------------------
# What the board tells a viewer they may do
# ---------------------------------------------------------------------------

def test_the_creator_may_pick_for_an_unclaimed_slot(client, league):
    viewer = client.get(f"/api/leagues/{league}/draft").json()["viewer"]
    assert viewer["can_pick"] is True
    assert viewer["is_member"] is True
    assert viewer["player"] is None, "the creator holds no slot until they claim one"


def test_a_member_waiting_their_turn_is_told_they_cannot_pick(client, league):
    """The board must not offer a DRAFT button that would 403."""
    state = client.get(f"/api/leagues/{league}/draft").json()
    waiting = next(p for p in state["order"] if p != state["on_the_clock"]["player"])

    act_as("user_waiting")
    client.post(f"/api/leagues/{league}/claim", json={"player": waiting})
    viewer = client.get(f"/api/leagues/{league}/draft").json()["viewer"]

    assert viewer["player"] == waiting
    assert viewer["is_member"] is True, "they are in the league"
    assert viewer["can_pick"] is False, "but it is not their turn"


def test_the_member_on_the_clock_is_told_they_can_pick(client, league):
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]

    act_as("user_turn")
    client.post(f"/api/leagues/{league}/claim", json={"player": on_clock})
    viewer = client.get(f"/api/leagues/{league}/draft").json()["viewer"]

    assert viewer["player"] == on_clock
    assert viewer["can_pick"] is True


def test_a_spectator_on_a_public_league_may_watch_but_not_act(client, league):
    """Public leagues are browsable, so this is a real caller, not a hypothetical."""
    act_as(OWNER)
    client.patch(f"/api/leagues/{league}", json={"visibility": "public"})

    for who in ("user_stranger", None):
        act_as(who)
        viewer = client.get(f"/api/leagues/{league}/draft").json()["viewer"]
        assert viewer["can_pick"] is False, who
        assert viewer["is_member"] is False, who
        assert viewer["player"] is None, who


def test_the_viewer_block_changes_the_etag(client, league):
    """Two people looking at one board must not share a cache entry.

    Without this the second person's poll could be answered 304 against the first
    person's permissions, and the board would offer them a button that 403s.
    """
    act_as(OWNER)
    client.patch(f"/api/leagues/{league}", json={"visibility": "public"})
    creator_tag = client.get(f"/api/leagues/{league}/draft").headers["etag"]

    act_as("user_other")
    other = client.get(f"/api/leagues/{league}/draft",
                       headers={"If-None-Match": creator_tag})
    assert other.status_code == 200, "a different viewer got the creator's cached board"
    assert other.headers["etag"] != creator_tag


def test_can_pick_goes_false_once_the_turn_passes(client, league):
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]
    assert client.get(f"/api/leagues/{league}/draft").json()["viewer"]["can_pick"] is True

    client.post(f"/api/leagues/{league}/draft/pick",
                json={"player": on_clock, "tmdb_id": 4242, "title": "Something"})

    # Still the creator, so still able to act for the next unclaimed player.
    assert client.get(f"/api/leagues/{league}/draft").json()["viewer"]["can_pick"] is True

    # Someone outside the league, reading it because it is public.
    client.patch(f"/api/leagues/{league}", json={"visibility": "public"})
    act_as("user_nobody")
    assert client.get(f"/api/leagues/{league}/draft").json()["viewer"]["can_pick"] is False

"""Tests for public/private league visibility.

Visibility governs READING only. Writing is always ownership-based, so making a league
public must not grant a stranger any ability to change it -- several tests below exist
purely to hold that line.
"""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db.models import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC
from app.main import app
from .helpers import act_as

CREATOR = "user_creator"
MEMBER = "user_member"
STRANGER = "user_stranger"


@pytest.fixture
def client(never_touch_the_real_database):
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def league(client):
    act_as(CREATOR)
    # Explicitly private: most of this file tests private behaviour, and a fixture that
    # leans on whatever the default happens to be silently changes meaning when the
    # default does -- which is exactly what happened when creation moved to public.
    created = client.post("/api/leagues", json={
        "name": "Test", "year": 2027, "players": ["Ann", "Bob"], "rounds": 1,
        "pick_seconds": 0, "visibility": "private"})
    assert created.status_code == 201, created.text
    league_id = created.json()["league_id"]
    act_as(MEMBER)
    client.post(f"/api/leagues/{league_id}/claim", json={"player": "Ann"})
    act_as(CREATOR)
    return league_id


def make_public(client, league_id):
    act_as(CREATOR)
    r = client.patch(f"/api/leagues/{league_id}", json={"visibility": "public"})
    assert r.status_code == 200, r.text
    assert r.json()["visibility"] == "public"


READ_ROUTES = ["/draft", "/leaderboard"]


# ---------------------------------------------------------------------------
# the default
# ---------------------------------------------------------------------------

def test_a_new_league_is_public_by_default(client):
    """The product default. A league nobody can find is not much of a league, and the
    people you want reading it mostly do not have accounts."""
    client.post("/api/leagues", json={"name": "Default", "year": 2027,
                                      "players": ["Ann", "Bob"], "rounds": 1})
    listed = client.get("/api/leagues").json()
    assert listed[0]["visibility"] == VISIBILITY_PUBLIC


def test_creation_can_ask_for_private(client):
    client.post("/api/leagues", json={"name": "Hidden", "year": 2027,
                                      "players": ["Ann", "Bob"], "rounds": 1,
                                      "visibility": "private"})
    listed = client.get("/api/leagues").json()
    assert listed[0]["visibility"] == VISIBILITY_PRIVATE


def test_creation_rejects_an_unknown_visibility(client):
    response = client.post("/api/leagues", json={"name": "Odd", "year": 2027,
                                                 "players": ["Ann", "Bob"], "rounds": 1,
                                                 "visibility": "unlisted"})
    assert response.status_code == 422


def test_the_storage_default_stays_private(never_touch_the_real_database):
    """The column default is a safety net, not the product default.

    A row created by code that forgot to say is private; a user creating a league through
    the API gets public. The two differ on purpose -- forgetting should fail closed.
    """
    from app.db.models import League
    with never_touch_the_real_database() as s:
        league = League(name="Bare", year=2027, rounds=1)
        s.add(league)
        s.commit()
        assert league.visibility == VISIBILITY_PRIVATE


# ---------------------------------------------------------------------------
# private
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", READ_ROUTES)
def test_a_stranger_cannot_read_a_private_league(client, league, route):
    act_as(STRANGER)
    assert client.get(f"/api/leagues/{league}{route}").status_code == 404


@pytest.mark.parametrize("route", READ_ROUTES)
def test_a_signed_out_visitor_cannot_read_a_private_league(client, league, route):
    act_as(None)
    assert client.get(f"/api/leagues/{league}{route}").status_code == 404


def test_a_private_league_answers_404_not_403(client, league):
    """403 would confirm the league exists, which leaks the thing privacy is for."""
    act_as(STRANGER)
    response = client.get(f"/api/leagues/{league}/leaderboard")
    assert response.status_code == 404
    assert str(league) not in response.json()["detail"]
    assert "Test" not in response.json()["detail"]


@pytest.mark.parametrize("route", READ_ROUTES)
def test_members_can_read_their_own_private_league(client, league, route):
    for who in (CREATOR, MEMBER):
        act_as(who)
        assert client.get(f"/api/leagues/{league}{route}").status_code == 200, who


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route", READ_ROUTES)
def test_anyone_can_read_a_public_league(client, league, route):
    make_public(client, league)
    for who in (STRANGER, None):
        act_as(who)
        assert client.get(f"/api/leagues/{league}{route}").status_code == 200, who


def test_a_public_league_is_readable_by_a_signed_out_visitor(client, league):
    """The point of public: a standings link works for someone with no account at all."""
    make_public(client, league)
    act_as(None)
    body = client.get(f"/api/leagues/{league}/leaderboard").json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# public grants READING and nothing else
# ---------------------------------------------------------------------------

def test_public_does_not_let_a_stranger_edit_the_league(client, league):
    make_public(client, league)
    act_as(STRANGER)
    assert client.patch(f"/api/leagues/{league}", json={"name": "Hijacked"}).status_code == 403


def test_public_does_not_let_a_stranger_delete_the_league(client, league):
    make_public(client, league)
    act_as(STRANGER)
    assert client.delete(f"/api/leagues/{league}").status_code == 403


def test_public_does_not_let_a_stranger_pick(client, league):
    make_public(client, league)
    act_as(CREATOR)
    client.post(f"/api/leagues/{league}/draft/start")
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]
    act_as(STRANGER)
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 1, "title": "A"})
    assert response.status_code == 403


def test_a_public_league_appears_on_everyones_list(client, league):
    """Reverses the original rule, deliberately.

    This shipped as "public means the link works, not that it appears on everyone's home
    screen". That made public leagues undiscoverable: with no directory, the only way to
    reach one was a link somebody sent you, and a signed-out visitor met a login wall
    instead of the app. Browsable is the product decision; `mine` keeps them grouped.
    """
    make_public(client, league)
    act_as(STRANGER)
    listed = client.get("/api/leagues").json()
    assert [lg["name"] for lg in listed] == ["Test"]
    assert listed[0]["mine"] is False
    assert listed[0]["is_creator"] is False


def test_a_private_league_never_appears_on_a_strangers_list(client, league):
    act_as(STRANGER)
    assert client.get("/api/leagues").json() == []


def test_a_signed_out_visitor_sees_public_leagues(client, league):
    """The whole point of this change: arrive with no account and still see something."""
    make_public(client, league)
    act_as(None)
    listed = client.get("/api/leagues").json()
    assert [lg["name"] for lg in listed] == ["Test"]
    assert listed[0]["mine"] is False


def test_a_signed_out_visitor_sees_nothing_when_nothing_is_public(client, league):
    act_as(None)
    assert client.get("/api/leagues").json() == []


def test_your_own_leagues_are_tagged_mine(client, league):
    act_as(CREATOR)
    listed = client.get("/api/leagues").json()
    assert listed[0]["mine"] is True
    assert listed[0]["is_creator"] is True

    act_as(MEMBER)          # holds a slot, did not create it
    listed = client.get("/api/leagues").json()
    assert listed[0]["mine"] is True
    assert listed[0]["is_creator"] is False


def test_a_backup_still_holds_only_your_own_leagues(client, league):
    """A public league you can *read* is not a league you should be backing up."""
    make_public(client, league)
    act_as(STRANGER)
    assert client.get("/api/export").json()["leagues"] == []


def test_only_the_creator_can_change_visibility(client, league):
    act_as(MEMBER)          # a member, not the creator
    assert client.patch(f"/api/leagues/{league}",
                        json={"visibility": "public"}).status_code == 403


def test_an_invalid_visibility_is_rejected(client, league):
    act_as(CREATOR)
    assert client.patch(f"/api/leagues/{league}",
                        json={"visibility": "semi-public"}).status_code == 422


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_the_archive_export_requires_signing_in(client, league):
    act_as(None)
    assert client.get("/api/export").status_code == 401


def test_the_archive_export_holds_only_your_own_leagues(client, league):
    """Regression: this route once returned every league in the database to anyone."""
    act_as(STRANGER)
    body = client.get("/api/export").json()
    assert body["leagues"] == []

    act_as(CREATOR)
    assert [lg["name"] for lg in client.get("/api/export").json()["leagues"]] == ["Test"]


def test_a_public_league_is_still_not_exportable_by_a_stranger(client, league):
    """Public grants the standings, not every account id that claimed a slot."""
    make_public(client, league)
    act_as(STRANGER)
    assert client.get(f"/api/leagues/{league}/export").status_code == 404


def test_visibility_survives_a_backup_round_trip(client, league):
    """Third column in a row that a backup would have silently dropped."""
    make_public(client, league)
    act_as(CREATOR)
    assert client.get("/api/export").json()["leagues"][0]["visibility"] == VISIBILITY_PUBLIC

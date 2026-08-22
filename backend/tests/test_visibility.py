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

CREATOR = "user_creator"
MEMBER = "user_member"
STRANGER = "user_stranger"


@pytest.fixture
def client(never_touch_the_real_database):
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def act_as(user_id):
    """Sign requests as `user_id`; None means signed out."""
    app.dependency_overrides[auth.current_user_optional] = lambda: user_id
    if user_id is None:
        def _401():
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Sign in to do that.")
        app.dependency_overrides[auth.current_user] = _401
    else:
        app.dependency_overrides[auth.current_user] = lambda: user_id


@pytest.fixture
def league(client):
    act_as(CREATOR)
    created = client.post("/api/leagues", json={
        "name": "Test", "year": 2027, "players": ["Ann", "Bob"], "rounds": 1,
        "pick_seconds": 0})
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

def test_a_new_league_is_private(client, league):
    """The safe direction: a league exposed by accident cannot be un-seen."""
    listed = client.get("/api/leagues").json()
    assert listed[0]["visibility"] == VISIBILITY_PRIVATE


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


def test_public_does_not_put_the_league_on_a_strangers_list(client, league):
    """Public means the link works, not that it appears in everyone's home screen."""
    make_public(client, league)
    act_as(STRANGER)
    assert client.get("/api/leagues").json() == []


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

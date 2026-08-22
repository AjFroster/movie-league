"""Tests for identity and permissions.

Most of this file is denials. A suite that only checks that the right person may act
proves nothing about whether the wrong person is stopped, and stopping the wrong person is
the entire reason accounts exist.
"""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt as pyjwt

from app import auth
from app.db import repo
from app.main import app

CREATOR = "user_creator"
OTHER = "user_other"


@pytest.fixture
def client(never_touch_the_real_database):
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def act_as(user_id):
    """Sign every subsequent request as `user_id`.

    Both dependencies: read routes take the optional one, so overriding only `current_user`
    leaves reads resolving to the real local identity and answering 404 on a private league.
    """
    app.dependency_overrides[auth.current_user] = lambda: user_id
    app.dependency_overrides[auth.current_user_optional] = lambda: user_id


@pytest.fixture
def league(client, never_touch_the_real_database):
    """A league created by CREATOR, drafting, with nobody's slot claimed."""
    act_as(CREATOR)
    body = {"name": "Test", "year": 2027, "players": ["Ann", "Bob"], "rounds": 1,
            "pick_seconds": 0}
    created = client.post("/api/leagues", json=body)
    assert created.status_code == 201, created.text
    league_id = created.json()["league_id"]
    client.post(f"/api/leagues/{league_id}/draft/start")
    return league_id


# ---------------------------------------------------------------------------
# local identity
# ---------------------------------------------------------------------------

def test_without_clerk_every_request_is_the_same_local_user(client, monkeypatch):
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    assert not auth.clerk_configured()

    from fastapi import Request
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    assert auth.current_user(Request(scope)) == auth.LOCAL_USER_ID


def test_local_mode_is_allowed_on_a_sqlite_localhost_setup(monkeypatch):
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.setenv("CORS_ORIGIN", "http://localhost:5173")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    auth.verify_startup_configuration()          # must not raise


def test_local_mode_refuses_to_start_against_postgres(monkeypatch):
    """The guard that stops unauthenticated access reaching a deployment."""
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user@host/db")

    with pytest.raises(RuntimeError, match="not SQLite"):
        auth.verify_startup_configuration()


def test_local_mode_refuses_to_start_on_a_public_origin(monkeypatch):
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CORS_ORIGIN", "https://movieleague.example.com")

    with pytest.raises(RuntimeError, match="not a localhost origin"):
        auth.verify_startup_configuration()


def test_a_configured_provider_lifts_the_local_guard(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://real.clerk.accounts.dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user@host/db")
    monkeypatch.setenv("CORS_ORIGIN", "https://movieleague.example.com")
    auth.verify_startup_configuration()          # must not raise


# ---------------------------------------------------------------------------
# token verification
# ---------------------------------------------------------------------------

ISSUER = "https://test.clerk.accounts.dev"


@pytest.fixture
def signing(monkeypatch):
    """A synthetic RSA keypair standing in for Clerk's, with the JWKS lookup stubbed."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    monkeypatch.setenv("CLERK_ISSUER", ISSUER)
    monkeypatch.setattr(auth, "_jwks_client", None)

    class FakeKey:
        def __init__(self, k): self.key = k

    class FakeClient:
        uri = f"{ISSUER}/.well-known/jwks.json"
        def get_signing_key_from_jwt(self, _token): return FakeKey(key.public_key())

    monkeypatch.setattr(auth, "_client", lambda: FakeClient())

    def mint(**overrides):
        now = int(time.time())
        claims = {"sub": "user_abc", "iss": ISSUER, "iat": now, "exp": now + 3600}
        claims.update(overrides)
        return pyjwt.encode(claims, pem, algorithm="RS256")

    return mint


def _request_with(token):
    from fastapi import Request
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request({"type": "http", "headers": headers, "method": "GET", "path": "/"})


def test_a_valid_token_yields_its_subject(signing):
    assert auth.current_user(_request_with(signing())) == "user_abc"


def test_an_expired_token_is_rejected(signing):
    now = int(time.time())
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(signing(exp=now - 10, iat=now - 3600)))
    assert e.value.status_code == 401


def test_a_token_from_another_issuer_is_rejected(signing):
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(signing(iss="https://evil.example.com")))
    assert e.value.status_code == 401


def test_a_tampered_token_is_rejected(signing):
    token = signing()
    head, payload, sig = token.split(".")
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(f"{head}.{payload}.{sig[:-4]}AAAA"))
    assert e.value.status_code == 401


def test_a_token_signed_by_the_wrong_key_is_rejected(signing, monkeypatch):
    """The signature must actually be checked, not merely decoded."""
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = stranger.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    now = int(time.time())
    forged = pyjwt.encode({"sub": "user_abc", "iss": ISSUER, "iat": now, "exp": now + 60},
                          pem, algorithm="RS256")
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(forged))
    assert e.value.status_code == 401


def test_a_missing_header_is_rejected_when_a_provider_is_configured(signing):
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(None))
    assert e.value.status_code == 401


def test_a_token_without_a_subject_is_rejected(signing):
    with pytest.raises(Exception) as e:
        auth.current_user(_request_with(signing(sub="")))
    assert e.value.status_code == 401


# ---------------------------------------------------------------------------
# creator-only actions -- the denials
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("patch", "", {"name": "Renamed"}),
    ("patch", "", {"settles_on": "2028-01-01"}),
    ("patch", "", {"pick_seconds": 30}),
    ("delete", "", None),
    ("post", "/freeze", None),
    ("post", "/draft/start", None),
    ("post", "/enrich-all", None),
])
def test_a_stranger_cannot_administer_someone_elses_league(client, league, method, path,
                                                           body):
    act_as(OTHER)
    response = getattr(client, method)(f"/api/leagues/{league}{path}",
                                       **({"json": body} if body else {}))
    assert response.status_code == 403, f"{method.upper()} {path} was allowed"
    assert "created this league" in response.json()["detail"]


def test_the_creator_can_administer_their_own_league(client, league):
    act_as(CREATOR)
    assert client.patch(f"/api/leagues/{league}", json={"name": "Renamed"}).status_code == 200


def test_a_stranger_cannot_delete_a_league(client, league, never_touch_the_real_database):
    act_as(OTHER)
    assert client.delete(f"/api/leagues/{league}").status_code == 403
    with never_touch_the_real_database() as s:
        assert repo.get_league(s, league) is not None      # still there


# ---------------------------------------------------------------------------
# acting as a player
# ---------------------------------------------------------------------------

def test_the_creator_may_pick_for_an_unclaimed_slot(client, league):
    """The single-laptop draft: one person picking for everyone in the room."""
    act_as(CREATOR)
    state = client.get(f"/api/leagues/{league}/draft").json()
    on_clock = state["on_the_clock"]["player"]
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 1, "title": "A"})
    assert response.status_code == 200, response.text


def test_a_stranger_may_not_pick_for_an_unclaimed_slot(client, league):
    act_as(CREATOR)
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]

    act_as(OTHER)
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 1, "title": "A"})
    assert response.status_code == 403
    assert "has not been claimed" in response.json()["detail"]


def test_claiming_a_slot_lets_that_account_pick(client, league):
    act_as(CREATOR)
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]

    act_as(OTHER)
    assert client.post(f"/api/leagues/{league}/claim",
                       json={"player": on_clock}).status_code == 200
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 1, "title": "A"})
    assert response.status_code == 200, response.text


def test_the_creator_loses_the_slot_once_someone_claims_it(client, league):
    """Claiming means it is yours. The pick clock covers a player who goes silent."""
    act_as(CREATOR)
    on_clock = client.get(f"/api/leagues/{league}/draft").json()["on_the_clock"]["player"]

    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": on_clock})

    act_as(CREATOR)
    response = client.post(f"/api/leagues/{league}/draft/pick",
                           json={"player": on_clock, "tmdb_id": 1, "title": "A"})
    assert response.status_code == 403
    assert "someone else's slot" in response.json()["detail"]


def test_a_watch_can_only_be_ticked_by_the_person_who_watched(client, league):
    act_as(CREATOR)
    state = client.get(f"/api/leagues/{league}/draft").json()
    for _ in range(2):
        state = client.get(f"/api/leagues/{league}/draft").json()
        if state["on_the_clock"] is None:
            break
        who = state["on_the_clock"]["player"]
        client.post(f"/api/leagues/{league}/draft/pick",
                    json={"player": who, "tmdb_id": hash(who) % 9999, "title": who})

    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    # Ann's account ticking Bob's box: Bob's watch, not Ann's.
    response = client.post(f"/api/leagues/{league}/movies/Ann/1/watch",
                           json={"viewer": "Bob", "watched": True})
    assert response.status_code == 403


def test_a_non_member_cannot_autopick(client, league):
    act_as(OTHER)
    response = client.post(f"/api/leagues/{league}/draft/autopick")
    assert response.status_code == 403
    assert "not in this league" in response.json()["detail"]


# ---------------------------------------------------------------------------
# claiming
# ---------------------------------------------------------------------------

def test_a_claimed_slot_cannot_be_taken_by_someone_else(client, league):
    act_as(OTHER)
    assert client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"}).status_code == 200
    act_as("user_third")
    response = client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    assert response.status_code == 409
    assert "already been claimed" in response.json()["detail"]


def test_one_account_cannot_hold_two_slots_in_a_league(client, league):
    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    response = client.post(f"/api/leagues/{league}/claim", json={"player": "Bob"})
    assert response.status_code == 409
    assert "already playing this league" in response.json()["detail"]


def test_claiming_an_unknown_player_is_a_404(client, league):
    act_as(OTHER)
    assert client.post(f"/api/leagues/{league}/claim",
                       json={"player": "Nobody"}).status_code == 404


def test_you_may_release_your_own_slot(client, league):
    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    assert client.delete(f"/api/leagues/{league}/claim/Ann").status_code == 204


def test_you_may_not_release_someone_elses_slot(client, league):
    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    act_as("user_third")
    response = client.delete(f"/api/leagues/{league}/claim/Ann")
    assert response.status_code == 403


def test_the_creator_may_release_anyones_slot(client, league):
    """Makes a wrong claim fixable; without it a mistake locks a slot for the season."""
    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    act_as(CREATOR)
    assert client.delete(f"/api/leagues/{league}/claim/Ann").status_code == 204


# ---------------------------------------------------------------------------
# visibility
# ---------------------------------------------------------------------------

def test_your_league_list_holds_only_your_leagues(client, league):
    act_as(OTHER)
    assert client.get("/api/leagues").json() == []

    act_as(CREATOR)
    assert [l["id"] for l in client.get("/api/leagues").json()] == [league]


def test_claiming_a_slot_puts_the_league_on_your_list(client, league):
    act_as(OTHER)
    client.post(f"/api/leagues/{league}/claim", json={"player": "Ann"})
    listed = client.get("/api/leagues").json()
    assert [l["id"] for l in listed] == [league]
    assert listed[0]["your_player"] == "Ann"
    assert "Ann" not in listed[0]["unclaimed"]

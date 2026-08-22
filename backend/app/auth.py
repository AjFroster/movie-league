"""Who is making this request, and whether they may do it.

There is no flag that turns authorization off. The permission checks always run; only the
source of identity changes -- a verified JWT subject when Clerk is configured, and
LOCAL_USER_ID when it is not. Unauthenticated is a database with one account in it, not a
branch that skips checks.

`verify_startup_configuration` refuses to boot in local-identity mode unless the database
is SQLite and CORS_ORIGIN is localhost, so a deployment cannot quietly serve open access.
"""
import os
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient

from .db import repo
from .db.models import VISIBILITY_PUBLIC, League, Player

# The single identity used when no identity provider is configured. Deliberately unlike a
# Clerk subject (`user_2ab...`) so the two can never be confused in a database or a log.
# NOTE: migration 1dc80faa982d hardcodes this string when backfilling existing leagues.
# Overridable so two processes can run as different people against one database, which is
# what the multi-user browser tests need. It changes nothing about safety: this identity is
# only ever used when no provider is configured, and that already requires SQLite and a
# localhost origin. One process is still exactly one user; it just has a nameable one.
LOCAL_USER_ID = os.environ.get("LEAGUE_LOCAL_USER") or "local"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
_jwks_client: PyJWKClient | None = None


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

def jwks_url() -> str | None:
    """Where to fetch Clerk's signing keys, derived from the issuer if not given."""
    explicit = os.environ.get("CLERK_JWKS_URL")
    if explicit:
        return explicit
    issuer = os.environ.get("CLERK_ISSUER")
    return f"{issuer.rstrip('/')}/.well-known/jwks.json" if issuer else None


def clerk_configured() -> bool:
    return jwks_url() is not None


def _looks_local(origin: str) -> bool:
    host = urlparse(origin).hostname if "//" in origin else origin.split(":")[0]
    return host in _LOCAL_HOSTS


def _assert_local_mode_is_safe() -> None:
    """Refuse to run without an identity provider anywhere that looks hosted.

    Either signal being non-local stops the process; a deployment flips both.
    """
    from .db.session import database_url

    reasons = []
    if not database_url().startswith("sqlite"):
        reasons.append("DATABASE_URL is not SQLite")
    origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    if not _looks_local(origin):
        reasons.append(f"CORS_ORIGIN is {origin!r}, not a localhost origin")

    if reasons:
        raise RuntimeError(
            "Refusing to start: no identity provider is configured, so every request "
            "would be treated as the same single local user, but " + " and ".join(reasons)
            + ". Set CLERK_ISSUER (or CLERK_JWKS_URL) to require real accounts."
        )


def verify_startup_configuration() -> None:
    """Called at boot. Either Clerk is configured, or this had better be a laptop."""
    if not clerk_configured():
        _assert_local_mode_is_safe()


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

def _client() -> PyJWKClient:
    global _jwks_client
    url = jwks_url()
    # PyJWKClient caches fetched keys, so a token does not cost a round trip to Clerk.
    if _jwks_client is None or _jwks_client.uri != url:
        _jwks_client = PyJWKClient(url, cache_keys=True)
    return _jwks_client


def _subject_from_token(token: str) -> str:
    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=os.environ.get("CLERK_ISSUER"),
            # Clerk session tokens carry no `aud`, so there is nothing to verify against;
            # `iss` and the signature are what bind a token to this instance.
            options={"verify_aud": False, "require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as e:
        # The message is the library's, never the token: a token in a response body or a
        # log is a session someone else can replay.
        raise HTTPException(status_code=401, detail=f"Invalid session token: {e}") from None

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Session token carries no subject.")
    return subject


def current_user(request: Request) -> str:
    """The identity behind this request. Never None -- callers get a user or a 401."""
    if not clerk_configured():
        return LOCAL_USER_ID

    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Sign in to do that.")
    return _subject_from_token(token.strip())


def current_user_optional(request: Request) -> str | None:
    """The identity behind this request, or None if there is not one.

    A missing token means anonymous, which read routes need for public leagues. A token
    that is present but invalid still 401s: downgrading a forgery to "anonymous" would
    turn the check into "send a bad token to look like a stranger".
    """
    if not clerk_configured():
        return LOCAL_USER_ID
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return _subject_from_token(token.strip())


CurrentUser = Depends(current_user)
MaybeUser = Depends(current_user_optional)


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------

def require_creator(session, league_id: int, user_id: str) -> League:
    """Only the account that created a league may change or destroy it."""
    league = repo.get_league(session, league_id)
    if league.owner_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the person who created this league can do that.")
    return league


def require_member(session, league_id: int, user_id: str) -> League:
    """Created the league, or holds a slot in it.

    Used for auto-picking, where any member may ask so a draft advances even when the
    player on the clock has closed their laptop. The server re-checks its own deadline,
    so asking early achieves nothing.
    """
    league = repo.get_league(session, league_id)
    if not repo.is_member(session, league_id, user_id):
        raise HTTPException(status_code=403, detail="You are not in this league.")
    return league


def require_viewer(session, league_id: int, user_id: str | None) -> League:
    """May this caller READ this league? Public: anyone. Private: members only.

    Separate from write permission, which is always ownership-based.
    """
    league = repo.get_league(session, league_id)
    if league.visibility == VISIBILITY_PUBLIC:
        return league
    if user_id is not None and repo.is_member(session, league_id, user_id):
        return league
    # 404, not 403: answering "forbidden" for a private league confirms it exists, which
    # leaks the very thing privacy is for. An outsider cannot distinguish a private league
    # from one that was never created.
    raise HTTPException(status_code=404, detail="No such league.")


def require_actor(session, league_id: int, user_id: str, player_name: str) -> Player:
    """May `user_id` pick or tick watches as `player_name`?

    Yes if they claimed the slot, or if it is unclaimed and they created the league --
    that second case is the single-laptop draft.
    """
    league = repo.get_league(session, league_id)
    player = next((p for p in league.players if p.name == player_name), None)
    if player is None:
        raise HTTPException(status_code=422,
                            detail=f"No player named {player_name!r} in this league.")

    if player.user_id == user_id:
        return player
    if player.user_id is None and league.owner_user_id == user_id:
        return player

    if player.user_id is None:
        detail = (f"{player_name} has not been claimed yet, and only the league's creator "
                  "can act for an unclaimed player.")
    else:
        detail = f"{player_name} is someone else's slot."
    raise HTTPException(status_code=403, detail=detail)

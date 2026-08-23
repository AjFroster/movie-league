"""Who is in a league: claiming a player slot, releasing it, membership checks."""
from sqlalchemy.orm import Session

from ..models import Player
from .leagues import get_league


def claim_slot(session: Session, league_id: int, *, player_name: str,
               user_id: str) -> Player:
    """Attach an account to a player slot.

    Refuses a slot someone else already holds, and refuses a second slot in a league the
    account is already in -- `uq_claim_per_league` would reject it anyway, but a clear
    message beats an integrity error.
    """
    league = get_league(session, league_id)
    player = next((p for p in league.players if p.name == player_name), None)
    if player is None:
        raise LookupError(f"no player named {player_name!r} in this league")
    if player.user_id == user_id:
        return player
    if player.user_id is not None:
        raise ValueError(f"{player_name} has already been claimed")

    held = next((p for p in league.players if p.user_id == user_id), None)
    if held is not None:
        raise ValueError(f"you are already playing this league as {held.name}")

    player.user_id = user_id
    session.flush()
    return player


def release_slot(session: Session, league_id: int, *, player_name: str) -> Player:
    """Detach an account from a slot, returning it to unclaimed."""
    league = get_league(session, league_id)
    player = next((p for p in league.players if p.name == player_name), None)
    if player is None:
        raise LookupError(f"no player named {player_name!r} in this league")
    player.user_id = None
    session.flush()
    return player


def is_member(session: Session, league_id: int, user_id: str) -> bool:
    """Created the league, or holds a slot in it."""
    league = get_league(session, league_id)
    return (league.owner_user_id == user_id
            or any(p.user_id == user_id for p in league.players))


def can_act_as(session: Session, league_id: int, user_id: str | None,
               player_name: str | None) -> bool:
    """Non-raising twin of auth.require_actor, for telling a board what it may offer.

    The rule lives here once. A browser that re-derived it would drift from the server the
    first time the rule changed, and the drift would show as buttons that 403.
    """
    if user_id is None or player_name is None:
        return False
    league = get_league(session, league_id)
    player = next((p for p in league.players if p.name == player_name), None)
    if player is None:
        return False
    return (player.user_id == user_id
            or (player.user_id is None and league.owner_user_id == user_id))


def slot_held_by(session: Session, league_id: int, user_id: str | None) -> str | None:
    """The player this account has claimed in this league, if any."""
    if user_id is None:
        return None
    league = get_league(session, league_id)
    return next((p.name for p in league.players if p.user_id == user_id), None)

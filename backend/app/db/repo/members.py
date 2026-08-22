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

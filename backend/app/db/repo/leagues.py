"""Leagues themselves: creating, reading, renaming, settling, deleting."""
from datetime import date, datetime, timezone

from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session, selectinload

from ... import draft as draft_rules
from ..models import (
    STATUS_SETUP,
    VISIBILITIES,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    League,
    Player,
)


def get_league(session: Session, league_id: int) -> League:
    league = session.get(League, league_id)
    if league is None:
        raise LookupError(f"no league with id {league_id}")
    return league


def list_leagues(session: Session, *, user_id: str | None = None,
                 scope: str = "all") -> list[dict]:
    """Leagues a caller may see, each tagged `mine` so the UI can group them.

    `scope`:
      * "all"    -- yours plus every public league. What the home screen shows, and what a
                    signed-out visitor gets (for them, "yours" is empty).
      * "mine"   -- only leagues you created or hold a slot in. Used where "everything I
                    own" is the question, such as building a backup.

    `user_id=None` is a signed-out visitor: they see public leagues under "all", and
    nothing at all under "mine". Note this differs from the old meaning of None, which was
    "no filter" -- an unscoped listing is no longer reachable from a request.
    """
    mine_filter = or_(
        League.owner_user_id == user_id,
        League.id.in_(select(Player.league_id).where(Player.user_id == user_id)),
    ) if user_id is not None else false()

    query = (select(League).options(selectinload(League.players),
                                    selectinload(League.entries))
             .order_by(League.year.desc(), League.id.desc()))
    if scope == "mine":
        query = query.where(mine_filter)
    else:
        query = query.where(or_(mine_filter, League.visibility == VISIBILITY_PUBLIC))
    leagues = session.scalars(query).all()

    def _is_mine(lg: League) -> bool:
        return user_id is not None and (
            lg.owner_user_id == user_id or any(p.user_id == user_id for p in lg.players))
    return [{"id": lg.id, "name": lg.name, "year": lg.year, "rounds": lg.rounds,
             "status": lg.status, "players": [p.name for p in lg.players],
             "picks_made": sum(1 for e in lg.entries if e.tmdb_id is not None or e.title),
             "total_picks": len(lg.players) * lg.rounds,
             # Once a draft is done the meaningful progress is no longer picks but how
             # many films have ratings in yet -- the season running rather than the draft.
             "films_scored": sum(1 for e in lg.entries if e.imdb is not None),
             "films_total": len(lg.entries),
             "frozen_at": lg.frozen_at.isoformat() if lg.frozen_at else None,
             "settles_on": (lg.settles_on or default_settles_on(lg.year)).isoformat(),
             "pick_seconds": lg.pick_seconds,
             # Ready to settle once the date this league chose has passed.
             "season_ended": date.today() > (lg.settles_on or default_settles_on(lg.year)),
             "owner_user_id": lg.owner_user_id,
             "visibility": lg.visibility,
             # Lets the home screen split "your leagues" from "public leagues" without
             # re-deriving membership in the browser from data it should not need.
             "mine": _is_mine(lg),
             "is_creator": user_id is not None and lg.owner_user_id == user_id,
             # Which slots are still up for grabs, so the UI can offer them to claim.
             "unclaimed": [p.name for p in lg.players if p.user_id is None],
             "your_player": next((p.name for p in lg.players
                                  if user_id is not None and p.user_id == user_id), None)}
            for lg in leagues]


def create_league(session: Session, *, name: str, year: int, players: list[str],
                  rounds: int = 6, settles_on: date | None = None,
                  pick_seconds: int = 60, owner_user_id: str | None = None,
                  visibility: str = VISIBILITY_PRIVATE) -> League:
    names = [p.strip() for p in players]
    draft_rules.validate_setup(names, rounds)
    if visibility not in VISIBILITIES:
        raise ValueError(f"visibility must be one of {VISIBILITIES}, not {visibility!r}")
    league = League(name=name.strip() or f"League {year}", year=year, rounds=rounds,
                    status=STATUS_SETUP, owner_user_id=owner_user_id,
                    visibility=visibility,
                    settles_on=settles_on or default_settles_on(year),
                    pick_seconds=max(0, min(int(pick_seconds), 3600)))
    session.add(league)
    session.flush()
    for player_name in names:
        session.add(Player(league_id=league.id, name=player_name))
    session.flush()
    return league


def delete_league(session: Session, league_id: int) -> None:
    """Delete a league and everything under it, via the ON DELETE CASCADE relationships."""
    session.delete(get_league(session, league_id))
    session.flush()


def rename_league(session: Session, league_id: int, *, name: str) -> League:
    """Rename a league. The only mutable field once players exist.

    Everything else about a league -- its year, its roster, its draft order -- is something
    a pick was already made against, so changing it would invalidate the season rather
    than edit it.
    """
    league = get_league(session, league_id)
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("a league needs a name")
    league.name = cleaned[:120]
    session.flush()
    return league


def set_visibility(session: Session, league_id: int, *, visibility: str) -> League:
    """Public or private. Read access only -- writing is always ownership-based."""
    if visibility not in VISIBILITIES:
        raise ValueError(f"visibility must be one of {VISIBILITIES}, not {visibility!r}")
    league = get_league(session, league_id)
    league.visibility = visibility
    session.flush()
    return league


def set_settles_on(session: Session, league_id: int, *, on: date) -> League:
    """Change when this league's books close.

    Editable after the fact because the roster is what decides it, and the roster is not
    known until the draft is done -- a season whose last pick opens on Christmas Eve needs
    longer to settle than one that wrapped in September.
    """
    league = get_league(session, league_id)
    if on < date(league.year, 1, 1):
        raise ValueError("a season cannot settle before it starts")
    league.settles_on = on
    session.flush()
    return league


def set_pick_seconds(session: Session, league_id: int, *, seconds: int) -> League:
    """Change the per-pick time. 0 turns the clock off."""
    league = get_league(session, league_id)
    if not 0 <= seconds <= 3600:
        raise ValueError("pick timer must be between 0 and 3600 seconds")
    league.pick_seconds = int(seconds)
    session.flush()
    return league


def freeze_league(session: Session, league_id: int, *, frozen: bool = True) -> League:
    """Settle a season, or reopen it.

    Reversible on purpose: a freeze is a bookkeeping decision, not a destructive one, and
    a league that froze too early should be able to finish counting.
    """
    league = get_league(session, league_id)
    league.frozen_at = datetime.now(tz=timezone.utc) if frozen else None
    session.flush()
    return league

DEFAULT_SETTLE_MONTH_DAY = (12, 31)


def default_settles_on(year: int) -> date:
    """A season's books close at the end of its year unless the league says otherwise."""
    return date(year, *DEFAULT_SETTLE_MONTH_DAY)


def player_names(league: League) -> dict[int, str]:
    return {p.id: p.name for p in league.players}


def _now():
    return datetime.now(tz=timezone.utc)


def _aware(value):
    """SQLite hands back naive datetimes; compare in UTC rather than crashing on the mix."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

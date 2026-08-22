"""The draft: opening it, reporting its state, and recording a pick."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import draft as draft_rules
from ..models import STATUS_COMPLETE, STATUS_DRAFTING, STATUS_SETUP, Entry, League
from .leagues import _aware, _now, get_league, player_names


def start_draft(session: Session, league_id: int, *, rng=None) -> League:
    """Randomize the order and open the draft. Only legal from setup."""
    league = get_league(session, league_id)
    if league.status != STATUS_SETUP:
        raise ValueError(f"draft cannot start from status {league.status!r}")
    names = [p.name for p in league.players]
    draft_rules.validate_setup(names, league.rounds)
    league.draft_order = draft_rules.randomize_order(names, rng=rng)
    league.status = STATUS_DRAFTING
    league.clock_started_at = _now()
    session.flush()
    return league


def draft_state(session: Session, league_id: int) -> dict:
    """Everything a draft board needs, derived from the picks rather than a stored cursor."""
    league = get_league(session, league_id)
    order = league.draft_order or [p.name for p in league.players]
    names = player_names(league)
    picks = session.scalars(
        select(Entry).where(Entry.league_id == league_id, Entry.tmdb_id.isnot(None))
        .order_by(Entry.pick_number)).all()
    made = [{"pick": e.pick_number, "round": e.round, "player": names.get(e.player_id),
             "tmdb_id": e.tmdb_id, "title": e.title} for e in picks]
    # Nobody is on the clock until the draft opens. Before that `order` is the order the
    # names were typed in, not the randomised one, so naming a player here would name the
    # wrong player -- a wrong answer that happens not to be read yet.
    clock = (draft_rules.on_the_clock(order, league.rounds, len(made))
             if league.status == STATUS_DRAFTING else None)
    if clock is not None:
        # The snake's one counter-intuitive consequence: the player picking last in a round
        # picks first in the next. Worth surfacing at the moment someone is choosing.
        following = draft_rules.on_the_clock(order, league.rounds, len(made) + 1)
        clock = {**clock,
                 "back_to_back": following is not None
                 and following["player"] == clock["player"]}

    # Rosters, so the board can show each player's picks forming without a second request.
    rosters = []
    for name in order:
        owned = [p for p in made if p["player"] == name]
        rosters.append({
            "player": name, "picks": owned,
            "count": len(owned), "of": league.rounds,
            "waits": draft_rules.picks_until_next_turn(order, league.rounds,
                                                       len(made), name),
        })

    remaining = None
    if (league.status == STATUS_DRAFTING and league.pick_seconds
            and league.clock_started_at):
        elapsed = (_now() - _aware(league.clock_started_at)).total_seconds()
        # Clamped at zero rather than going negative: "overdue" is a client concern, and
        # the server only needs to say whether time is left.
        remaining = max(0, round(league.pick_seconds - elapsed))

    return {
        "league_id": league.id, "name": league.name, "year": league.year,
        "pick_seconds": league.pick_seconds,
        "clock_started_at": (_aware(league.clock_started_at).isoformat()
                             if league.clock_started_at else None),
        "seconds_remaining": remaining,
        "rounds": league.rounds, "status": league.status, "order": order,
        "picks": made, "picks_made": len(made),
        "total_picks": draft_rules.total_picks(len(order), league.rounds),
        "on_the_clock": clock,
        "upcoming": draft_rules.upcoming_picks(order, league.rounds, len(made)),
        "board": draft_rules.board_grid(order, league.rounds),
        "rosters": rosters,
        "drafted_ids": [e.tmdb_id for e in picks],
        # Who took what, so the pool can say "TAKEN - ANDREW - PICK 1" rather than just
        # marking a film unavailable with no explanation.
        "taken": {p["tmdb_id"]: {"player": p["player"], "pick": p["pick"]} for p in made},
    }


def make_pick(session: Session, league_id: int, *, player: str, tmdb_id: int,
              title: str, poster_path: str | None = None) -> dict:
    """Record one pick, or raise ValueError explaining why it is not legal."""
    league = get_league(session, league_id)
    if league.status != STATUS_DRAFTING:
        raise ValueError(f"league is not drafting (status {league.status!r})")

    order = league.draft_order or []
    names = player_names(league)
    by_name = {p.name: p for p in league.players}
    if player not in by_name:
        raise ValueError(f"no player named {player!r} in this league")

    existing = session.scalars(
        select(Entry).where(Entry.league_id == league_id, Entry.tmdb_id.isnot(None))
        .order_by(Entry.pick_number)).all()
    picks = [{"player": names.get(e.player_id), "movie_id": e.tmdb_id} for e in existing]

    slot = draft_rules.validate_pick(order=order, rounds=league.rounds, picks=picks,
                                     player=player, movie_id=tmdb_id)

    # The pool already knows the artwork at the moment of the pick. Storing it here means
    # a freshly drafted league shows posters immediately, rather than only after someone
    # remembers to run enrichment.
    session.add(Entry(league_id=league_id, player_id=by_name[player].id,
                      round=slot["round"], pick_number=slot["pick"],
                      tmdb_id=int(tmdb_id), title=title,
                      poster_path=poster_path or None, sources={}))
    session.flush()

    if len(picks) + 1 >= draft_rules.total_picks(len(order), league.rounds):
        league.status = STATUS_COMPLETE
        league.clock_started_at = None
    else:
        # The next player's clock starts the moment this pick lands, not when their
        # browser happens to render -- otherwise a slow page load buys extra time.
        league.clock_started_at = _now()
    session.flush()
    return draft_state(session, league_id)


# ---------------------------------------------------------------------------
# watches
# ---------------------------------------------------------------------------


def clock_expired(league: League) -> bool:
    """Whether the current pick's time is genuinely up, judged by the server's clock.

    The browser asks for an auto-pick, but never decides one is due -- a wrong clock or a
    tampered client would otherwise take a player's pick away early.
    """
    if league.status != STATUS_DRAFTING or not league.pick_seconds:
        return False
    if league.clock_started_at is None:
        return False
    elapsed = (_now() - _aware(league.clock_started_at)).total_seconds()
    return elapsed >= league.pick_seconds

"""Queries and commands over the relational store.

Everything the API does to league data goes through here, so the endpoints stay thin and
the transaction boundary is always a whole operation rather than a read and a write that
another request can interleave between -- the failure that lost three of four simultaneous
watch toggles under the JSON store.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import draft as draft_rules
from .. import scoring
from .models import (Entry, League, Player, STATUS_COMPLETE, STATUS_DRAFTING,
                     STATUS_SETUP, Watch)


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def list_leagues(session: Session) -> list[dict]:
    leagues = session.scalars(
        select(League).options(selectinload(League.players),
                               selectinload(League.entries))
        .order_by(League.year.desc(), League.id.desc())).all()
    return [{"id": l.id, "name": l.name, "year": l.year, "rounds": l.rounds,
             "status": l.status, "players": [p.name for p in l.players],
             "picks_made": sum(1 for e in l.entries if e.tmdb_id is not None or e.title),
             "total_picks": len(l.players) * l.rounds}
            for l in leagues]


def default_league_id(session: Session) -> int | None:
    """The league the legacy single-league endpoints operate on: the most recent."""
    return session.scalar(select(League.id).order_by(League.year.desc(), League.id.desc()))


def get_league(session: Session, league_id: int) -> League:
    league = session.get(League, league_id)
    if league is None:
        raise LookupError(f"no league with id {league_id}")
    return league


def _entry_dict(entry: Entry, names: dict[int, str]) -> dict:
    return {
        "owner": names.get(entry.player_id),
        "round": entry.round,
        "movie": entry.title,
        "tmdb_id": entry.tmdb_id,
        "pick_number": entry.pick_number,
        "imdb": entry.imdb, "letterboxd": entry.letterboxd,
        "rt_crit": entry.rt_crit, "rt_aud": entry.rt_aud,
        "budget": entry.budget, "gross": entry.gross, "roi": entry.roi,
        "bo_rank": entry.bo_rank, "awards": entry.awards,
        "rating_score": entry.rating_score, "financial_score": entry.financial_score,
        "penalties": entry.penalties, "penalty_notes": entry.penalty_notes,
        "watch_points": entry.watch_points, "total": entry.total,
        "who_watched": [names[w.player_id] for w in entry.watches if w.player_id in names],
        "sources": entry.sources or {},
    }


def player_names(league: League) -> dict[int, str]:
    return {p.id: p.name for p in league.players}


def league_movies(session: Session, league_id: int) -> list[dict]:
    league = get_league(session, league_id)
    names = player_names(league)
    order = league.draft_order or list(names.values())
    entries = session.scalars(
        select(Entry).where(Entry.league_id == league_id)
        .options(selectinload(Entry.watches))).all()
    rows = [_entry_dict(e, names) for e in entries]
    for row in rows:
        row["who_watched"] = [n for n in order if n in row["who_watched"]]
    return sorted(rows, key=lambda r: (r["owner"] or "", r["round"]))


def owner_movies(session: Session, league_id: int, owner: str) -> list[dict]:
    return [m for m in league_movies(session, league_id) if m["owner"] == owner]


def leaderboard(session: Session, league_id: int) -> list[dict]:
    """Standings, with watch points attributed to the watcher rather than the owner."""
    league = get_league(session, league_id)
    names = player_names(league)
    movies = league_movies(session, league_id)

    board = {name: {"owner": name, "total": 0, "rounds_played": 0, "rating_score": 0,
                    "financial_score": 0, "penalties": 0, "watch_points": 0,
                    "own_watch_points": 0, "other_watch_points": 0}
             for name in names.values()}

    for m in movies:
        row = board.get(m["owner"])
        if row is None:
            continue
        row["total"] += m["total"]
        row["rating_score"] += m["rating_score"]
        row["financial_score"] += m["financial_score"]
        row["penalties"] += m["penalties"]
        if m["imdb"] is not None:
            row["rounds_played"] += 1

    for name, row in board.items():
        own = sum(scoring.OWN_WATCH_POINTS for m in movies
                  if m["owner"] == name and name in m["who_watched"])
        other = sum(scoring.OTHER_WATCH_POINTS for m in movies
                    if m["owner"] != name and name in m["who_watched"])
        row["own_watch_points"], row["other_watch_points"] = own, other
        row["watch_points"] = own + other
        # Each entry's own total already carries its owner's own-pick watch points; only
        # the cross-owner points are new at the league level.
        row["total"] += other

    ranked = sorted(board.values(), key=lambda r: r["total"], reverse=True)
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    return ranked


# ---------------------------------------------------------------------------
# league creation and drafting
# ---------------------------------------------------------------------------

def create_league(session: Session, *, name: str, year: int, players: list[str],
                  rounds: int = 6) -> League:
    names = [p.strip() for p in players]
    draft_rules.validate_setup(names, rounds)
    league = League(name=name.strip() or f"League {year}", year=year, rounds=rounds,
                    status=STATUS_SETUP)
    session.add(league)
    session.flush()
    for player_name in names:
        session.add(Player(league_id=league.id, name=player_name))
    session.flush()
    return league


def start_draft(session: Session, league_id: int, *, rng=None) -> League:
    """Randomize the order and open the draft. Only legal from setup."""
    league = get_league(session, league_id)
    if league.status != STATUS_SETUP:
        raise ValueError(f"draft cannot start from status {league.status!r}")
    names = [p.name for p in league.players]
    draft_rules.validate_setup(names, league.rounds)
    league.draft_order = draft_rules.randomize_order(names, rng=rng)
    league.status = STATUS_DRAFTING
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
    clock = draft_rules.on_the_clock(order, league.rounds, len(made))
    return {
        "league_id": league.id, "name": league.name, "year": league.year,
        "rounds": league.rounds, "status": league.status, "order": order,
        "picks": made, "picks_made": len(made),
        "total_picks": draft_rules.total_picks(len(order), league.rounds),
        "on_the_clock": clock,
        "drafted_ids": [e.tmdb_id for e in picks],
    }


def make_pick(session: Session, league_id: int, *, player: str, tmdb_id: int,
              title: str) -> dict:
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

    session.add(Entry(league_id=league_id, player_id=by_name[player].id,
                      round=slot["round"], pick_number=slot["pick"],
                      tmdb_id=int(tmdb_id), title=title, sources={}))
    session.flush()

    if len(picks) + 1 >= draft_rules.total_picks(len(order), league.rounds):
        league.status = STATUS_COMPLETE
    session.flush()
    return draft_state(session, league_id)


# ---------------------------------------------------------------------------
# watches
# ---------------------------------------------------------------------------

def set_watched(session: Session, league_id: int, *, owner: str, round_number: int,
                viewer: str, watched: bool) -> dict:
    league = get_league(session, league_id)
    by_name = {p.name: p for p in league.players}
    if viewer not in by_name:
        raise LookupError(f"no player named {viewer!r}")
    if owner not in by_name:
        raise LookupError(f"no player named {owner!r}")

    entry = session.scalar(
        select(Entry).where(Entry.league_id == league_id,
                            Entry.player_id == by_name[owner].id,
                            Entry.round == round_number))
    if entry is None:
        raise LookupError("movie entry not found")

    viewer_id = by_name[viewer].id
    existing = session.get(Watch, {"entry_id": entry.id, "player_id": viewer_id})
    if watched and existing is None:
        session.add(Watch(entry_id=entry.id, player_id=viewer_id))
    elif not watched and existing is not None:
        session.delete(existing)
    session.flush()

    rescore_entry(session, entry, league)
    session.flush()
    names = player_names(league)
    order = league.draft_order or list(names.values())
    row = _entry_dict(entry, names)
    row["who_watched"] = [n for n in order if n in row["who_watched"]]
    return row


def rescore_entry(session: Session, entry: Entry, league: League) -> Entry:
    """Recompute an entry's derived scores from its current inputs and watches."""
    names = player_names(league)
    payload = {
        "owner": names.get(entry.player_id),
        "who_watched": [names[w.player_id] for w in entry.watches if w.player_id in names],
        **{f: getattr(entry, f) for f in
           ("imdb", "letterboxd", "rt_crit", "rt_aud", "budget", "gross", "roi")},
    }
    scoring.compute_movie_scores(payload)
    for field in ("rating_score", "financial_score", "penalties", "penalty_notes",
                  "watch_points", "total"):
        setattr(entry, field, payload[field])
    return entry

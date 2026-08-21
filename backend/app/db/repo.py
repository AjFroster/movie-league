"""Queries and commands over the relational store.

Everything the API does to league data goes through here, so the endpoints stay thin and
the transaction boundary is always a whole operation rather than a read and a write that
another request can interleave between -- the failure that lost three of four simultaneous
watch toggles under the JSON store.
"""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import draft as draft_rules
from .. import scoring
from ..services.pool import IMAGE_BASE as POSTER_BASE
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
             "total_picks": len(l.players) * l.rounds,
             # Once a draft is done the meaningful progress is no longer picks but how
             # many films have ratings in yet -- the season running rather than the draft.
             "films_scored": sum(1 for e in l.entries if e.imdb is not None),
             "films_total": len(l.entries),
             "frozen_at": l.frozen_at.isoformat() if l.frozen_at else None,
             "settles_on": (l.settles_on or default_settles_on(l.year)).isoformat(),
             # Ready to settle once the date this league chose has passed.
             "season_ended": date.today() > (l.settles_on or default_settles_on(l.year))}
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
        "poster_path": entry.poster_path,
        "poster_url": (f"{POSTER_BASE}{entry.poster_path}" if entry.poster_path else None),
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

DEFAULT_SETTLE_MONTH_DAY = (12, 31)


def default_settles_on(year: int) -> date:
    """A season's books close at the end of its year unless the league says otherwise."""
    return date(year, *DEFAULT_SETTLE_MONTH_DAY)


def create_league(session: Session, *, name: str, year: int, players: list[str],
                  rounds: int = 6, settles_on: date | None = None) -> League:
    names = [p.strip() for p in players]
    draft_rules.validate_setup(names, rounds)
    league = League(name=name.strip() or f"League {year}", year=year, rounds=rounds,
                    status=STATUS_SETUP,
                    settles_on=settles_on or default_settles_on(year))
    session.add(league)
    session.flush()
    for player_name in names:
        session.add(Player(league_id=league.id, name=player_name))
    session.flush()
    return league


def freeze_league(session: Session, league_id: int, *, frozen: bool = True) -> League:
    """Settle a season, or reopen it.

    Reversible on purpose: a freeze is a bookkeeping decision, not a destructive one, and
    a league that froze too early should be able to finish counting.
    """
    from datetime import datetime, timezone
    league = get_league(session, league_id)
    league.frozen_at = datetime.now(tz=timezone.utc) if frozen else None
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


def delete_league(session: Session, league_id: int) -> None:
    """Delete a league and everything under it, via the ON DELETE CASCADE relationships."""
    session.delete(get_league(session, league_id))
    session.flush()


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

    return {
        "league_id": league.id, "name": league.name, "year": league.year,
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


# ---------------------------------------------------------------------------
# enrichment and manual edits
# ---------------------------------------------------------------------------

INPUT_FIELDS = ("imdb", "letterboxd", "rt_crit", "rt_aud", "budget", "gross", "roi",
                "bo_rank", "awards")


def entries_as_documents(session: Session, league_id: int) -> tuple[list[dict], dict]:
    """League rows in the plain-dict shape enrichment.py already understands.

    Returned alongside a {(owner, round): Entry} index so the caller can write results
    back without a second query. Enrichment stays engine-agnostic this way -- it never
    learns what a database is.
    """
    league = get_league(session, league_id)
    names = player_names(league)
    entries = session.scalars(
        select(Entry).where(Entry.league_id == league_id)
        .options(selectinload(Entry.watches))).all()
    documents, index = [], {}
    for entry in entries:
        document = _entry_dict(entry, names)
        documents.append(document)
        index[(document["owner"], document["round"])] = entry
    return documents, index


def apply_documents(session: Session, league_id: int, documents: list[dict],
                    index: dict) -> None:
    """Write enriched documents back onto their rows and rescore them."""
    league = get_league(session, league_id)
    if league.frozen_at is not None:
        # The whole point of freezing: refuse the write rather than silently skip it, so a
        # caller cannot believe it refreshed a season that did not move.
        raise ValueError(f"{league.name!r} is frozen; unfreeze it to refresh its scores")
    for document in documents:
        entry = index.get((document["owner"], document["round"]))
        if entry is None:
            continue
        for field in INPUT_FIELDS:
            setattr(entry, field, document.get(field))
        entry.sources = document.get("sources") or {}
        if document.get("movie"):
            entry.title = document["movie"]
        # Identity and artwork arrive with the enrichment payload. A migrated league has
        # neither, so this is also the backfill path for seasons that predate drafting.
        if document.get("tmdb_id") and entry.tmdb_id is None:
            entry.tmdb_id = document["tmdb_id"]
        if document.get("poster_path"):
            entry.poster_path = document["poster_path"]
        rescore_entry(session, entry, league)
    session.flush()


def update_entry(session: Session, league_id: int, *, owner: str, round_number: int,
                 payload: dict) -> dict:
    """Apply a hand edit, stamping changed fields as manual, then rescore."""
    from .. import provenance

    league = get_league(session, league_id)
    by_name = {p.name: p for p in league.players}
    if owner not in by_name:
        raise LookupError(f"no player named {owner!r}")
    entry = session.scalar(
        select(Entry).where(Entry.league_id == league_id,
                            Entry.player_id == by_name[owner].id,
                            Entry.round == round_number))
    if entry is None:
        raise LookupError("movie entry not found")

    # Provenance is recomputed from the stored row, never taken from the request body: a
    # client that could assert its own sources could pin any field against enrichment.
    document = {"sources": dict(entry.sources or {})}
    changed = [f for f in provenance.ENRICHABLE_FIELDS
               if payload.get(f) != getattr(entry, f)]
    for field in changed:
        provenance.mark_manual(document, field)

    for field in INPUT_FIELDS:
        if field in payload:
            setattr(entry, field, payload[field])
    if payload.get("movie"):
        entry.title = payload["movie"]

    # A human supplying budget and gross by hand implies a manual roi, unless they set it
    # explicitly (in which case it is already stamped above).
    if "roi" not in changed:
        budget, gross = entry.budget, entry.gross
        if isinstance(budget, (int, float)) and isinstance(gross, (int, float)) and budget > 0:
            entry.roi = round(gross / budget, 3)
            provenance.set_source(document, "roi", provenance.MANUAL)

    entry.sources = document["sources"]
    rescore_entry(session, entry, league)
    session.flush()

    names = player_names(league)
    order = league.draft_order or list(names.values())
    row = _entry_dict(entry, names)
    row["who_watched"] = [n for n in order if n in row["who_watched"]]
    return row

"""Moving league data between the JSON file and the database, in both directions.

Import runs once to bring the existing season across. Export runs whenever you want a
readable, diffable, git-committable snapshot -- the database is the source of truth for
writes, but a binary file is a poor thing to be the only copy of a season's history.
"""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Entry, League, Player, Watch, STATUS_COMPLETE

# Fields carried verbatim between an Entry row and a JSON movie object.
SCORE_FIELDS = ("imdb", "letterboxd", "rt_crit", "rt_aud", "budget", "gross", "roi",
                "bo_rank", "awards", "rating_score", "financial_score", "penalties",
                "penalty_notes", "watch_points", "total")


def import_league(session: Session, data: dict, *, name: str, year: int,
                  rounds: int | None = None) -> League:
    """Create a league from a legacy `{owners, movies}` document.

    The imported league is marked complete: its roster already exists, so there is no draft
    left to run. Re-drafting it would mean discarding the season it represents.
    """
    owners = list(data.get("owners") or [])
    movies = list(data.get("movies") or [])
    if not owners:
        raise ValueError("cannot import a league with no owners")

    inferred = max((m.get("round") or 0) for m in movies) if movies else 0
    league = League(name=name, year=year, rounds=rounds or inferred or 6,
                    status=STATUS_COMPLETE, draft_order=owners)
    session.add(league)
    session.flush()

    players = {}
    for owner in owners:
        player = Player(league_id=league.id, name=owner)
        session.add(player)
        players[owner] = player
    session.flush()

    # who_watched holds names; resolve them to rows once, and ignore any name that is not
    # a player in this league rather than inventing one.
    for movie in movies:
        owner = movie.get("owner")
        if owner not in players:
            continue
        entry = Entry(
            league_id=league.id, player_id=players[owner].id,
            round=movie.get("round") or 0,
            tmdb_id=movie.get("tmdb_id"), title=movie.get("movie"),
            sources=movie.get("sources") or {},
            **{f: movie.get(f) for f in SCORE_FIELDS if f not in ("penalty_notes",)},
        )
        entry.penalty_notes = movie.get("penalty_notes") or ""
        session.add(entry)
        session.flush()
        for watcher in movie.get("who_watched") or []:
            if watcher in players:
                session.add(Watch(entry_id=entry.id, player_id=players[watcher].id))
    session.flush()
    return league


def export_league(session: Session, league_id: int) -> dict:
    """Render a league back to the legacy `{owners, movies}` shape."""
    league = session.get(League, league_id)
    if league is None:
        raise ValueError(f"no league with id {league_id}")

    players = {p.id: p.name for p in league.players}
    order = league.draft_order or [p.name for p in league.players]
    # Keep the stored draft order where possible so an exported file reads the way the
    # league is actually arranged, not in whatever order rows came back.
    owners = [n for n in order if n in players.values()]
    owners += [n for n in players.values() if n not in owners]

    entries = session.scalars(
        select(Entry).where(Entry.league_id == league_id)).all()
    movies = []
    for entry in sorted(entries, key=lambda e: (players.get(e.player_id, ""), e.round)):
        watched = [players[w.player_id] for w in entry.watches if w.player_id in players]
        movie = {
            "owner": players.get(entry.player_id),
            "round": entry.round,
            "movie": entry.title,
            **{f: getattr(entry, f) for f in SCORE_FIELDS},
            # League order, not click order, so repeated exports are byte-stable.
            "who_watched": [o for o in owners if o in watched],
            "sources": entry.sources or {},
        }
        # Only emitted when known: a legacy file has no tmdb_id, and inventing the key
        # would make the round trip lossy against exactly the data this migration runs on.
        if entry.tmdb_id is not None:
            movie["tmdb_id"] = entry.tmdb_id
        movies.append(movie)
    return {"owners": owners, "movies": movies}


def export_to_file(session: Session, league_id: int, path: str | Path) -> Path:
    """Write an export to disk atomically, matching the old store's write discipline."""
    path = Path(path)
    payload = export_league(session, league_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)
    return path

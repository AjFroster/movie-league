"""Moving league data between the JSON file and the database, in both directions.

Import runs once to bring the existing season across. Export runs whenever you want a
readable, diffable, git-committable snapshot -- the database is the source of truth for
writes, but a binary file is a poor thing to be the only copy of a season's history.
"""
import json
from datetime import date as dateonly
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import STATUS_COMPLETE, Entry, League, Player, Watch

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


# ---------------------------------------------------------------------------
# Full-fidelity archive format
#
# The legacy shape above cannot express pick numbers, posters, or league settings, so it
# is not a backup. This one carries everything that cannot be recomputed, minus database
# ids (a restore assigns its own) and clock_started_at (live state, not league data).
# ---------------------------------------------------------------------------

ARCHIVE_FORMAT = "movie-league/1"

# Scalars copied straight across in both directions.
LEAGUE_FIELDS = ("name", "year", "rounds", "status", "draft_order", "pick_seconds",
                 "owner_user_id", "visibility")
ENTRY_FIELDS = ("round", "pick_number", "tmdb_id", "title", "poster_path", *SCORE_FIELDS)


def _iso(value):
    """Datetime/date -> ISO string, treating a naive datetime as UTC.

    SQLite has no timezone type and hands back naive datetimes even from a
    `DateTime(timezone=True)` column, so a value written as UTC-aware reads back bare.
    Normalising here is what makes dump -> load -> dump byte-stable across engines;
    without it a round trip through SQLite would drop the offset and fail its own test.
    """
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _parse_dt(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value):
    return dateonly.fromisoformat(value) if value else None


def dump_league(session: Session, league_id: int) -> dict:
    """Everything about one league that cannot be recomputed from what remains."""
    league = session.get(League, league_id)
    if league is None:
        raise ValueError(f"no league with id {league_id}")

    names = {p.id: p.name for p in league.players}
    entries = session.scalars(
        select(Entry).where(Entry.league_id == league_id)).all()

    # Sorted so repeated exports of an unchanged league are byte-identical and therefore
    # diffable in git -- the whole reason for a text format over copying the .db file.
    return {
        **{f: getattr(league, f) for f in LEAGUE_FIELDS},
        "created_at": _iso(league.created_at),
        "frozen_at": _iso(league.frozen_at),
        "settles_on": _iso(league.settles_on),
        # Objects rather than bare names so a slot's claim survives a restore. Losing
        # `user_id` would hand every claimed slot back to the league's creator.
        "players": [{"name": p.name, "user_id": p.user_id} for p in league.players],
        "entries": [
            {
                "owner": names.get(entry.player_id),
                **{f: getattr(entry, f) for f in ENTRY_FIELDS},
                "sources": entry.sources or {},
                "watches": sorted(
                    ({"player": names[w.player_id], "at": _iso(w.at)}
                     for w in entry.watches if w.player_id in names),
                    key=lambda w: w["player"],
                ),
            }
            for entry in sorted(entries, key=lambda e: (names.get(e.player_id, ""), e.round))
        ],
    }


def archive(leagues: list[dict]) -> dict:
    """Wrap dumped leagues in the versioned envelope.

    One league and many leagues share a shape on purpose, so `load_archive` reads a
    single-season export with no special case.
    """
    return {
        "format": ARCHIVE_FORMAT,
        "exported_at": _iso(datetime.now(timezone.utc)),
        "leagues": leagues,
    }


def dump_archive(session: Session) -> dict:
    """Every league in the database, version-stamped."""
    ids = session.scalars(select(League.id).order_by(League.id)).all()
    return archive([dump_league(session, i) for i in ids])


def load_league(session: Session, doc: dict) -> League:
    """Recreate a league from `dump_league` output. Always a new row, never an update."""
    league = League(
        **{f: doc.get(f) for f in LEAGUE_FIELDS},
        created_at=_parse_dt(doc.get("created_at")) or datetime.now(timezone.utc),
        frozen_at=_parse_dt(doc.get("frozen_at")),
        settles_on=_parse_date(doc.get("settles_on")),
    )
    session.add(league)
    session.flush()

    players = {}
    for row in doc.get("players") or []:
        # Bare strings are the shape this format used before slots could be claimed.
        # Accepted so an archive taken then still restores.
        name = row if isinstance(row, str) else row.get("name")
        user_id = None if isinstance(row, str) else row.get("user_id")
        player = Player(league_id=league.id, name=name, user_id=user_id)
        session.add(player)
        players[name] = player
    session.flush()

    for row in doc.get("entries") or []:
        owner = row.get("owner")
        if owner not in players:
            # A dump always names an owner that exists; a hand-edited file might not.
            # Skipping is recoverable, inventing a player is not.
            continue
        entry = Entry(
            league_id=league.id, player_id=players[owner].id,
            sources=row.get("sources") or {},
            **{f: row.get(f) for f in ENTRY_FIELDS if f != "penalty_notes"},
        )
        entry.penalty_notes = row.get("penalty_notes") or ""
        session.add(entry)
        session.flush()
        for watch in row.get("watches") or []:
            if watch.get("player") in players:
                session.add(Watch(entry_id=entry.id,
                                  player_id=players[watch["player"]].id,
                                  at=_parse_dt(watch.get("at")) or datetime.now(timezone.utc)))
    session.flush()
    return league


def load_archive(session: Session, doc: dict) -> list[League]:
    """Recreate every league in an archive. Rejects a format it does not understand."""
    found = doc.get("format")
    if found != ARCHIVE_FORMAT:
        raise ValueError(
            f"unrecognised archive format {found!r}, expected {ARCHIVE_FORMAT!r}. "
            "A legacy {owners, movies} file is read by import_league instead.")
    return [load_league(session, lg) for lg in doc.get("leagues") or []]


def dump_archive_to_file(session: Session, path: str | Path) -> Path:
    """Write a whole-database archive atomically."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dump_archive(session), indent=2))
    tmp.replace(path)
    return path

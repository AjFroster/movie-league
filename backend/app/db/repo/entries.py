"""Entries -- a drafted film on a roster -- and everything scored about them."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ... import provenance, scoring
from ...services.pool import IMAGE_BASE as POSTER_BASE
from ..models import Entry, League, Watch
from .leagues import get_league, player_names


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

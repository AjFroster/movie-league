"""League creation, drafting, and the movie pool.

Kept out of main.py so the legacy single-league endpoints and the multi-league ones do not
grow into each other. Everything here is league-scoped by path.
"""
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import repo
from .db.session import session_scope
from .redaction import ProviderError, redact_secrets
from . import enrichment, scoring
from .services import pool

router = APIRouter(prefix="/api/leagues", tags=["leagues"])


class CreateLeague(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1900, le=2100)
    players: list[str] = Field(min_length=2, max_length=20)
    rounds: int = Field(default=6, ge=1, le=30)
    # Omitted means 31 December of the league's year.
    settles_on: date | None = None
    # Seconds on the clock per pick; 0 turns the timer off.
    pick_seconds: int = Field(default=60, ge=0, le=3600)


class EditLeague(BaseModel):
    """Only what is safe to change after creation.

    Year and player list are deliberately absent: the roster is already drafted against a
    year's film pool, so changing either would invalidate picks rather than edit them. The
    settle date is editable precisely because the roster is what decides it.
    """
    name: str | None = Field(default=None, min_length=1, max_length=120)
    settles_on: date | None = None
    pick_seconds: int | None = Field(default=None, ge=0, le=3600)


class MakePick(BaseModel):
    player: str
    tmdb_id: int
    title: str = Field(min_length=1, max_length=300)
    poster_path: str | None = Field(default=None, max_length=200)


def _mark(film: dict, taken: dict) -> dict:
    """Tag a pool film with who drafted it, so the board can explain its unavailability."""
    claim = taken.get(film["tmdb_id"])
    return {**film, "drafted": claim is not None,
            "taken_by": claim["player"] if claim else None,
            "taken_at_pick": claim["pick"] if claim else None}


@router.get("")
def get_leagues():
    with session_scope() as session:
        return repo.list_leagues(session)


@router.post("", status_code=201)
def post_league(body: CreateLeague):
    with session_scope() as session:
        try:
            league = repo.create_league(session, name=body.name, year=body.year,
                                        players=body.players, rounds=body.rounds,
                                        settles_on=body.settles_on,
                                        pick_seconds=body.pick_seconds)
        except ValueError as e:
            # A rejected setup is the caller's input problem, not a server fault.
            raise HTTPException(status_code=422, detail=redact_secrets(str(e)))
        session.flush()
        return repo.draft_state(session, league.id)


@router.get("/pool-size")
async def get_pool_size(year: int = Query(ge=1900, le=2100),
                        size: int = Query(default=pool.DEFAULT_POOL_SIZE, ge=1,
                                          le=pool.MAX_POOL_SIZE)):
    """How many films a year offers, before any league exists to scope it to.

    The create screen quotes this while you are still choosing a year, so it cannot be
    league-scoped like the other pool routes.
    """
    try:
        films = await pool.fetch_pool(year, size=size)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
    return {"year": year, "count": len(films)}


@router.patch("/{league_id}")
def patch_league(league_id: int, body: EditLeague):
    with session_scope() as session:
        try:
            league = repo.get_league(session, league_id)
            if body.name is not None:
                league = repo.rename_league(session, league_id, name=body.name)
            if body.settles_on is not None:
                league = repo.set_settles_on(session, league_id, on=body.settles_on)
            if body.pick_seconds is not None:
                league = repo.set_pick_seconds(session, league_id,
                                               seconds=body.pick_seconds)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=redact_secrets(str(e)))
        return {"id": league.id, "name": league.name, "year": league.year,
                "status": league.status,
                "settles_on": league.settles_on.isoformat() if league.settles_on else None,
                "pick_seconds": league.pick_seconds}


@router.post("/{league_id}/freeze")
def post_freeze(league_id: int, frozen: bool = Query(default=True)):
    """Settle a season so its scores stop moving, or reopen it.

    The league's rule is that a season ends on 31 December; this is the action that makes
    that stick, since films keep earning and ratings keep drifting long afterwards.
    """
    with session_scope() as session:
        try:
            league = repo.freeze_league(session, league_id, frozen=frozen)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        return {"id": league.id, "name": league.name,
                "frozen_at": league.frozen_at.isoformat() if league.frozen_at else None}


@router.delete("/{league_id}", status_code=204)
def delete_league(league_id: int):
    """Remove a league and everything drafted in it. Cascades to players and entries."""
    with session_scope() as session:
        try:
            repo.delete_league(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
    return None


@router.get("/{league_id}/draft")
def get_draft(league_id: int):
    with session_scope() as session:
        try:
            return repo.draft_state(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))


@router.post("/{league_id}/draft/start")
def post_start_draft(league_id: int):
    """Randomize the order and open the draft. Legal only from setup."""
    with session_scope() as session:
        try:
            repo.start_draft(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))
        return repo.draft_state(session, league_id)


@router.post("/{league_id}/draft/pick")
def post_pick(league_id: int, body: MakePick):
    with session_scope() as session:
        try:
            return repo.make_pick(session, league_id, player=body.player,
                                  tmdb_id=body.tmdb_id, title=body.title,
                                  poster_path=body.poster_path)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        except ValueError as e:
            # 409: the request was well formed but conflicts with the draft's state --
            # someone else took the film, or it is not this player's turn.
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))


@router.get("/{league_id}/leaderboard")
def get_league_leaderboard(league_id: int):
    """Standings for one league.

    The legacy /api/leaderboard serves whichever league is current; once more than one
    exists, reviewing a specific season needs to name it.
    """
    with session_scope() as session:
        try:
            return repo.leaderboard(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))


@router.get("/{league_id}/owners/{owner}")
def get_league_owner(league_id: int, owner: str):
    with session_scope() as session:
        try:
            movies = repo.owner_movies(session, league_id, owner)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        if not movies:
            raise HTTPException(status_code=404, detail=f"No owner named {owner}")
        return {"owner": owner,
                "movies": [{**m, "breakdown": scoring.score_breakdown(m)} for m in movies]}


@router.post("/{league_id}/enrich-all")
async def post_league_enrich(league_id: int, force: bool = False,
                             max_calls: int = enrichment.DEFAULT_MAX_CALLS):
    """Enrich and rescore one league. A freshly drafted season starts unscored."""
    if not 1 <= max_calls <= enrichment.HARD_MAX_CALLS:
        raise HTTPException(
            status_code=422,
            detail=f"max_calls must be between 1 and {enrichment.HARD_MAX_CALLS}")
    with session_scope() as session:
        try:
            documents, index = repo.entries_as_documents(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        try:
            summary = await enrichment.enrich_all({"movies": documents}, force=force,
                                                  max_calls=max_calls)
        except (ProviderError, httpx.HTTPError) as e:
            raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
        try:
            repo.apply_documents(session, league_id, documents, index)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))
        return summary


class WatchUpdate(BaseModel):
    viewer: str
    watched: bool


@router.post("/{league_id}/movies/{owner}/{round_number}/watch")
def post_league_watch(league_id: int, owner: str, round_number: int, body: WatchUpdate):
    """Record a watch against a named league.

    The legacy route acts on whichever league is current, which is wrong the moment you are
    looking at an older season: toggling a 2026 watch would write to the newest league and
    fail with "no player named ...".
    """
    with session_scope() as session:
        try:
            row = repo.set_watched(session, league_id, owner=owner,
                                   round_number=round_number,
                                   viewer=body.viewer, watched=body.watched)
        except LookupError as e:
            detail = redact_secrets(str(e))
            raise HTTPException(status_code=422 if "no player" in detail else 404,
                                detail=detail)
        return {"movie": {**row, "breakdown": scoring.score_breakdown(row)},
                "leaderboard": repo.leaderboard(session, league_id)}


@router.post("/{league_id}/draft/autopick")
async def post_autopick(league_id: int):
    """Take the pick for whoever is on the clock, once their time is genuinely up.

    The browser asks; the server decides. It re-checks the deadline against its own clock,
    so a wrong client clock -- or a tampered one -- cannot take someone's pick early. It
    also chooses the film itself, from the top of the pool, rather than accepting a title
    from the caller.
    """
    with session_scope() as session:
        try:
            league = repo.get_league(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        if not repo.clock_expired(league):
            raise HTTPException(status_code=409,
                                detail="the clock has not run out for this pick")
        state = repo.draft_state(session, league_id)
        clock = state["on_the_clock"]
        if clock is None:
            raise HTTPException(status_code=409, detail="the draft is already complete")
        year, taken = state["year"], set(state["drafted_ids"])

    try:
        films = await pool.fetch_pool(year)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
    choice = next((f for f in films if f["tmdb_id"] not in taken), None)
    if choice is None:
        raise HTTPException(status_code=409, detail="no films left to auto-pick")

    with session_scope() as session:
        # Re-check inside the write transaction: the player may have picked in the moment
        # between the deadline check and here, and their own pick must win over the clock.
        league = repo.get_league(session, league_id)
        if not repo.clock_expired(league):
            raise HTTPException(status_code=409,
                                detail="the pick was made before the clock ran out")
        try:
            result = repo.make_pick(session, league_id, player=clock["player"],
                                    tmdb_id=choice["tmdb_id"], title=choice["title"],
                                    poster_path=choice.get("poster_path"))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))
        return {**result, "autopicked": {"player": clock["player"],
                                         "title": choice["title"]}}


@router.get("/{league_id}/pool")
async def get_pool(league_id: int, size: int = Query(default=pool.DEFAULT_POOL_SIZE,
                                                     ge=1, le=pool.MAX_POOL_SIZE)):
    """The draftable films for this league's year, with drafted ones marked."""
    with session_scope() as session:
        try:
            state = repo.draft_state(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        year, taken = state["year"], state["taken"]

    try:
        films = await pool.fetch_pool(year, size=size)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
    if not films:
        # An empty pool means no TMDB key far more often than it means no films.
        raise HTTPException(
            status_code=503,
            detail="No movie pool available - set TMDB_API_KEY in backend/.env.")
    return {"year": year, "films": [_mark(f, taken) for f in films]}


@router.get("/{league_id}/pool/search")
async def get_pool_search(league_id: int, q: str = Query(min_length=1, max_length=120)):
    """Title search, so a film outside the top N is still draftable."""
    with session_scope() as session:
        try:
            state = repo.draft_state(session, league_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))
        year, taken = state["year"], state["taken"]

    try:
        films = await pool.search(q, year=year)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
    return {"year": year, "films": [_mark(f, taken) for f in films]}

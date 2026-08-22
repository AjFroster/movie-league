"""League creation, drafting, and the movie pool.

Kept out of main.py so the legacy single-league endpoints and the multi-league ones do not
grow into each other. Everything here is league-scoped by path.
"""
from datetime import date
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import enrichment, scoring
from .auth import (
    CurrentUser,
    MaybeUser,
    require_actor,
    require_creator,
    require_member,
    require_viewer,
)
from .db import repo
from .db.session import session_scope
from .errors import http_errors
from .models import Movie
from .redaction import ProviderError, redact_secrets
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
    # Public by default: a league nobody can find is not much of a league, and the people
    # you want reading it mostly do not have accounts. Note this differs from the column
    # default in models.py, which stays `private` -- that one is a safety net for a row
    # created by code that forgot to say, not a product decision.
    visibility: Literal["private", "public"] = "public"


class EditLeague(BaseModel):
    """Only what is safe to change after creation.

    Year and players are absent: the roster is drafted against a year's pool, so changing
    either would invalidate picks rather than edit them.
    """
    name: str | None = Field(default=None, min_length=1, max_length=120)
    settles_on: date | None = None
    pick_seconds: int | None = Field(default=None, ge=0, le=3600)
    visibility: Literal["private", "public"] | None = None


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
def get_leagues(user: str | None = MaybeUser):
    """Leagues this caller may see: their own, plus every public one.

    Open to signed-out visitors, who get the public ones only. Each row carries `mine` so
    the home screen can group them. Private leagues you are not in never appear.
    """
    with session_scope() as session:
        return repo.list_leagues(session, user_id=user, scope="all")


@router.post("", status_code=201)
def post_league(body: CreateLeague, user: str = CurrentUser):
    with session_scope() as session:
        with http_errors(ValueError=422):
            league = repo.create_league(session, name=body.name, year=body.year,
                                        players=body.players, rounds=body.rounds,
                                        settles_on=body.settles_on,
                                        pick_seconds=body.pick_seconds,
                                        visibility=body.visibility,
                                        owner_user_id=user)
        session.flush()
        return repo.draft_state(session, league.id)


@router.get("/pool-size")
async def get_pool_size(year: int = Query(ge=1900, le=2100),
                        size: int = Query(default=pool.DEFAULT_POOL_SIZE, ge=1,
                                          le=pool.MAX_POOL_SIZE)):
    """How many films a year offers. Unscoped because the create screen asks before a
    league exists."""
    try:
        films = await pool.fetch_pool(year, size=size)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
    return {"year": year, "count": len(films)}


@router.patch("/{league_id}")
def patch_league(league_id: int, body: EditLeague, user: str = CurrentUser):
    with session_scope() as session:
        with http_errors(LookupError=404, ValueError=422):
            league = require_creator(session, league_id, user)
            if body.name is not None:
                league = repo.rename_league(session, league_id, name=body.name)
            if body.settles_on is not None:
                league = repo.set_settles_on(session, league_id, on=body.settles_on)
            if body.pick_seconds is not None:
                league = repo.set_pick_seconds(session, league_id,
                                               seconds=body.pick_seconds)
            if body.visibility is not None:
                league = repo.set_visibility(session, league_id,
                                             visibility=body.visibility)
        return {"id": league.id, "name": league.name, "year": league.year,
                "status": league.status,
                "settles_on": league.settles_on.isoformat() if league.settles_on else None,
                "pick_seconds": league.pick_seconds, "visibility": league.visibility}


@router.post("/{league_id}/freeze")
def post_freeze(league_id: int, frozen: bool = Query(default=True),
                user: str = CurrentUser):
    """Settle a season so its scores stop moving, or reopen it.

    Films keep earning and ratings keep drifting long after a season ends.
    """
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_creator(session, league_id, user)
            league = repo.freeze_league(session, league_id, frozen=frozen)
        return {"id": league.id, "name": league.name,
                "frozen_at": league.frozen_at.isoformat() if league.frozen_at else None}


@router.delete("/{league_id}", status_code=204)
def delete_league(league_id: int, user: str = CurrentUser):
    """Remove a league and everything drafted in it. Cascades to players and entries."""
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_creator(session, league_id, user)
            repo.delete_league(session, league_id)
    return None


class ClaimSlot(BaseModel):
    player: str = Field(min_length=1, max_length=80)


@router.post("/{league_id}/claim")
def post_claim(league_id: int, body: ClaimSlot, user: str = CurrentUser):
    """Take a player slot in this league as yourself.

    Open to any signed-in account rather than invite-gated: claiming grants only the
    ability to act as that one player. First-come; only the creator can release a slot.
    """
    with session_scope() as session:
        with http_errors(LookupError=404, ValueError=409):
            player = repo.claim_slot(session, league_id, player_name=body.player,
                                     user_id=user)
        return {"league_id": league_id, "player": player.name, "claimed": True}


@router.delete("/{league_id}/claim/{player_name}", status_code=204)
def delete_claim(league_id: int, player_name: str, user: str = CurrentUser):
    """Release a slot: your own, or -- as the league's creator -- anyone's.

    The override is what makes a wrong claim fixable rather than locked in for the season.
    """
    with session_scope() as session:
        with http_errors(LookupError=404):
            league = repo.get_league(session, league_id)
            player = next((p for p in league.players if p.name == player_name), None)
            if player is None:
                raise HTTPException(status_code=404,
                                    detail=f"No player named {player_name!r}.")
            if player.user_id != user and league.owner_user_id != user:
                raise HTTPException(
                    status_code=403,
                    detail="Only the league's creator can release someone else's slot.")
            repo.release_slot(session, league_id, player_name=player_name)
    return None


@router.get("/{league_id}/draft")
def get_draft(league_id: int, user: str | None = MaybeUser):
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_viewer(session, league_id, user)
            return repo.draft_state(session, league_id)


@router.post("/{league_id}/draft/start")
def post_start_draft(league_id: int, user: str = CurrentUser):
    """Randomize the order and open the draft. Legal only from setup."""
    with session_scope() as session:
        with http_errors(LookupError=404, ValueError=409):
            require_creator(session, league_id, user)
            repo.start_draft(session, league_id)
        return repo.draft_state(session, league_id)


@router.post("/{league_id}/draft/pick")
def post_pick(league_id: int, body: MakePick, user: str = CurrentUser):
    with session_scope() as session:
        with http_errors(LookupError=404, ValueError=409):
            require_actor(session, league_id, user, body.player)
            return repo.make_pick(session, league_id, player=body.player,
                                  tmdb_id=body.tmdb_id, title=body.title,
                                  poster_path=body.poster_path)


@router.get("/{league_id}/leaderboard")
def get_league_leaderboard(league_id: int, user: str | None = MaybeUser):
    """Standings for one league."""
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_viewer(session, league_id, user)
            return repo.leaderboard(session, league_id)


@router.get("/{league_id}/owners/{owner}")
def get_league_owner(league_id: int, owner: str, user: str | None = MaybeUser):
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_viewer(session, league_id, user)
            movies = repo.owner_movies(session, league_id, owner)
        if not movies:
            raise HTTPException(status_code=404, detail=f"No owner named {owner}")
        return {"owner": owner,
                "movies": [{**m, "breakdown": scoring.score_breakdown(m)} for m in movies]}


@router.post("/{league_id}/enrich-all")
async def post_league_enrich(league_id: int, force: bool = False,
                             max_calls: int = enrichment.DEFAULT_MAX_CALLS,
                             user: str = CurrentUser):
    """Enrich and rescore one league. A freshly drafted season starts unscored."""
    if not 1 <= max_calls <= enrichment.HARD_MAX_CALLS:
        raise HTTPException(
            status_code=422,
            detail=f"max_calls must be between 1 and {enrichment.HARD_MAX_CALLS}")
    with session_scope() as session:
        with http_errors(LookupError=404):
            require_creator(session, league_id, user)
            documents, index = repo.entries_as_documents(session, league_id)
        try:
            summary = await enrichment.enrich_all({"movies": documents}, force=force,
                                                  max_calls=max_calls)
        except (ProviderError, httpx.HTTPError) as e:
            raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
        with http_errors(ValueError=409):
            repo.apply_documents(session, league_id, documents, index)
        return summary


class WatchUpdate(BaseModel):
    viewer: str
    watched: bool


@router.post("/{league_id}/movies/{owner}/{round_number}/watch")
def post_league_watch(league_id: int, owner: str, round_number: int, body: WatchUpdate,
                      user: str = CurrentUser):
    """Record a watch. The viewer must be the caller, or an unclaimed slot they own."""
    with session_scope() as session:
        try:
            # The VIEWER, not the owner: a watch is "I saw this", so the caller must be
            # the person being ticked (or the creator, for a slot nobody has claimed).
            require_actor(session, league_id, user, body.viewer)
            row = repo.set_watched(session, league_id, owner=owner,
                                   round_number=round_number,
                                   viewer=body.viewer, watched=body.watched)
        except LookupError as e:
            detail = redact_secrets(str(e))
            raise HTTPException(status_code=422 if "no player" in detail else 404,
                                detail=detail) from None
        return {"movie": {**row, "breakdown": scoring.score_breakdown(row)},
                "leaderboard": repo.leaderboard(session, league_id)}


@router.put("/{league_id}/movies/{owner}/{round_number}")
def put_league_movie(league_id: int, owner: str, round_number: int, movie: Movie,
                     user: str = CurrentUser):
    """Hand-edit an entry. Changed fields are stamped manual so enrichment leaves them."""
    with session_scope() as session:
        require_creator(session, league_id, user)
        with http_errors(LookupError=404):
            return repo.update_entry(session, league_id, owner=owner,
                                     round_number=round_number,
                                     payload=movie.model_dump())


@router.post("/{league_id}/movies/{owner}/{round_number}/enrich")
async def post_league_movie_enrich(league_id: int, owner: str, round_number: int,
                                   force: bool = False, user: str = CurrentUser):
    """Fetch financials and ratings for one entry, then rescore it.

    Hand-entered values are protected unless force=true. Served from cache when fresh.
    """
    with session_scope() as session:
        require_creator(session, league_id, user)
        with http_errors(LookupError=404):
            documents, index = repo.entries_as_documents(session, league_id)
        target = next((d for d in documents
                       if d["owner"] == owner and d["round"] == round_number), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Movie entry not found")

        budget = enrichment.CallBudget(enrichment.MAX_CALLS_PER_ENTRY)
        try:
            report = await enrichment.enrich_entry(target, budget=budget, force=force)
        except (ProviderError, httpx.HTTPError) as e:
            # redact_secrets is mandatory: OMDb and MDBList authenticate by query
            # parameter, and httpx puts the full URL into its error messages.
            raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
        with http_errors(ValueError=409):
            repo.apply_documents(session, league_id, [target], index)
        row = repo.owner_movies(session, league_id, owner)
        movie = next(m for m in row if m["round"] == round_number)
        return {"movie": movie, "report": report, "api_calls_used": budget.used}


@router.post("/{league_id}/draft/autopick")
async def post_autopick(league_id: int, user: str = CurrentUser):
    """Take the pick for whoever is on the clock, once their time is up.

    The browser asks; the server decides. It re-checks the deadline against its own clock
    and chooses the film itself, so a wrong or tampered client clock cannot take a pick
    early or name the film.
    """
    with session_scope() as session:
        with http_errors(LookupError=404):
            league = require_member(session, league_id, user)
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
        raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
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
        with http_errors(ValueError=409):
            result = repo.make_pick(session, league_id, player=clock["player"],
                                    tmdb_id=choice["tmdb_id"], title=choice["title"],
                                    poster_path=choice.get("poster_path"))
        return {**result, "autopicked": {"player": clock["player"],
                                         "title": choice["title"]}}


@router.get("/{league_id}/pool")
async def get_pool(league_id: int, size: int = Query(default=pool.DEFAULT_POOL_SIZE,
                                                     ge=1, le=pool.MAX_POOL_SIZE),
                   user: str = CurrentUser):
    """The draftable films for this league's year, with drafted ones marked."""
    with session_scope() as session:
        with http_errors(LookupError=404):
            state = repo.draft_state(session, league_id)
        year, taken = state["year"], state["taken"]

    try:
        films = await pool.fetch_pool(year, size=size)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
    if not films:
        # An empty pool means no TMDB key far more often than it means no films.
        raise HTTPException(
            status_code=503,
            detail="No movie pool available - set TMDB_API_KEY in backend/.env.")
    return {"year": year, "films": [_mark(f, taken) for f in films]}


@router.get("/{league_id}/pool/search")
async def get_pool_search(league_id: int, q: str = Query(min_length=1, max_length=120),
                          user: str = CurrentUser):
    """Title search, so a film outside the top N is still draftable."""
    with session_scope() as session:
        with http_errors(LookupError=404):
            state = repo.draft_state(session, league_id)
        year, taken = state["year"], state["taken"]

    try:
        films = await pool.search(q, year=year)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e))) from None
    return {"year": year, "films": [_mark(f, taken) for f in films]}

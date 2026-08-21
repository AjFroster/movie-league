import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .storage import load_data, save_data, compute_leaderboard
from .db import repo
from .db.session import init_db, session_scope
from .routes_leagues import router as leagues_router
from .routes_export import router as export_router
from pydantic import BaseModel

from .models import Movie
from . import enrichment, provenance, scoring
from .redaction import ProviderError, redact_secrets

app = FastAPI(title="Fantasy Movie League API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _default_league(session):
    """The league the legacy single-league endpoints act on: the most recent one."""
    league_id = repo.default_league_id(session)
    if league_id is None:
        raise HTTPException(status_code=503, detail="No leagues yet - create one first.")
    return league_id


@app.get("/api/leaderboard")
def get_leaderboard():
    with session_scope() as session:
        return repo.leaderboard(session, _default_league(session))


@app.get("/api/owners/{owner}")
def get_owner(owner: str):
    with session_scope() as session:
        movies = repo.owner_movies(session, _default_league(session), owner)
        if not movies:
            raise HTTPException(status_code=404, detail=f"No owner named {owner}")
        # The per-row breakdown is attached here rather than stored: it is a view of the
        # scoring rules, so it must never go stale against them or be editable via PUT.
        return {"owner": owner,
                "movies": [{**m, "breakdown": scoring.score_breakdown(m)} for m in movies]}


@app.get("/api/rounds/{round_number}")
def get_round(round_number: int):
    with session_scope() as session:
        movies = [m for m in repo.league_movies(session, _default_league(session))
                  if m["round"] == round_number]
    if not movies:
        raise HTTPException(status_code=404, detail=f"No data for round {round_number}")
    return movies


@app.get("/api/movies")
def get_all_movies():
    with session_scope() as session:
        return repo.league_movies(session, _default_league(session))


@app.put("/api/movies/{owner}/{round_number}")
def update_movie(owner: str, round_number: int, movie: Movie):
    """Apply a hand edit. Changed fields are stamped manual so enrichment leaves them be."""
    with session_scope() as session:
        league_id = _default_league(session)
        try:
            return repo.update_entry(session, league_id, owner=owner,
                                     round_number=round_number,
                                     payload=movie.model_dump())
        except LookupError as e:
            raise HTTPException(status_code=404, detail=redact_secrets(str(e)))


class WatchUpdate(BaseModel):
    viewer: str
    watched: bool


@app.post("/api/movies/{owner}/{round_number}/watch")
def set_watched(owner: str, round_number: int, update: WatchUpdate):
    """Record whether `viewer` has watched this film.

    Points follow the watcher, not the owner: +5 for your own pick, +1 for someone else's.
    The whole read-modify-write happens in one transaction, so two people ticking boxes at
    the same moment cannot overwrite each other -- the JSON store lost 3 of 4 here.
    """
    with session_scope() as session:
        league_id = _default_league(session)
        try:
            row = repo.set_watched(session, league_id, owner=owner,
                                   round_number=round_number,
                                   viewer=update.viewer, watched=update.watched)
        except LookupError as e:
            detail = redact_secrets(str(e))
            code = 422 if "no player" in detail else 404
            raise HTTPException(status_code=code, detail=detail)
        return {"movie": {**row, "breakdown": scoring.score_breakdown(row)},
                "leaderboard": repo.leaderboard(session, league_id)}


@app.post("/api/movies/{owner}/{round_number}/enrich")
async def enrich_movie(owner: str, round_number: int, force: bool = False):
    """Fill budget/gross from TMDB and the ratings from MDBList for one entry.

    Hand-entered values are protected; pass ?force=true to overwrite them. Results are
    served from the cache when fresh, so a repeat call costs no API calls. Scores are
    recomputed from the new values.
    """
    with session_scope() as session:
        league_id = _default_league(session)
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
            raise HTTPException(status_code=502, detail=redact_secrets(str(e)))

        try:
            repo.apply_documents(session, league_id, [target], index)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))
        row = repo.owner_movies(session, league_id, owner)
        movie = next(m for m in row if m["round"] == round_number)
        return {"movie": movie, "report": report, "api_calls_used": budget.used}


@app.post("/api/enrich-all")
async def enrich_all_movies(force: bool = False,
                            max_calls: int = enrichment.DEFAULT_MAX_CALLS):
    """Enrich every entry in one paced, capped run, then rescore the league."""
    if not 1 <= max_calls <= enrichment.HARD_MAX_CALLS:
        raise HTTPException(
            status_code=422,
            detail=f"max_calls must be between 1 and {enrichment.HARD_MAX_CALLS}")

    with session_scope() as session:
        league_id = _default_league(session)
        documents, index = repo.entries_as_documents(session, league_id)
        payload = {"movies": documents}
        try:
            summary = await enrichment.enrich_all(payload, force=force,
                                                  max_calls=max_calls)
        except (ProviderError, httpx.HTTPError) as e:
            raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
        try:
            repo.apply_documents(session, league_id, documents, index)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=redact_secrets(str(e)))
        return summary


app.include_router(leagues_router)
app.include_router(export_router)


@app.on_event("startup")
def _startup():
    """Create tables on first run. Alembic owns schema changes; this is bootstrap only."""
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}

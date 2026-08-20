import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .storage import load_data, save_data, compute_leaderboard
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


@app.get("/api/leaderboard")
def get_leaderboard():
    data = load_data()
    return compute_leaderboard(data)


@app.get("/api/owners/{owner}")
def get_owner(owner: str):
    data = load_data()
    if owner not in data["owners"]:
        raise HTTPException(status_code=404, detail=f"No owner named {owner}")
    movies = [m for m in data["movies"] if m["owner"] == owner]
    return {"owner": owner, "movies": sorted(movies, key=lambda m: m["round"])}


@app.get("/api/rounds/{round_number}")
def get_round(round_number: int):
    data = load_data()
    movies = [m for m in data["movies"] if m["round"] == round_number]
    if not movies:
        raise HTTPException(status_code=404, detail=f"No data for round {round_number}")
    return movies


@app.get("/api/movies")
def get_all_movies():
    return load_data()["movies"]


@app.put("/api/movies/{owner}/{round_number}")
def update_movie(owner: str, round_number: int, movie: Movie):
    data = load_data()
    for i, m in enumerate(data["movies"]):
        if m["owner"] == owner and m["round"] == round_number:
            entry = movie.model_dump()
            entry["owner"] = owner
            entry["round"] = round_number

            # Provenance is recomputed from the stored row, never taken from the request
            # body: a client that could assert its own `sources` could pin any field
            # against enrichment, or expose a hand-entered one to being overwritten.
            entry["sources"] = dict(m.get("sources") or {})
            changed = [f for f in provenance.ENRICHABLE_FIELDS if entry.get(f) != m.get(f)]
            for field in changed:
                provenance.mark_manual(entry, field)

            # A human supplying budget and gross by hand implies a manual roi, unless they
            # set roi explicitly (in which case it is already stamped above).
            if "roi" not in changed:
                b, g = entry.get("budget"), entry.get("gross")
                if isinstance(b, (int, float)) and isinstance(g, (int, float)) and b > 0:
                    entry["roi"] = round(g / b, 3)
                    provenance.set_source(entry, "roi", provenance.MANUAL)

            # A hand-edited rating or financial changes the derived scores too. Scores are
            # always recomputed rather than accepted from the request body: they are a
            # cached calculation, not data a client gets to assert.
            scoring.compute_movie_scores(entry)

            data["movies"][i] = entry
            try:
                save_data(data)
            except Exception:
                raise HTTPException(status_code=507, detail="Failed to persist update")
            return data["movies"][i]
    raise HTTPException(status_code=404, detail="Movie entry not found")


@app.post("/api/movies/{owner}/{round_number}/enrich")
async def enrich_movie(owner: str, round_number: int, force: bool = False):
    """Fill budget/gross from TMDB and imdb/rt_crit from OMDb for one entry.

    Hand-entered values are protected; pass ?force=true to overwrite them. Results are
    served from backend/data/api_cache.json when fresh, so a repeat call costs no API
    calls. Scores ARE recomputed from the new values (see scoring.py), so the leaderboard
    reflects the fetched data.
    """
    data = load_data()
    for i, m in enumerate(data["movies"]):
        if m["owner"] == owner and m["round"] == round_number:
            budget = enrichment.CallBudget(enrichment.MAX_CALLS_PER_ENTRY)
            try:
                report = await enrichment.enrich_entry(m, budget=budget, force=force)
            except (ProviderError, httpx.HTTPError) as e:
                # redact_secrets is mandatory here: OMDb has no header auth, so its key is
                # a query parameter, and httpx puts the full URL into its error messages.
                # Passing the raw exception text through unredacted would leak OMDB_API_KEY
                # into this 502 body.
                raise HTTPException(status_code=502, detail=redact_secrets(str(e)))
            # Fresh ratings/financials mean the derived scores are now stale.
            scoring.compute_movie_scores(m)
            data["movies"][i] = m
            try:
                save_data(data)
            except Exception:
                raise HTTPException(status_code=507, detail="Failed to persist update")
            return {"movie": m, "report": report, "api_calls_used": budget.used}
    raise HTTPException(status_code=404, detail="Movie entry not found")


@app.post("/api/enrich-all")
async def enrich_all_movies(force: bool = False,
                            max_calls: int = enrichment.DEFAULT_MAX_CALLS):
    """Manually-triggered bulk enrichment across every movie row.

    There is no scheduler and no refresh-on-page-load by design -- this runs only when
    called. Rows are processed sequentially with a delay, and `max_calls` hard-caps total
    outbound requests so an accidental loop cannot exhaust OMDb's 1,000/day free tier.
    Hand-entered values are protected unless ?force=true.
    """
    if not 1 <= max_calls <= enrichment.HARD_MAX_CALLS:
        raise HTTPException(
            status_code=422,
            detail=f"max_calls must be between 1 and {enrichment.HARD_MAX_CALLS}")

    data = load_data()
    try:
        summary = await enrichment.enrich_all(data, force=force, max_calls=max_calls)
    except (ProviderError, httpx.HTTPError) as e:
        raise HTTPException(status_code=502, detail=redact_secrets(str(e)))

    # Rescore every row, not just the enriched ones: watch_points depends on who_watched,
    # which enrichment never touches, so a row can need rescoring without being fetched.
    for m in data["movies"]:
        scoring.compute_movie_scores(m)

    try:
        save_data(data)
    except Exception:
        raise HTTPException(status_code=507, detail="Failed to persist enrichment results")
    return summary


@app.get("/api/health")
def health():
    return {"status": "ok"}

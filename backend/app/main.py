import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .storage import load_data, save_data, compute_leaderboard
from .models import Movie
from .services import tmdb

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


def _compute_roi(entry: dict) -> dict:
    """Set roi = gross / budget in-place when both are known."""
    b, g = entry.get("budget"), entry.get("gross")
    if b and g and b > 0:
        entry["roi"] = round(g / b, 3)
    return entry


@app.put("/api/movies/{owner}/{round_number}")
def update_movie(owner: str, round_number: int, movie: Movie):
    data = load_data()
    for i, m in enumerate(data["movies"]):
        if m["owner"] == owner and m["round"] == round_number:
            entry = movie.model_dump()
            entry["owner"] = owner
            entry["round"] = round_number
            _compute_roi(entry)
            data["movies"][i] = entry
            try:
                save_data(data)
            except Exception:
                raise HTTPException(status_code=507, detail="Failed to persist update")
            return data["movies"][i]
    raise HTTPException(status_code=404, detail="Movie entry not found")


@app.post("/api/movies/{owner}/{round_number}/enrich")
async def enrich_movie(owner: str, round_number: int):
    """Auto-fill budget/gross from TMDB for a movie entry. RT/Letterboxd stay manual."""
    data = load_data()
    for i, m in enumerate(data["movies"]):
        if m["owner"] == owner and m["round"] == round_number:
            try:
                financials = await tmdb.fetch_movie_financials(m["movie"])
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=str(e))
            if financials:
                if financials.get("budget_millions") is not None:
                    m["budget"] = financials["budget_millions"]
                if financials.get("gross_millions") is not None:
                    m["gross"] = financials["gross_millions"]
                if financials.get("vote_average") is not None:
                    m["imdb"] = financials["vote_average"]
                _compute_roi(m)
                data["movies"][i] = m
                save_data(data)
            return {"movie": m, "tmdb_match": financials is not None}
    raise HTTPException(status_code=404, detail="Movie entry not found")


@app.get("/api/health")
def health():
    return {"status": "ok"}

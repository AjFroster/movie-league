import json
import os
from pathlib import Path
from threading import Lock

from fastapi import HTTPException

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "league_data.json"
_lock = Lock()


def load_data() -> dict:
    with _lock:
        try:
            with open(DATA_PATH, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=503, detail=f"Data store unavailable: {e}")


def save_data(data: dict) -> None:
    with _lock:
        tmp = DATA_PATH.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, DATA_PATH)


def compute_leaderboard(data: dict) -> list[dict]:
    """Aggregate totals per owner across all rounds."""
    board = {owner: {"owner": owner, "total": 0, "rounds_played": 0,
                      "rating_score": 0, "financial_score": 0,
                      "penalties": 0, "watch_points": 0}
             for owner in data["owners"]}

    for m in data["movies"]:
        row = board.get(m["owner"])
        if row is None:
            continue
        row["total"] += m["total"]
        row["rating_score"] += m["rating_score"]
        row["financial_score"] += m["financial_score"]
        row["penalties"] += m["penalties"]
        row["watch_points"] += m["watch_points"]
        if m["imdb"] is not None:
            row["rounds_played"] += 1

    ranked = sorted(board.values(), key=lambda r: r["total"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked

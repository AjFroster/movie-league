import json
import os
from pathlib import Path
from threading import Lock

from fastapi import HTTPException

from . import scoring

_DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "league_data.json"

# Overridable so a preview or staging instance can be pointed at a copy of the league file
# rather than the live one -- running the app against real data just to look at it is how
# real data gets modified by accident.
DATA_PATH = Path(os.environ.get("LEAGUE_DATA_PATH") or _DEFAULT_DATA_PATH)
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
    """Aggregate totals per owner across all rounds.

    Watch points are the one component that does not come from the owner's own rows: a
    point earned for watching someone else's pick belongs to the watcher, so it is
    attributed league-wide rather than summed per row.
    """
    board = {owner: {"owner": owner, "total": 0, "rounds_played": 0,
                      "rating_score": 0, "financial_score": 0,
                      "penalties": 0, "watch_points": 0, "own_watch_points": 0,
                      "other_watch_points": 0}
             for owner in data["owners"]}

    for m in data["movies"]:
        row = board.get(m["owner"])
        if row is None:
            continue
        row["total"] += m["total"]
        row["rating_score"] += m["rating_score"]
        row["financial_score"] += m["financial_score"]
        row["penalties"] += m["penalties"]
        # m["watch_points"] is deliberately NOT summed here: it is the owner's own-pick
        # component, and adding it would double-count against the league-wide pass below.
        if m["imdb"] is not None:
            row["rounds_played"] += 1

    # Watch points, attributed to the watcher across every film in the league.
    for owner, row in board.items():
        own = sum(scoring.OWN_WATCH_POINTS for m in data["movies"]
                  if m.get("owner") == owner and owner in (m.get("who_watched") or []))
        other = sum(scoring.OTHER_WATCH_POINTS for m in data["movies"]
                    if m.get("owner") != owner and owner in (m.get("who_watched") or []))
        row["own_watch_points"] = own
        row["other_watch_points"] = other
        row["watch_points"] = own + other
        # Each row's `total` already includes its own-pick watch points, so only the
        # cross-owner points are new information at the league level.
        row["total"] += other

    ranked = sorted(board.values(), key=lambda r: r["total"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked

"""Shared fixtures.

Hard rule for this suite: no test may make a network call or require a real API key.
The autouse fixture below enforces that -- if a test starts passing only because a
developer has TMDB_API_KEY exported in their shell, that is a broken test, and
stripping the env vars makes it fail loudly instead.
"""
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import storage  # noqa: E402
from app.services import cache  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """Every test runs with zero provider credentials unless it sets its own."""
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)


@pytest.fixture
def sample_movie():
    """One movie row in the exact shape stored in backend/data/league_data.json."""
    return {
        "owner": "Liam", "round": 2, "movie": "Super Girl",
        "imdb": None, "letterboxd": None, "rt_crit": None, "rt_aud": None,
        "budget": None, "gross": None, "roi": None, "bo_rank": None, "awards": None,
        "who_watched": [], "rating_score": 0, "financial_score": 0,
        "penalties": 0, "penalty_notes": "", "watch_points": 0, "total": 0,
        "sources": {},
    }


@pytest.fixture
def tmp_league(tmp_path, monkeypatch, sample_movie):
    """Redirect storage.DATA_PATH at a throwaway file so no test can touch real league data."""
    path = tmp_path / "league_data.json"
    path.write_text(json.dumps({"owners": ["Liam"], "movies": [dict(sample_movie)]}, indent=2))
    monkeypatch.setattr(storage, "DATA_PATH", path)
    return path


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Redirect the API cache at a throwaway file so tests never share cache state."""
    path = tmp_path / "api_cache.json"
    monkeypatch.setattr(cache, "CACHE_PATH", path)
    return path

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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    monkeypatch.delenv("MDBLIST_API_KEY", raising=False)


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
def tmp_league(tmp_path, monkeypatch, sample_movie, never_touch_the_real_database):
    """Throwaway league data in BOTH backends.

    The endpoints read the database now, but this fixture predates that and only
    redirected the JSON file -- which is how a test run once rewrote the real season. It
    seeds both so the fixture's promise holds whichever layer a test exercises.
    """
    document = {"owners": ["Liam"], "movies": [dict(sample_movie)]}
    path = tmp_path / "league_data.json"
    path.write_text(json.dumps(document, indent=2))
    monkeypatch.setattr(storage, "DATA_PATH", path)

    from app.auth import LOCAL_USER_ID
    from app.db.porting import import_league
    with never_touch_the_real_database() as session:
        league = import_league(session, document, name="Test League", year=2026)
        # Owned by the local identity, which is who an unauthenticated test request is.
        # Without this every mutating endpoint correctly answers 403 and the fixture is
        # useless -- which is exactly what happened when accounts landed.
        league.owner_user_id = LOCAL_USER_ID
        session.commit()
    return path


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Redirect the API cache at a throwaway file so tests never share cache state."""
    path = tmp_path / "api_cache.json"
    monkeypatch.setattr(cache, "CACHE_PATH", path)
    return path


@pytest.fixture(autouse=True)
def never_touch_the_real_database(tmp_path, monkeypatch):
    """Point every test at a throwaway database.

    Not a convenience: a test run once wrote through to the real league.db and rewrote the
    season, because the endpoints had moved to the database while the fixtures still
    redirected only the JSON file. Redirecting the session factory here means a test cannot
    reach the real file even if it forgets to ask.
    """
    from app.db import session as db_session
    from app.db.models import Base

    # In memory with StaticPool: every test gets a fresh, isolated database, and building
    # one costs no disk I/O. StaticPool is required -- without it each connection would
    # get its own blank :memory: database and the schema would vanish between queries.
    engine = create_engine("sqlite://", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(db_session, "_engine", engine)
    monkeypatch.setattr(db_session, "_SessionLocal", maker)
    monkeypatch.setattr(db_session, "DEFAULT_DB_PATH", tmp_path / "autouse.db")
    return maker

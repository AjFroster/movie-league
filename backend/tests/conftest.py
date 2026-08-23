"""Shared fixtures.

Hard rule for this suite: no test may make a network call or require a real API key.
The autouse fixture below enforces that -- if a test starts passing only because a
developer has TMDB_API_KEY exported in their shell, that is a broken test, and
stripping the env vars makes it fail loudly instead.
"""
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import cache  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch):
    """Every test runs with zero provider credentials unless it sets its own.

    CLERK_* belongs here for the same reason as the rest: `main.py` calls `load_dotenv()`
    at import, so the moment a real CLERK_ISSUER landed in backend/.env every test request
    started 401ing against a live Clerk instance. A test's identity must come from the
    test, never from whatever the developer happens to have configured.
    """
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    monkeypatch.delenv("MDBLIST_API_KEY", raising=False)
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)


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
def tmp_league(sample_movie, never_touch_the_real_database):
    """A throwaway league owned by the local identity. Returns its id."""
    from app.auth import LOCAL_USER_ID
    from app.db.porting import import_league
    with never_touch_the_real_database() as session:
        league = import_league(session, {"owners": ["Liam"], "movies": [dict(sample_movie)]},
                               name="Test League", year=2026)
        # Without an owner every mutating endpoint correctly answers 403.
        league.owner_user_id = LOCAL_USER_ID
        session.commit()
        return league.id


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Redirect the API cache at a throwaway file so tests never share cache state."""
    path = tmp_path / "api_cache.json"
    monkeypatch.setattr(cache, "CACHE_PATH", path)
    return path


# SQLite by default: instant, and needs nothing installed. TEST_DATABASE_URL points the
# same suite at a real Postgres, which is what the `backend-postgres` CI job does.
#
# Deliberately not DATABASE_URL. That one is read by `auth.verify_startup_configuration`,
# which refuses to run in local-identity mode against a non-SQLite database -- a guard a
# test run has no business switching off. Separate variable, guard untouched.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def _shared_engine():
    """One Postgres engine and schema for the whole run, or None when running on SQLite.

    Session-scoped because building a Postgres schema per test would cost more than the
    tests do. SQLite pays nothing for a fresh database, so it keeps making one per test.
    """
    if not TEST_DATABASE_URL:
        yield None
        return

    from app.db.models import Base
    from app.db.session import create_db_engine

    engine = create_db_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)     # a run that crashed last time leaves tables behind
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def _empty_database(_shared_engine):
    """An engine on an empty schema, whichever backend is in play.

    RESTART IDENTITY is not cosmetic. On SQLite every test gets a brand new :memory:
    database, so the first league is always id 1 and a fair number of tests say so out
    loud; resetting the sequences is what keeps those tests honest on Postgres.
    """
    from app.db.models import Base
    from app.db.session import create_db_engine

    if _shared_engine is None:
        # create_db_engine rather than a bare create_engine, so the test database gets the
        # same pragmas production does -- foreign_keys=ON above all, without which
        # ON DELETE CASCADE silently does nothing and a test proves the wrong thing.
        # StaticPool is required: without it each connection gets its own blank :memory:
        # database and the schema vanishes between queries.
        engine = create_db_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        return engine

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with _shared_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return _shared_engine


@pytest.fixture(autouse=True)
def never_touch_the_real_database(tmp_path, monkeypatch, _empty_database):
    """Point every test at a throwaway database.

    Not a convenience: a test run once wrote through to the real league.db and rewrote the
    season, because the endpoints had moved to the database while the fixtures still
    redirected only the JSON file. Redirecting the session factory here means a test cannot
    reach the real file even if it forgets to ask.
    """
    from app.db import session as db_session

    maker = sessionmaker(bind=_empty_database, expire_on_commit=False, future=True)
    monkeypatch.setattr(db_session, "_engine", _empty_database)
    monkeypatch.setattr(db_session, "_SessionLocal", maker)
    monkeypatch.setattr(db_session, "DEFAULT_DB_PATH", tmp_path / "autouse.db")
    return maker


@pytest.fixture
def session(never_touch_the_real_database):
    """A throwaway database session.

    Was defined three times, near-identically, in test_archive / test_db_porting /
    test_repo_draft. One copy, so a change to how tests get a session happens once -- and
    it is the same database the endpoints see, rather than a second one alongside it.
    """
    with never_touch_the_real_database() as s:
        yield s

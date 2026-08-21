"""Engine and session setup.

The database URL is the only thing that changes between running on a laptop and running on
a host: `sqlite:///.../league.db` here, `postgresql+psycopg://...` on RDS. Everything above
this module is engine-agnostic.
"""
import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "league.db"


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_DB_PATH}"


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_db_engine(url: str | None = None):
    url = url or database_url()
    # check_same_thread is a SQLite-only guard against sharing a connection between
    # threads; FastAPI's threadpool does exactly that, and SQLAlchemy's pool already
    # serialises access.
    kwargs = {"connect_args": {"check_same_thread": False}} if _is_sqlite(url) else {}
    engine = create_engine(url, future=True, **kwargs)

    if _is_sqlite(url):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            # WAL: readers never block the writer, which is what makes a draft board
            # responsive while someone is picking.
            cursor.execute("PRAGMA journal_mode=WAL")
            # Wait rather than fail instantly when another write is in flight.
            cursor.execute("PRAGMA busy_timeout=5000")
            # SQLite does NOT enforce foreign keys unless asked, per connection. Without
            # this, ON DELETE CASCADE silently does nothing and deleting a league leaves
            # orphaned entries behind.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def init_db() -> None:
    """Create tables if absent. Alembic owns schema *changes*; this is first-run setup."""
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Session:
    """A transaction. Commits on success, rolls back on any exception.

    Every write goes through one of these, so a request that fails halfway cannot leave
    half its changes behind -- the failure mode the JSON store had no answer for.
    """
    get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

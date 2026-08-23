"""Who owns the schema, and where.

Named apart from test_migration.py on purpose: that file tests the one-shot provenance
backfill script, which is a different sense of the word entirely.
"""


def test_init_db_creates_nothing_on_a_hosted_database(monkeypatch):
    """Alembic owns the schema anywhere but SQLite, and this is why.

    create_all against a fresh Postgres builds every table with no row in
    alembic_version, so the next `alembic upgrade head` tries to create tables that
    already exist and fails -- with the deployment already half-live.
    """
    from app.db import session as db_session

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@example.invalid/league")
    created = []
    monkeypatch.setattr(db_session.Base.metadata, "create_all",
                        lambda *a, **k: created.append(True))

    db_session.init_db()

    assert created == [], "init_db touched the schema of a hosted database"


def test_init_db_still_sets_up_a_fresh_sqlite_file(monkeypatch):
    """The convenience it exists for has to survive the guard: a clone with no database
    should still run without anyone being told to migrate first."""
    from app.db import session as db_session

    monkeypatch.delenv("DATABASE_URL", raising=False)
    created = []
    monkeypatch.setattr(db_session.Base.metadata, "create_all",
                        lambda *a, **k: created.append(True))

    db_session.init_db()

    assert created == [True]

"""Assert that `alembic upgrade head` builds exactly what the models describe.

The test suite creates its schema with `Base.metadata.create_all`, which proves the models
are valid and says nothing about the migrations. Production has no `create_all`: a hosted
database gets its schema from Alembic and nothing else. When the two disagree the suite
stays green and the deployment is quietly wrong -- a column that exists on a laptop and
not on the server.

    DATABASE_URL=postgresql+psycopg://... python -m scripts.check_schema_drift

Run it against a database that has just had `alembic upgrade head` applied.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import create_db_engine, database_url  # noqa: E402


def main() -> int:
    url = database_url()
    print(f"comparing {url.rsplit('@', 1)[-1]} against the models")

    engine = create_db_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    if not diff:
        print("no drift: the migrations build exactly what the models describe")
        return 0

    print(f"\n{len(diff)} difference(s) between the migrated schema and the models:\n")
    for item in diff:
        print(f"  {item}")
    print("\nEither a migration is missing, or one does not match the model it belongs to.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

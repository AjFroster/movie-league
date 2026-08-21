"""Restore a league archive into a database. The other half of GET /api/export.

Deliberately a script and not an endpoint. A restore replaces league history, and with no
authentication in front of the API an endpoint that could do this would be the worst hole
in the app. Running it requires shell access to the machine holding the data, which is the
right bar for an operation this destructive.

This is also the SQLite -> Postgres migration:

    curl -sO http://localhost:8000/api/export                 # or use the UI button
    DATABASE_URL=postgresql+psycopg://... python -m alembic upgrade head
    DATABASE_URL=postgresql+psycopg://... python -m scripts.restore backup.json

    python -m scripts.restore backup.json [--replace] [--dry-run]

Without --replace the archive is added alongside whatever is already there, which will
duplicate leagues if they already exist. --replace deletes every existing league first.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.models import League
from app.db.porting import ARCHIVE_FORMAT, dump_archive, load_archive
from app.db.session import database_url, init_db, session_scope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--replace", action="store_true",
                        help="delete every existing league first")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen, write nothing")
    args = parser.parse_args()

    if not args.archive.exists():
        print(f"no such file: {args.archive}", file=sys.stderr)
        return 1

    doc = json.loads(args.archive.read_text())
    if doc.get("format") != ARCHIVE_FORMAT:
        print(f"unrecognised format {doc.get('format')!r}, expected {ARCHIVE_FORMAT!r}",
              file=sys.stderr)
        return 1

    incoming = doc.get("leagues") or []
    print(f"archive : {args.archive}  ({doc.get('exported_at')})")
    for lg in incoming:
        picks = sum(1 for e in lg["entries"] if e.get("pick_number") is not None)
        print(f"          {lg['name']!r} {lg['year']}  "
              f"{len(lg['players'])} players, {len(lg['entries'])} entries, {picks} picks")
    print(f"target  : {database_url()}")

    init_db()
    with session_scope() as session:
        existing = session.scalars(select(League)).all()
        print(f"          {len(existing)} league(s) already present")

        if existing and not args.replace:
            print("\nRefusing to restore into a non-empty database without --replace: the "
                  "archive would be added alongside what is there, duplicating leagues.",
                  file=sys.stderr)
            return 1

        if args.dry_run:
            verb = "replace" if args.replace else "add"
            print(f"\ndry run: would {verb} -> {len(incoming)} league(s). Nothing written.")
            return 0

        if args.replace and existing:
            # Safety net for the one command in this project that destroys data: a
            # snapshot of what is about to be deleted, written before the delete.
            fallback = args.archive.with_name(f"{args.archive.stem}.replaced.json")
            fallback.write_text(json.dumps(dump_archive(session), indent=2))
            print(f"          saved existing data to {fallback}")
            for league in existing:
                session.delete(league)      # cascades to players, entries, watches
            session.flush()

        restored = load_archive(session, doc)

    print(f"\nrestored {len(restored)} league(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

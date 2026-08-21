"""One-time migration: league_data.json -> league.db.

Idempotent by name+year, so re-running it will not create a second copy of the season.
Verifies the round trip before committing: if the exported league does not match what went
in, nothing is written. The season this migrates cannot be regenerated from any API.

    python -m scripts.migrate_to_db [--name NAME] [--year YEAR] [--dry-run]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.models import League
from app.db.porting import export_league, import_league
from app.db.session import init_db, session_scope

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "league_data.json"


def _mismatches(original: dict, exported: dict) -> list[str]:
    """Differences that would mean data loss. Watcher order is normalised by design."""
    problems = []
    if set(original["owners"]) != set(exported["owners"]):
        problems.append("owner list differs")
    if len(original["movies"]) != len(exported["movies"]):
        problems.append("movie count differs")

    def key(m):
        return (m.get("owner"), m.get("round"))

    for before, after in zip(sorted(original["movies"], key=key),
                             sorted(exported["movies"], key=key)):
        before, after = dict(before), dict(after)
        if set(before.pop("who_watched", []) or []) != set(after.pop("who_watched", []) or []):
            problems.append(f"watchers differ: {key(before)}")
        after.pop("tmdb_id", None)          # added by the schema, absent from legacy files
        for field, value in before.items():
            if after.get(field) != value:
                problems.append(f"{key(before)} {field}: {value!r} -> {after.get(field)!r}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Movie League 2026")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    original = json.loads(DATA_PATH.read_text())
    print(f"source : {DATA_PATH}")
    print(f"         {len(original['owners'])} players, {len(original['movies'])} entries")

    init_db()
    with session_scope() as session:
        existing = session.scalar(
            select(League).where(League.name == args.name, League.year == args.year))
        if existing is not None:
            print(f"already migrated: league id={existing.id} {existing.name!r} "
                  f"({existing.year}) -- nothing to do")
            return 0

        league = import_league(session, original, name=args.name, year=args.year)
        session.flush()
        problems = _mismatches(original, export_league(session, league.id))
        if problems:
            print("\nREFUSING TO MIGRATE -- round trip lost data:")
            for p in problems[:20]:
                print(f"   {p}")
            raise SystemExit(1)     # session_scope rolls back

        print(f"\nround trip verified: {len(original['movies'])} entries preserved")
        if args.dry_run:
            print("dry run -- rolling back")
            raise SystemExit(0)     # rollback via the exception path
        print(f"migrated: league id={league.id} {league.name!r} ({league.year}), "
              f"rounds={league.rounds}, status={league.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

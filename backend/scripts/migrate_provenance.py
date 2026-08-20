"""One-shot backfill of per-field provenance onto backend/data/league_data.json.

Classification is derived from the repo's actual write history, not from guesswork:

  main.py::enrich_movie has always written exactly imdb, budget, gross, and roi (via
  _compute_roi). Those four therefore have AMBIGUOUS origin -- a value there may be a
  human's spreadsheet number or a TMDB value from a past /enrich run. In particular the
  `imdb` field may hold TMDB's vote_average, which is not the IMDb rating. They are marked
  UNKNOWN (writable, correctable) with the pre-migration number kept in `legacy_value`.

  letterboxd, rt_crit, rt_aud, bo_rank, and awards have never had any automated writer in
  this codebase. Only a human could have set them, so they are marked MANUAL (protected).

Null fields get no sources entry at all -- there is nothing to protect.

Usage:
    backend/.venv/bin/python backend/scripts/migrate_provenance.py --dry-run
    backend/.venv/bin/python backend/scripts/migrate_provenance.py
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app import provenance  # noqa: E402

DATA_PATH = BACKEND_ROOT / "data" / "league_data.json"
BACKUP_SUFFIX = ".bak"

# Fields main.py::enrich_movie has always been able to write -> ambiguous origin.
UNKNOWN_FIELDS = ("imdb", "budget", "gross", "roi")
# Fields no code path has ever written -> can only be human-entered.
MANUAL_FIELDS = ("letterboxd", "rt_crit", "rt_aud", "bo_rank", "awards")

MIGRATION_TIMESTAMP_NOTE = "backfilled by scripts/migrate_provenance.py"


def migrate_entry(entry: dict) -> tuple[int, int]:
    """Backfill one row. Returns (manual_count, unknown_count) written."""
    manual = unknown = 0
    for field in UNKNOWN_FIELDS:
        if entry.get(field) is None:
            continue
        provenance.set_source(entry, field, provenance.UNKNOWN,
                              provider="", legacy_value=entry[field])
        unknown += 1
    for field in MANUAL_FIELDS:
        if entry.get(field) is None:
            continue
        provenance.set_source(entry, field, provenance.MANUAL, provider="")
        manual += 1
    return manual, unknown


def migrate(data: dict) -> dict:
    """Returns a summary dict. Rows that already carry a non-empty `sources` are skipped,
    which is what makes re-running this script a no-op."""
    migrated = skipped = manual_total = unknown_total = 0
    for entry in data["movies"]:
        if isinstance(entry.get("sources"), dict) and entry["sources"]:
            skipped += 1
            continue
        entry.setdefault("sources", {})
        m, u = migrate_entry(entry)
        manual_total += m
        unknown_total += u
        migrated += 1
    return {"movies": len(data["movies"]), "migrated": migrated, "skipped": skipped,
            "manual_fields": manual_total, "unknown_fields": unknown_total}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the summary without writing anything")
    args = parser.parse_args()

    with open(DATA_PATH, "r") as f:
        data = json.load(f)

    summary = migrate(data)
    line = ("SUMMARY: movies={movies} migrated={migrated} skipped={skipped} "
            "manual_fields={manual_fields} unknown_fields={unknown_fields}").format(**summary)
    print(line)

    if args.dry_run:
        print("DRY RUN: no files written")
        return 0

    backup = DATA_PATH.with_suffix(DATA_PATH.suffix + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(DATA_PATH, backup)
        print(f"BACKUP: {backup}")
    else:
        print(f"BACKUP: {backup} (already exists, kept)")

    tmp = DATA_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_PATH)
    print(f"WROTE: {DATA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

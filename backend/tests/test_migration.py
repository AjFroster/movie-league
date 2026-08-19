"""Tests for backend/scripts/migrate_provenance.py.

Import path note: this script lives outside the `app` package (backend/scripts/, no
__init__.py -- it is a script, not a package), so it is reached by adding
backend/scripts to sys.path directly rather than through the app import root that
conftest.py already sets up.
"""
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from migrate_provenance import migrate, migrate_entry  # noqa: E402


def test_fully_null_row_produces_empty_sources(sample_movie):
    entry = dict(sample_movie)

    manual, unknown = migrate_entry(entry)

    assert manual == 0
    assert unknown == 0
    assert entry.get("sources", {}) == {}


def test_ambiguous_and_human_only_fields_classified_correctly(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1
    entry["rt_crit"] = 98

    manual, unknown = migrate_entry(entry)

    assert unknown == 1
    assert manual == 1
    imdb_source = entry["sources"]["imdb"]
    assert imdb_source["origin"] == "unknown"
    assert imdb_source["legacy_value"] == 6.1

    rt_crit_source = entry["sources"]["rt_crit"]
    assert rt_crit_source["origin"] == "manual"
    assert "legacy_value" not in rt_crit_source


def test_bo_rank_and_awards_null_produce_no_entries(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1
    entry["rt_crit"] = 98
    entry["bo_rank"] = None
    entry["awards"] = None

    migrate_entry(entry)

    assert "bo_rank" not in entry["sources"]
    assert "awards" not in entry["sources"]


def test_migrate_on_already_migrated_dataset_is_idempotent(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1
    entry["rt_crit"] = 98
    data = {"owners": ["Liam"], "movies": [entry]}

    first = migrate(data)
    assert first["migrated"] == 1
    assert first["skipped"] == 0

    before = json.dumps(data, sort_keys=True)
    second = migrate(data)
    after = json.dumps(data, sort_keys=True)

    assert second["migrated"] == 0
    assert second["skipped"] == 1
    assert before == after


def test_migrate_reports_totals_across_multiple_rows(sample_movie):
    null_row = dict(sample_movie)
    scored_row = dict(sample_movie)
    scored_row["imdb"] = 6.1
    scored_row["rt_crit"] = 98
    data = {"owners": ["Liam"], "movies": [null_row, scored_row]}

    summary = migrate(data)

    assert summary["movies"] == 2
    assert summary["migrated"] == 2
    assert summary["skipped"] == 0
    assert summary["manual_fields"] == 1
    assert summary["unknown_fields"] == 1

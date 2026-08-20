"""Tests for app.provenance: origins, the no-clobber rule, and legacy_value preservation.

Regression coverage for RESEARCH section 4: main.py::enrich_movie's historical unconditional
overwrite of imdb/budget/gross, and the fact that 16/30 rows carry hand-entered ratings with
no way to distinguish them from machine-written ones.
"""
from datetime import datetime

from app import provenance


def test_get_source_returns_none_when_no_provenance_recorded(sample_movie):
    entry = dict(sample_movie)
    assert provenance.get_source(entry, "imdb") is None


def test_set_source_creates_sources_dict_if_absent(sample_movie):
    entry = dict(sample_movie)
    del entry["sources"]
    assert "sources" not in entry

    provenance.set_source(entry, "imdb", provenance.FETCHED, provider="omdb")

    assert "sources" in entry
    source = entry["sources"]["imdb"]
    assert source["origin"] == provenance.FETCHED
    assert source["provider"] == "omdb"
    assert "at" in source
    parsed = datetime.fromisoformat(source["at"])
    assert parsed.tzinfo is not None


def test_can_write_true_when_no_source_and_field_empty(sample_movie):
    entry = dict(sample_movie)
    assert entry["imdb"] is None
    assert provenance.can_write(entry, "imdb") is True


def test_can_write_false_when_no_source_but_field_has_value(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    assert provenance.can_write(entry, "imdb") is False


def test_can_write_false_for_manual_origin(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    provenance.set_source(entry, "imdb", provenance.MANUAL)
    assert provenance.can_write(entry, "imdb") is False


def test_can_write_true_for_fetched_origin(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    provenance.set_source(entry, "imdb", provenance.FETCHED, provider="omdb")
    assert provenance.can_write(entry, "imdb") is True


def test_can_write_true_for_unknown_origin(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1
    provenance.set_source(entry, "imdb", provenance.UNKNOWN, legacy_value=6.1)
    assert provenance.can_write(entry, "imdb") is True


def test_can_write_force_true_overrides_every_case(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    provenance.set_source(entry, "imdb", provenance.MANUAL)
    assert provenance.can_write(entry, "imdb") is False
    assert provenance.can_write(entry, "imdb", force=True) is True


def test_apply_fetched_on_manual_field_refused(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    provenance.set_source(entry, "imdb", provenance.MANUAL)

    result = provenance.apply_fetched(entry, "imdb", 8.0, provider="omdb")

    assert result is False
    assert entry["imdb"] == 7.0


def test_apply_fetched_on_manual_field_with_force_succeeds(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0
    provenance.set_source(entry, "imdb", provenance.MANUAL)

    result = provenance.apply_fetched(entry, "imdb", 8.0, provider="omdb", force=True)

    assert result is True
    assert entry["imdb"] == 8.0
    assert provenance.get_source(entry, "imdb")["origin"] == provenance.FETCHED


def test_apply_fetched_on_unknown_field_preserves_legacy_value(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1
    provenance.set_source(entry, "imdb", provenance.UNKNOWN, legacy_value=6.1)

    result = provenance.apply_fetched(entry, "imdb", 7.4, provider="omdb")

    assert result is True
    assert entry["imdb"] == 7.4
    source = provenance.get_source(entry, "imdb")
    assert source["origin"] == provenance.FETCHED
    assert source["legacy_value"] == 6.1


def test_apply_fetched_with_none_value_writes_nothing(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = None

    result = provenance.apply_fetched(entry, "imdb", None, provider="omdb")

    assert result is False
    assert entry["imdb"] is None
    assert provenance.get_source(entry, "imdb") is None


def test_mark_manual_sets_origin_manual_with_empty_provider(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 7.0

    provenance.mark_manual(entry, "imdb")

    source = provenance.get_source(entry, "imdb")
    assert source["origin"] == provenance.MANUAL
    assert source["provider"] == ""


def test_enrichable_fields_constant():
    """rt_aud and letterboxd became fetchable when MDBList replaced OMDb as the ratings
    source; before that no free provider carried either."""
    assert provenance.ENRICHABLE_FIELDS == (
        "imdb", "rt_crit", "rt_aud", "letterboxd", "budget", "gross", "roi")


# --- Verbatim regression tests from PLAN.md (RESEARCH section 4) ---

def test_manual_value_survives_enrichment_but_yields_to_force(sample_movie):
    entry = dict(sample_movie)
    entry["rt_crit"] = 98
    provenance.mark_manual(entry, "rt_crit")

    assert provenance.apply_fetched(entry, "rt_crit", 54, provider="omdb") is False
    assert entry["rt_crit"] == 98

    assert provenance.apply_fetched(entry, "rt_crit", 54, provider="omdb", force=True) is True
    assert entry["rt_crit"] == 54
    assert provenance.get_source(entry, "rt_crit")["origin"] == provenance.FETCHED


def test_unknown_legacy_value_is_corrected_but_never_lost(sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 6.1  # may be a TMDB vote_average, not a real IMDb rating
    provenance.set_source(entry, "imdb", provenance.UNKNOWN, legacy_value=6.1)

    assert provenance.apply_fetched(entry, "imdb", 7.4, provider="omdb") is True
    assert entry["imdb"] == 7.4
    source = provenance.get_source(entry, "imdb")
    assert source["origin"] == provenance.FETCHED
    assert source["provider"] == "omdb"
    assert source["legacy_value"] == 6.1


def test_apply_fetched_is_a_noop_when_the_value_is_unchanged(sample_movie):
    """Re-applying an identical provider value must not report an update.

    Guards the cached-repeat-run case: when every field is served from cache the run makes
    zero outbound calls, so league_data.json must not be rewritten with fresh timestamps.
    Mirrors the same guard on enrichment.compute_roi.
    """
    entry = dict(sample_movie)

    assert provenance.apply_fetched(entry, "imdb", 7.4, provider="omdb") is True
    stamped_at = provenance.get_source(entry, "imdb")["at"]

    assert provenance.apply_fetched(entry, "imdb", 7.4, provider="omdb") is False
    assert provenance.get_source(entry, "imdb")["at"] == stamped_at

    # a genuinely different value still lands, and force still overrides
    assert provenance.apply_fetched(entry, "imdb", 7.9, provider="omdb") is True
    assert entry["imdb"] == 7.9
    assert provenance.apply_fetched(entry, "imdb", 7.9, provider="omdb", force=True) is True

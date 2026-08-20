"""Tests for the enrichment engine: cached provider fetches, the no-clobber merge, ROI
derivation, and the sequentially-paced, hard-capped bulk runner.

Every provider call in this suite is monkeypatched -- no network, no real API keys (the
autouse `no_real_api_keys` fixture in conftest.py strips both provider keys before every
test). The three tests carried over verbatim from PLAN.md are the regression tests for this
phase's headline guarantees: a repeat run costs zero calls, TMDB's vote_average never leaks
into `imdb`, and a keyless run never poisons the cache. `test_cap_stops_the_run_from_burning_
quota` and `test_rows_are_paced_sequentially_never_concurrently` (also verbatim) are the
regression tests for ROADMAP success criterion 4 -- the per-run call cap.
"""
from pathlib import Path

import httpx
import pytest

from app import enrichment, provenance
from app.redaction import ProviderError
from app.services import cache, omdb, tmdb

TMDB_PAYLOAD = {"tmdb_id": 1, "budget_millions": 170.0, "gross_millions": 100.5,
                "vote_average": 9.9, "imdb_id": "tt0111161", "release_date": "2001-04-01"}
OMDB_PAYLOAD = {"imdb_id": "tt0111161", "imdb": 6.1, "rt_crit": 54.0}

# Fields no automated enrichment run may ever touch -- hand-entered, watch-tracking, or
# purely derived-from-hand-entry. RESEARCH section 3: there is no scoring formula in code.
INVARIANT_FIELDS = ("rating_score", "financial_score", "penalties", "watch_points", "total",
                    "letterboxd", "rt_aud", "who_watched", "penalty_notes")


@pytest.fixture
def fake_providers(monkeypatch):
    """Replace both provider modules with counting fakes. No network, no keys."""
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    calls = {"tmdb": 0, "omdb": 0}

    async def fake_tmdb(title, year=None, *, client=None):
        calls["tmdb"] += 1
        return dict(TMDB_PAYLOAD)

    async def fake_omdb(imdb_id, *, client=None):
        calls["omdb"] += 1
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)
    return calls


# ---------------------------------------------------------------------------
# CallBudget
# ---------------------------------------------------------------------------

def test_call_budget_available_becomes_false_after_max_calls():
    budget = enrichment.CallBudget(2)
    assert budget.available() is True
    assert budget.exhausted is False

    budget.spend()
    assert budget.available() is True
    assert budget.exhausted is False

    budget.spend()
    assert budget.available() is False
    assert budget.exhausted is True
    assert budget.used == 2


# ---------------------------------------------------------------------------
# fetch_tmdb
# ---------------------------------------------------------------------------

async def test_fetch_tmdb_cold_cache_calls_provider_once_and_caches(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    calls = {"n": 0}

    async def fake(title, year=None, *, client=None):
        calls["n"] += 1
        return dict(TMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_tmdb("Some Movie", budget=budget)
    assert payload == TMDB_PAYLOAD
    assert outcome == enrichment.OUTCOME_FETCHED
    assert calls["n"] == 1
    assert budget.used == 1

    payload2, outcome2 = await enrichment.fetch_tmdb("Some Movie", budget=budget)
    assert payload2 == TMDB_PAYLOAD
    assert outcome2 == enrichment.OUTCOME_CACHE
    assert calls["n"] == 1  # no further provider call


async def test_fetch_tmdb_force_true_skips_cache_and_calls_again(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    calls = {"n": 0}

    async def fake(title, year=None, *, client=None):
        calls["n"] += 1
        return dict(TMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake)
    budget = enrichment.CallBudget(10)

    await enrichment.fetch_tmdb("Some Movie", budget=budget)
    assert calls["n"] == 1

    payload, outcome = await enrichment.fetch_tmdb("Some Movie", budget=budget, force=True)
    assert outcome == enrichment.OUTCOME_FETCHED
    assert payload == TMDB_PAYLOAD
    assert calls["n"] == 2


async def test_fetch_tmdb_no_match_writes_negative_cache_entry(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    calls = {"n": 0}

    async def fake(title, year=None, *, client=None):
        calls["n"] += 1
        return None

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_tmdb("Unknown Movie", budget=budget)
    assert payload is None
    assert outcome == enrichment.OUTCOME_MISS
    assert calls["n"] == 1

    payload2, outcome2 = await enrichment.fetch_tmdb("Unknown Movie", budget=budget)
    assert payload2 is None
    assert outcome2 == enrichment.OUTCOME_CACHE
    assert calls["n"] == 1


async def test_fetch_tmdb_no_key_spends_no_budget_and_writes_nothing(tmp_cache, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_tmdb("Some Movie", budget=budget)

    assert payload is None
    assert outcome == enrichment.OUTCOME_NO_KEY
    assert budget.used == 0
    assert cache.load_cache() == {}


async def test_fetch_tmdb_capped_when_budget_exhausted(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    calls = {"n": 0}

    async def fake(title, year=None, *, client=None):
        calls["n"] += 1
        return dict(TMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake)
    budget = enrichment.CallBudget(0)

    payload, outcome = await enrichment.fetch_tmdb("Some Movie", budget=budget)

    assert payload is None
    assert outcome == enrichment.OUTCOME_CAPPED
    assert calls["n"] == 0


async def test_fetch_tmdb_provider_error_spends_budget_writes_no_cache(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")

    async def fake(title, year=None, *, client=None):
        raise httpx.ConnectError("boom talking to tmdb")

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_tmdb("Some Movie", budget=budget)

    assert payload is None
    assert outcome.startswith(enrichment.ERROR_PREFIX)
    assert budget.used == 1
    assert cache.load_cache() == {}


# ---------------------------------------------------------------------------
# fetch_omdb -- same contract as fetch_tmdb, keyed on imdb_id, TTL from release_date
# ---------------------------------------------------------------------------

async def test_fetch_omdb_cold_cache_calls_once_and_caches(tmp_cache, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    calls = {"n": 0}

    async def fake(imdb_id, *, client=None):
        calls["n"] += 1
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(omdb, "fetch_ratings", fake)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_omdb(
        "tt0111161", release_date="2001-04-01", budget=budget)
    assert payload == OMDB_PAYLOAD
    assert outcome == enrichment.OUTCOME_FETCHED
    assert calls["n"] == 1

    payload2, outcome2 = await enrichment.fetch_omdb(
        "tt0111161", release_date="2001-04-01", budget=budget)
    assert payload2 == OMDB_PAYLOAD
    assert outcome2 == enrichment.OUTCOME_CACHE
    assert calls["n"] == 1


async def test_fetch_omdb_cache_key_is_provider_prefixed_imdb_id(tmp_cache, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")

    async def fake(imdb_id, *, client=None):
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(omdb, "fetch_ratings", fake)
    budget = enrichment.CallBudget(10)

    await enrichment.fetch_omdb("tt0111161", release_date="2001-04-01", budget=budget)

    assert "omdb:tt0111161" in cache.load_cache()


async def test_fetch_omdb_no_key_spends_no_budget_and_writes_nothing(tmp_cache, monkeypatch):
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_omdb(
        "tt0111161", release_date=None, budget=budget)

    assert payload is None
    assert outcome == enrichment.OUTCOME_NO_KEY
    assert budget.used == 0
    assert cache.load_cache() == {}


async def test_fetch_omdb_capped_when_budget_exhausted(tmp_cache, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    budget = enrichment.CallBudget(0)

    payload, outcome = await enrichment.fetch_omdb(
        "tt0111161", release_date=None, budget=budget)

    assert payload is None
    assert outcome == enrichment.OUTCOME_CAPPED


async def test_fetch_omdb_provider_error_is_redacted_and_spends_budget(tmp_cache, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRETOMDBKEY")

    async def fake(imdb_id, *, client=None):
        raise ProviderError(
            "failed for https://www.omdbapi.com/?apikey=SUPERSECRETOMDBKEY", provider="omdb")

    monkeypatch.setattr(omdb, "fetch_ratings", fake)
    budget = enrichment.CallBudget(10)

    payload, outcome = await enrichment.fetch_omdb(
        "tt0111161", release_date=None, budget=budget)

    assert payload is None
    assert outcome.startswith(enrichment.ERROR_PREFIX)
    assert "SUPERSECRETOMDBKEY" not in outcome
    assert budget.used == 1
    assert cache.load_cache() == {}


async def test_fetch_omdb_ttl_derived_from_release_date_argument(tmp_cache, monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")

    async def fake(imdb_id, *, client=None):
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(omdb, "fetch_ratings", fake)
    budget = enrichment.CallBudget(10)

    await enrichment.fetch_omdb("tt0111161", release_date="2001-04-01", budget=budget)

    entry = cache.load_cache()["omdb:tt0111161"]
    assert entry["ttl_seconds"] == cache.TTL_RELEASED


# ---------------------------------------------------------------------------
# compute_roi
# ---------------------------------------------------------------------------

def test_compute_roi_sets_value_and_provenance(sample_movie):
    entry = dict(sample_movie)
    entry["budget"] = 170.0
    entry["gross"] = 100.5

    result = enrichment.compute_roi(entry)

    assert result is True
    assert entry["roi"] == round(100.5 / 170.0, 3)
    source = provenance.get_source(entry, "roi")
    assert source["origin"] == provenance.FETCHED
    assert source["provider"] == "derived"


@pytest.mark.parametrize("budget,gross", [(0, 10), (-5, 10), (None, 10), ("bad", 10)])
def test_compute_roi_false_for_bad_budget(sample_movie, budget, gross):
    entry = dict(sample_movie)
    entry["budget"] = budget
    entry["gross"] = gross
    assert enrichment.compute_roi(entry) is False


def test_compute_roi_is_a_noop_when_the_value_is_unchanged(sample_movie):
    """A second derivation of the identical value must not report an update.

    Guards the keyless-run case: with no API keys set, enrich_all makes zero calls, so
    nothing about a row has changed and league_data.json must not be rewritten.
    """
    entry = dict(sample_movie)
    entry["budget"] = 170.0
    entry["gross"] = 100.5

    assert enrichment.compute_roi(entry) is True          # first pass stamps provenance
    stamped_at = provenance.get_source(entry, "roi")["at"]

    assert enrichment.compute_roi(entry) is False         # second pass is a true no-op
    assert provenance.get_source(entry, "roi")["at"] == stamped_at
    assert enrichment.compute_roi(entry, force=True) is True   # force still overrides


def test_compute_roi_leaves_an_unrecorded_existing_value_alone(sample_movie):
    """An existing value with no provenance record is never touched.

    `can_write` is fail-closed here -- an unrecorded value is treated as a human's until
    proven otherwise -- so the no-op guard is never even reached. Asserted explicitly so a
    future relaxation of that rule has to break a test rather than silently rewrite data.
    """
    entry = dict(sample_movie)
    entry["budget"] = 170.0
    entry["gross"] = 100.5
    entry["roi"] = 99.9          # deliberately NOT the derivable value
    entry["sources"] = {}

    assert enrichment.compute_roi(entry) is False
    assert entry["roi"] == 99.9
    assert provenance.get_source(entry, "roi") is None


def test_compute_roi_respects_manual_and_force(sample_movie):
    entry = dict(sample_movie)
    entry["budget"] = 170.0
    entry["gross"] = 100.5
    provenance.mark_manual(entry, "roi")

    assert enrichment.compute_roi(entry) is False
    assert entry.get("roi") in (None, 0)
    assert enrichment.compute_roi(entry, force=True) is True
    assert entry["roi"] == round(100.5 / 170.0, 3)


# ---------------------------------------------------------------------------
# enrich_entry
# ---------------------------------------------------------------------------

async def test_enrich_entry_fills_all_fields_on_empty_row(tmp_cache, fake_providers, sample_movie):
    entry = dict(sample_movie)

    report = await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    assert entry["budget"] == TMDB_PAYLOAD["budget_millions"]
    assert entry["gross"] == TMDB_PAYLOAD["gross_millions"]
    assert entry["imdb"] == OMDB_PAYLOAD["imdb"]
    assert entry["rt_crit"] == OMDB_PAYLOAD["rt_crit"]
    assert entry["roi"] == round(TMDB_PAYLOAD["gross_millions"] / TMDB_PAYLOAD["budget_millions"], 3)
    assert set(report["updated"]) == {"budget", "gross", "imdb", "rt_crit", "roi"}
    assert report["protected"] == []
    assert report["errors"] == []
    assert report["owner"] == entry["owner"]
    assert report["round"] == entry["round"]
    assert report["movie"] == entry["movie"]


async def test_enrich_entry_protects_manual_field_and_reports_it(tmp_cache, fake_providers, sample_movie):
    entry = dict(sample_movie)
    entry["rt_crit"] = 98
    provenance.mark_manual(entry, "rt_crit")

    report = await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    assert entry["rt_crit"] == 98
    assert "rt_crit" in report["protected"]
    assert "rt_crit" not in report["updated"]


async def test_enrich_entry_overwrites_unknown_field_and_preserves_legacy_value(
        tmp_cache, fake_providers, sample_movie):
    entry = dict(sample_movie)
    entry["imdb"] = 9.9  # legacy TMDB vote_average, pre-provenance
    provenance.set_source(entry, "imdb", provenance.UNKNOWN, legacy_value=9.9)

    report = await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    assert entry["imdb"] == OMDB_PAYLOAD["imdb"]
    assert "imdb" in report["updated"]
    source = provenance.get_source(entry, "imdb")
    assert source["origin"] == provenance.FETCHED
    assert source["legacy_value"] == 9.9


async def test_enrich_entry_no_imdb_id_skips_omdb_call(tmp_cache, monkeypatch, sample_movie):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    omdb_calls = {"n": 0}

    async def fake_tmdb(title, year=None, *, client=None):
        payload = dict(TMDB_PAYLOAD)
        payload["imdb_id"] = None
        return payload

    async def fake_omdb(imdb_id, *, client=None):
        omdb_calls["n"] += 1
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)

    entry = dict(sample_movie)
    report = await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    assert report["omdb"] == enrichment.OUTCOME_NO_IMDB_ID
    assert omdb_calls["n"] == 0
    assert entry["imdb"] is None
    assert entry["rt_crit"] is None


async def test_enrich_entry_never_touches_scoring_or_manual_only_fields(
        tmp_cache, fake_providers, sample_movie):
    entry = dict(sample_movie)
    entry["rating_score"] = 12
    entry["financial_score"] = 7
    entry["penalties"] = 1
    entry["watch_points"] = 3
    entry["total"] = 20
    entry["who_watched"] = ["Liam"]
    entry["penalty_notes"] = "late watch"
    before = {k: entry[k] for k in INVARIANT_FIELDS}

    await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    after = {k: entry[k] for k in INVARIANT_FIELDS}
    assert before == after


async def test_enrich_entry_provider_error_is_redacted_in_report(tmp_cache, monkeypatch, sample_movie):
    monkeypatch.setenv("TMDB_API_KEY", "SUPERSECRETTMDBKEY")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")

    async def failing_tmdb(title, year=None, *, client=None):
        raise httpx.HTTPError(
            "Client error for url https://api.themoviedb.org/3/search/movie?query=X "
            "Authorization: Bearer SUPERSECRETTMDBKEY")

    monkeypatch.setattr(tmdb, "fetch_movie_financials", failing_tmdb)

    entry = dict(sample_movie)
    report = await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))

    assert len(report["errors"]) == 1
    assert "SUPERSECRETTMDBKEY" not in report["errors"][0]
    assert report["omdb"] == enrichment.OUTCOME_NO_IMDB_ID  # tmdb failed, so no imdb_id to chase


# ---------------------------------------------------------------------------
# Verbatim regression tests from PLAN.md -- the phase's headline guarantees
# ---------------------------------------------------------------------------

async def test_second_run_costs_zero_api_calls(tmp_cache, fake_providers, sample_movie):
    entry = dict(sample_movie)
    await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))
    assert fake_providers == {"tmdb": 1, "omdb": 1}

    await enrichment.enrich_entry(dict(sample_movie), budget=enrichment.CallBudget(10))
    assert fake_providers == {"tmdb": 1, "omdb": 1}  # served entirely from cache


async def test_tmdb_vote_average_never_becomes_the_imdb_rating(tmp_cache, fake_providers,
                                                               sample_movie):
    entry = dict(sample_movie)
    await enrichment.enrich_entry(entry, budget=enrichment.CallBudget(10))
    assert entry["imdb"] == 6.1                       # OMDb's imdbRating
    assert entry["imdb"] != TMDB_PAYLOAD["vote_average"]
    assert provenance.get_source(entry, "imdb")["provider"] == "omdb"


async def test_keyless_run_writes_no_negative_cache_entry(tmp_cache, monkeypatch, sample_movie):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    budget = enrichment.CallBudget(10)

    report = await enrichment.enrich_entry(dict(sample_movie), budget=budget)

    assert report["tmdb"] == enrichment.OUTCOME_NO_KEY
    assert budget.used == 0
    assert cache.load_cache() == {}   # nothing poisoned; adding a key later works immediately


# ---------------------------------------------------------------------------
# enrich_all -- sequential pacing and the enforced per-run cap
# ---------------------------------------------------------------------------

async def _noop_sleep(_delay):
    """Recording-free fake sleep so the bulk-runner tests stay instant."""
    return None


def _bulk_rows(n=3):
    return [{"owner": "Liam", "round": i, "movie": f"Film {i}", "imdb": None, "rt_crit": None,
             "budget": None, "gross": None, "roi": None, "sources": {}} for i in range(1, n + 1)]


@pytest.fixture
def fake_providers_distinct(monkeypatch):
    """Like `fake_providers`, but each title resolves to its own imdb_id.

    `fake_providers` returns the same TMDB_PAYLOAD (and therefore the same imdb_id) no
    matter the title -- correct for the single-movie Task 1 tests, but wrong for a bulk
    test over several genuinely different films: OMDb's cache is keyed on imdb_id, so
    reusing one fake id across rows would make row 2 and row 3 hit row 1's cache entry
    (correct caching behaviour, but not what "3 rows -> 3 OMDb calls" is meant to prove).
    """
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSENTINEL")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    calls = {"tmdb": 0, "omdb": 0}

    async def fake_tmdb(title, year=None, *, client=None):
        calls["tmdb"] += 1
        index = title.rsplit(" ", 1)[-1]
        payload = dict(TMDB_PAYLOAD)
        payload["imdb_id"] = f"tt{int(index):07d}"
        return payload

    async def fake_omdb(imdb_id, *, client=None):
        calls["omdb"] += 1
        payload = dict(OMDB_PAYLOAD)
        payload["imdb_id"] = imdb_id
        return payload

    monkeypatch.setattr(tmdb, "fetch_movie_financials", fake_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)
    return calls


async def test_enrich_all_processes_every_row_with_generous_cap(tmp_cache, fake_providers_distinct):
    data = {"owners": ["Liam"], "movies": _bulk_rows(3)}

    summary = await enrichment.enrich_all(data, max_calls=100, sleep=_noop_sleep)

    assert fake_providers_distinct == {"tmdb": 3, "omdb": 3}
    assert summary["movies_processed"] == 3
    assert summary["api_calls_used"] == (
        fake_providers_distinct["tmdb"] + fake_providers_distinct["omdb"])
    assert summary["cap_reached"] is False


async def test_enrich_all_second_run_costs_zero_api_calls(tmp_cache, fake_providers_distinct):
    await enrichment.enrich_all({"owners": ["Liam"], "movies": _bulk_rows(3)}, sleep=_noop_sleep)
    assert fake_providers_distinct == {"tmdb": 3, "omdb": 3}

    summary = await enrichment.enrich_all(
        {"owners": ["Liam"], "movies": _bulk_rows(3)}, sleep=_noop_sleep)

    assert summary["api_calls_used"] == 0
    assert fake_providers_distinct == {"tmdb": 3, "omdb": 3}  # unchanged -- all from cache


async def test_enrich_all_force_true_refetches_every_row(tmp_cache, fake_providers_distinct):
    await enrichment.enrich_all({"owners": ["Liam"], "movies": _bulk_rows(3)}, sleep=_noop_sleep)
    assert fake_providers_distinct == {"tmdb": 3, "omdb": 3}

    summary = await enrichment.enrich_all(
        {"owners": ["Liam"], "movies": _bulk_rows(3)}, force=True, sleep=_noop_sleep)

    assert summary["forced"] is True
    assert fake_providers_distinct == {"tmdb": 6, "omdb": 6}
    assert summary["api_calls_used"] == 6


async def test_enrich_all_mutates_rows_in_place(tmp_cache, fake_providers):
    data = {"owners": ["Liam"], "movies": _bulk_rows(1)}
    row = data["movies"][0]
    assert row["imdb"] is None

    await enrichment.enrich_all(data, sleep=_noop_sleep)

    assert data["movies"][0] is row               # same object, mutated -- not replaced
    assert row["imdb"] == OMDB_PAYLOAD["imdb"]


async def test_enrich_all_summary_totals_match_per_row_reports(tmp_cache, fake_providers):
    data = {"owners": ["Liam"], "movies": _bulk_rows(2)}

    summary = await enrichment.enrich_all(data, sleep=_noop_sleep)

    assert summary["fields_updated"] == sum(len(r["updated"]) for r in summary["reports"])
    assert summary["fields_protected"] == sum(len(r["protected"]) for r in summary["reports"])
    assert summary["fields_updated"] == 10   # 5 fields x 2 rows, all empty going in
    assert summary["fields_protected"] == 0


async def test_enrich_all_one_row_error_does_not_abort_run(tmp_cache, monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "SECRETTMDBKEY12345")
    monkeypatch.setenv("OMDB_API_KEY", "OMDBSENTINEL")
    calls = {"tmdb": 0, "omdb": 0}

    async def flaky_tmdb(title, year=None, *, client=None):
        calls["tmdb"] += 1
        if title == "Film 1":
            raise httpx.HTTPError(f"boom for {title} key=SECRETTMDBKEY12345")
        return dict(TMDB_PAYLOAD)

    async def fake_omdb(imdb_id, *, client=None):
        calls["omdb"] += 1
        return dict(OMDB_PAYLOAD)

    monkeypatch.setattr(tmdb, "fetch_movie_financials", flaky_tmdb)
    monkeypatch.setattr(omdb, "fetch_ratings", fake_omdb)

    data = {"owners": ["Liam"], "movies": _bulk_rows(3)}
    summary = await enrichment.enrich_all(data, sleep=_noop_sleep)

    assert summary["movies_processed"] == 3       # every row still reported
    assert calls["tmdb"] == 3                      # every row still attempted
    assert len(summary["errors"]) == 1
    assert "SECRETTMDBKEY12345" not in summary["errors"][0]
    # rows after the failing one were still processed
    assert data["movies"][1]["imdb"] == OMDB_PAYLOAD["imdb"]
    assert data["movies"][2]["imdb"] == OMDB_PAYLOAD["imdb"]
    assert data["movies"][0]["imdb"] is None       # the failing row itself got nothing


def test_enrichment_module_never_uses_asyncio_gather():
    source = Path(enrichment.__file__).read_text()
    assert "asyncio.gather" not in source


# --- Verbatim from PLAN.md ---------------------------------------------------------

async def test_cap_stops_the_run_from_burning_quota(tmp_cache, fake_providers):
    data = {"owners": ["Liam"], "movies": [
        {"owner": "Liam", "round": n, "movie": f"Film {n}", "imdb": None, "rt_crit": None,
         "budget": None, "gross": None, "roi": None, "sources": {}} for n in (1, 2, 3)]}

    summary = await enrichment.enrich_all(data, max_calls=2, sleep=_noop_sleep)

    assert fake_providers["tmdb"] + fake_providers["omdb"] == 2
    assert summary["api_calls_used"] == 2
    assert summary["cap_reached"] is True
    assert summary["movies_processed"] == 3          # every row is still reported
    assert any(r["tmdb"] == enrichment.OUTCOME_CAPPED
               or r["omdb"] == enrichment.OUTCOME_CAPPED for r in summary["reports"])


async def test_rows_are_paced_sequentially_never_concurrently(tmp_cache, fake_providers):
    order = []

    async def recording_sleep(_delay):
        order.append(len(order))

    data = {"owners": ["Liam"], "movies": [
        {"owner": "Liam", "round": n, "movie": f"Film {n}", "imdb": None, "rt_crit": None,
         "budget": None, "gross": None, "roi": None, "sources": {}} for n in (1, 2, 3)]}

    await enrichment.enrich_all(data, sleep=recording_sleep)

    assert len(order) == 3          # one delay per row

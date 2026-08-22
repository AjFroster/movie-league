"""Coverage for the persistent JSON API cache: key format, tiered TTL, negative
caching, expiry, and corrupt-file tolerance. Every writing test uses the tmp_cache
fixture so the real backend/data/api_cache.json is never touched."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import cache

# -- make_key -------------------------------------------------------------------

def test_make_key_prefers_imdb_id():
    assert cache.make_key("omdb", imdb_id="tt0111161") == "omdb:tt0111161"


def test_make_key_normalizes_title_and_year():
    assert cache.make_key("tmdb", title="  The   MUMMY ", year=2026) == "tmdb:title:the mummy:2026"


def test_make_key_title_only_leaves_empty_year_slot():
    assert cache.make_key("tmdb", title="Digger") == "tmdb:title:digger:"


def test_make_key_requires_imdb_id_or_title():
    with pytest.raises(ValueError):
        cache.make_key("tmdb")


# -- ttl_for ----------------------------------------------------------------------

def test_ttl_for_no_match_is_negative():
    assert cache.ttl_for(None, matched=False) == cache.TTL_NEGATIVE


def test_ttl_for_released_over_a_year_ago_is_released_tier():
    assert cache.ttl_for("2001-04-01", matched=True) == cache.TTL_RELEASED


def test_ttl_for_released_recently_is_recent_tier():
    recent_date = (datetime.now(tz=timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    assert cache.ttl_for(recent_date, matched=True) == cache.TTL_RECENT


def test_ttl_for_unreleased_film_is_negative():
    assert cache.ttl_for("2099-01-01", matched=True) == cache.TTL_NEGATIVE


def test_ttl_for_undated_string_is_negative():
    assert cache.ttl_for("not-a-date", matched=True) == cache.TTL_NEGATIVE


# -- put/get round trip, expiry, negative caching ----------------------------------

def test_put_get_round_trip_returns_same_payload_and_writes_file(tmp_cache):
    entry = cache.put("omdb:tt1", {"imdbRating": "8.5"}, cache.TTL_RECENT)
    fetched = cache.get("omdb:tt1")
    assert fetched is not None
    assert fetched["payload"] == {"imdbRating": "8.5"}
    assert fetched["status"] == cache.STATUS_HIT
    assert entry["payload"] == {"imdbRating": "8.5"}
    assert tmp_cache.exists()


def test_get_returns_entry_before_expiry_and_none_after(tmp_cache):
    cache.put("omdb:tt2", {"imdbRating": "7.0"}, 10, now=1000)
    assert cache.get("omdb:tt2", now=1005) is not None
    assert cache.get("omdb:tt2", now=1011) is None


def test_negative_caching_is_distinguishable_from_cache_absence(tmp_cache):
    cache.put("omdb:tt3", None, cache.TTL_NEGATIVE)
    entry = cache.get("omdb:tt3")
    assert entry is not None
    assert entry["payload"] is None
    assert entry["status"] == cache.STATUS_MISS
    # A key that was never written returns plain None -- not a miss entry.
    assert cache.get("omdb:never-written") is None


# -- load_cache / save_cache resilience ---------------------------------------------

def test_load_cache_returns_empty_dict_when_file_missing(tmp_cache):
    assert not tmp_cache.exists()
    assert cache.load_cache() == {}


def test_load_cache_returns_empty_dict_on_invalid_json_without_raising(tmp_cache):
    tmp_cache.write_text("{not valid json")
    assert cache.load_cache() == {}


def test_save_cache_leaves_no_tmp_file_behind(tmp_cache):
    cache.save_cache({"omdb:tt1": {"status": cache.STATUS_HIT, "payload": {}}})
    tmp_file = tmp_cache.with_suffix(".tmp")
    assert not tmp_file.exists()
    assert tmp_cache.exists()

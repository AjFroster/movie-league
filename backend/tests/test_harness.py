"""Proves the harness itself works before any feature depends on it."""
import asyncio
import os

from app.db.models import League
from app.main import app


def test_app_imports_with_expected_routes():
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/health" in paths
    assert "/api/leagues" in paths


def test_every_data_route_is_league_scoped():
    """No route may act on "whichever league is newest" -- that was the legacy shape, and
    it silently wrote to the wrong season once four leagues existed."""
    data_paths = {r.path for r in app.routes if hasattr(r, "methods")
                  and r.path.startswith("/api/")
                  and r.path not in ("/api/health", "/api/export")}
    unscoped = {p for p in data_paths if "{league_id}" not in p and p != "/api/leagues"}
    assert unscoped == {"/api/leagues/pool-size"}, unscoped


async def test_async_tests_are_collected_and_run():
    """If this errors with 'async def functions are not natively supported',
    pytest.ini's asyncio_mode = auto is not being picked up."""
    await asyncio.sleep(0)
    assert True


def test_tmp_league_isolates_real_data(tmp_league, never_touch_the_real_database):
    with never_touch_the_real_database() as session:
        league = session.get(League, tmp_league)
        assert [p.name for p in league.players] == ["Liam"]


def test_provider_keys_are_stripped_by_default():
    assert os.environ.get("OMDB_API_KEY") is None
    assert os.environ.get("TMDB_API_KEY") is None

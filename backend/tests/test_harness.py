"""Proves the harness itself works before any feature depends on it."""
import asyncio
import os

from app import storage
from app.main import app


def test_app_imports_with_expected_routes():
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/leaderboard" in paths
    assert "/api/health" in paths


async def test_async_tests_are_collected_and_run():
    """If this errors with 'async def functions are not natively supported',
    pytest.ini's asyncio_mode = auto is not being picked up."""
    await asyncio.sleep(0)
    assert True


def test_tmp_league_isolates_real_data(tmp_league):
    assert storage.DATA_PATH == tmp_league
    assert storage.load_data()["owners"] == ["Liam"]


def test_provider_keys_are_stripped_by_default():
    assert os.environ.get("OMDB_API_KEY") is None
    assert os.environ.get("TMDB_API_KEY") is None

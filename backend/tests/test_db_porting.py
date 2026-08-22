"""Tests for the JSON <-> database round trip.

The one that matters is `test_round_trip_preserves_the_real_league`: it imports the actual
league_data.json and asserts the export is identical. Anything less is a claim, not
evidence, and this migration only runs once against data that cannot be regenerated.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import STATUS_COMPLETE, Entry, Player, Watch
from app.db.porting import export_league, export_to_file, import_league

REAL_DATA = Path(__file__).resolve().parent.parent / "data" / "league_data.json"


SMALL = {
    "owners": ["Ann", "Bob"],
    "movies": [
        {"owner": "Ann", "round": 1, "movie": "Alpha", "imdb": 8.0, "letterboxd": 4.1,
         "rt_crit": 90.0, "rt_aud": 88.0, "budget": 100.0, "gross": 300.0, "roi": 3.0,
         "bo_rank": None, "awards": None, "who_watched": ["Ann", "Bob"],
         "rating_score": 21, "financial_score": 10, "penalties": 0, "penalty_notes": "",
         "watch_points": 5, "total": 36, "sources": {"imdb": {"origin": "manual"}}},
        {"owner": "Bob", "round": 1, "movie": "Beta", "imdb": None, "letterboxd": None,
         "rt_crit": None, "rt_aud": None, "budget": None, "gross": None, "roi": None,
         "bo_rank": None, "awards": None, "who_watched": [],
         "rating_score": 0, "financial_score": 0, "penalties": 0, "penalty_notes": "",
         "watch_points": 0, "total": 0, "sources": {}},
    ],
}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def test_import_creates_league_players_entries_and_watches(session):
    league = import_league(session, SMALL, name="Test", year=2026)
    assert league.status == STATUS_COMPLETE     # an imported season has no draft to run
    assert {p.name for p in league.players} == {"Ann", "Bob"}
    assert len(session.scalars(select(Entry)).all()) == 2
    assert len(session.scalars(select(Watch)).all()) == 2


def test_import_infers_rounds_from_the_data(session):
    data = {"owners": ["Ann"], "movies": [{"owner": "Ann", "round": r, "movie": f"M{r}",
                                           "who_watched": []} for r in range(1, 7)]}
    assert import_league(session, data, name="T", year=2026).rounds == 6


def test_import_ignores_watchers_who_are_not_players(session):
    """A stray name in who_watched must not conjure a player row."""
    data = json.loads(json.dumps(SMALL))
    data["movies"][0]["who_watched"] = ["Ann", "Ghost"]
    import_league(session, data, name="T", year=2026)
    assert {p.name for p in session.scalars(select(Player)).all()} == {"Ann", "Bob"}
    assert len(session.scalars(select(Watch)).all()) == 1


def test_import_rejects_an_empty_league(session):
    with pytest.raises(ValueError):
        import_league(session, {"owners": [], "movies": []}, name="T", year=2026)


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------

def test_round_trip_is_lossless(session):
    league = import_league(session, SMALL, name="Test", year=2026)
    assert export_league(session, league.id) == SMALL


def test_round_trip_preserves_the_real_league(session):
    """The migration runs once, against data that cannot be regenerated."""
    original = json.loads(REAL_DATA.read_text())
    league = import_league(session, original, name="Movie League 2026", year=2026)
    exported = export_league(session, league.id)

    assert exported["owners"] == original["owners"]
    assert len(exported["movies"]) == len(original["movies"])

    def key(m):
        return (m["owner"], m["round"])

    for before, after in zip(sorted(original["movies"], key=key),
                             sorted(exported["movies"], key=key), strict=True):
        # who_watched is deliberately normalised to league order on export, so repeated
        # exports are byte-stable. Compare membership, not sequence.
        assert set(before.pop("who_watched")) == set(after.pop("who_watched")), \
            f"watchers changed: {before['owner']} R{before['round']}"
        assert before == after, f"row changed: {before['owner']} R{before['round']}"


def test_export_orders_watchers_by_league_order_not_insertion(session):
    """Byte-stable exports: repeated runs must not reshuffle who_watched."""
    data = json.loads(json.dumps(SMALL))
    data["movies"][0]["who_watched"] = ["Bob", "Ann"]     # deliberately reversed
    league = import_league(session, data, name="T", year=2026)
    assert export_league(session, league.id)["movies"][0]["who_watched"] == ["Ann", "Bob"]


def test_export_to_file_writes_atomically(session, tmp_path):
    league = import_league(session, SMALL, name="T", year=2026)
    path = export_to_file(session, league.id, tmp_path / "out.json")
    assert json.loads(path.read_text()) == SMALL
    assert not (tmp_path / "out.json.tmp").exists()      # no temp file left behind


def test_export_rejects_an_unknown_league(session):
    with pytest.raises(ValueError):
        export_league(session, 999)


# ---------------------------------------------------------------------------
# the constraints that application code used to have to get right
# ---------------------------------------------------------------------------

def test_the_same_film_cannot_be_drafted_twice_in_one_league(session):
    from sqlalchemy.exc import IntegrityError
    league = import_league(session, SMALL, name="T", year=2026)
    players = {p.name: p for p in league.players}
    session.add(Entry(league_id=league.id, player_id=players["Ann"].id, round=2,
                      tmdb_id=555, title="Same"))
    session.flush()
    session.add(Entry(league_id=league.id, player_id=players["Bob"].id, round=2,
                      tmdb_id=555, title="Same"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_the_same_film_may_be_drafted_in_a_different_league(session):
    a = import_league(session, SMALL, name="A", year=2026)
    b = import_league(session, SMALL, name="B", year=2027)
    session.add(Entry(league_id=a.id, player_id=a.players[0].id, round=2, tmdb_id=777))
    session.add(Entry(league_id=b.id, player_id=b.players[0].id, round=2, tmdb_id=777))
    session.flush()     # no clash: uniqueness is per league


def test_deleting_a_league_removes_its_rows(session):
    """Relies on PRAGMA foreign_keys=ON; without it SQLite silently orphans rows."""
    league = import_league(session, SMALL, name="T", year=2026)
    session.delete(league)
    session.flush()
    assert session.scalars(select(Entry)).all() == []
    assert session.scalars(select(Player)).all() == []
    assert session.scalars(select(Watch)).all() == []

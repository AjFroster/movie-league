"""Tests for the full-fidelity archive format.

The legacy suite in test_db_porting.py asserts that a legacy `{owners, movies}` document
survives a trip through the database. That is a real guarantee but a narrower one than it
sounds: the legacy shape cannot express pick numbers, poster paths, or any league setting,
so a round trip through it is lossless only because the data was never there to lose.

The test that matters here is the other direction -- database -> JSON -> database -> JSON --
because that is what a restore actually does, and it is the assertion no existing test made.
"""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Entry, League, Player, Watch, STATUS_COMPLETE
from app.db.porting import (ARCHIVE_FORMAT, dump_archive, dump_league, load_archive,
                            load_league)
from app.db.session import create_db_engine
from app.main import app


@pytest.fixture
def session(tmp_path) -> Session:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s


@pytest.fixture
def fresh(tmp_path) -> Session:
    """A second, empty database to restore into."""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'restored.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s


OWNER = "user_owner"


def build_league(session, name="Movie League 2027") -> League:
    """A league exercising every field the legacy format drops."""
    league = League(name=name, year=2027, rounds=2, status=STATUS_COMPLETE,
                    draft_order=["Bob", "Ann"], settles_on=date(2028, 3, 31),
                    pick_seconds=90, owner_user_id=OWNER,
                    frozen_at=datetime(2028, 4, 1, 12, 0, tzinfo=timezone.utc),
                    # Live clock state, deliberately not carried into an archive.
                    clock_started_at=datetime(2027, 6, 1, 9, 0, tzinfo=timezone.utc))
    session.add(league)
    session.flush()

    players = {}
    for who in ("Ann", "Bob"):
        players[who] = Player(league_id=league.id, name=who)
        session.add(players[who])
    session.flush()

    picks = [("Bob", 1, 1, 111, "Alpha", "/alpha.jpg"),
             ("Ann", 1, 2, 222, "Beta", "/beta.jpg"),
             ("Ann", 2, 3, 333, "Gamma", None),
             ("Bob", 2, 4, 444, "Delta", "/delta.jpg")]
    for owner, rnd, pick_no, tmdb, title, poster in picks:
        entry = Entry(league_id=league.id, player_id=players[owner].id, round=rnd,
                      pick_number=pick_no, tmdb_id=tmdb, title=title, poster_path=poster,
                      imdb=7.5, gross=500.0, budget=200.0, roi=2.5, total=24,
                      rating_score=14, financial_score=10, penalty_notes="",
                      sources={"imdb": {"origin": "fetched", "provider": "mdblist"}})
        session.add(entry)
        session.flush()
        session.add(Watch(entry_id=entry.id, player_id=players["Ann"].id,
                          at=datetime(2028, 1, 5, 20, 30, tzinfo=timezone.utc)))
    session.commit()
    return league


# ---------------------------------------------------------------------------
# the round trip
# ---------------------------------------------------------------------------

def test_database_round_trip_is_lossless(session, fresh):
    """dump -> load -> dump produces an identical document.

    This is the guarantee a backup actually needs. If it holds, restoring loses nothing.
    """
    build_league(session)
    before = dump_archive(session)

    load_archive(fresh, before)
    fresh.commit()
    after = dump_archive(fresh)

    assert before["leagues"] == after["leagues"]


def test_round_trip_survives_several_leagues(session, fresh):
    build_league(session, name="Movie League 2027")
    build_league(session, name="Sequels Only 2027")
    before = dump_archive(session)
    assert len(before["leagues"]) == 2

    load_archive(fresh, before)
    fresh.commit()
    assert dump_archive(fresh)["leagues"] == before["leagues"]


def test_pick_numbers_survive(session, fresh):
    """The draft history. The legacy format drops this entirely."""
    build_league(session)
    load_archive(fresh, dump_archive(session))
    fresh.commit()

    entries = dump_archive(fresh)["leagues"][0]["entries"]
    assert sorted(e["pick_number"] for e in entries) == [1, 2, 3, 4]


def test_league_settings_survive(session, fresh):
    build_league(session)
    load_archive(fresh, dump_archive(session))
    fresh.commit()

    restored = dump_archive(fresh)["leagues"][0]
    assert restored["name"] == "Movie League 2027"
    assert restored["year"] == 2027
    assert restored["rounds"] == 2
    assert restored["status"] == STATUS_COMPLETE
    assert restored["draft_order"] == ["Bob", "Ann"]
    assert restored["settles_on"] == "2028-03-31"
    assert restored["pick_seconds"] == 90
    assert restored["frozen_at"].startswith("2028-04-01T12:00:00")


def test_posters_survive(session, fresh):
    build_league(session)
    load_archive(fresh, dump_archive(session))
    fresh.commit()

    posters = {e["title"]: e["poster_path"] for e in dump_archive(fresh)["leagues"][0]["entries"]}
    assert posters == {"Alpha": "/alpha.jpg", "Beta": "/beta.jpg",
                       "Gamma": None, "Delta": "/delta.jpg"}


def test_watches_survive_with_their_timestamps(session, fresh):
    build_league(session)
    load_archive(fresh, dump_archive(session))
    fresh.commit()

    watches = [w for e in dump_archive(fresh)["leagues"][0]["entries"] for w in e["watches"]]
    assert len(watches) == 4
    assert {w["player"] for w in watches} == {"Ann"}
    assert all(w["at"].startswith("2028-01-05T20:30:00") for w in watches)


def test_provenance_survives(session, fresh):
    """`sources` is what stops enrichment overwriting hand-entered values."""
    build_league(session)
    load_archive(fresh, dump_archive(session))
    fresh.commit()

    entry = dump_archive(fresh)["leagues"][0]["entries"][0]
    assert entry["sources"] == {"imdb": {"origin": "fetched", "provider": "mdblist"}}


# ---------------------------------------------------------------------------
# what is deliberately not carried
# ---------------------------------------------------------------------------

def test_database_ids_are_not_carried(session):
    """Primary keys are local to one database; a restore assigns its own."""
    build_league(session)
    doc = dump_archive(session)

    def walk(node):
        if isinstance(node, dict):
            assert "id" not in node, f"database id leaked into the archive: {node!r}"
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)


def test_ownership_and_claims_survive(session, fresh):
    """Accounts are league data. Dropping them hands every claimed slot back to the creator."""
    league = build_league(session)
    league.owner_user_id = "user_creator"
    next(p for p in league.players if p.name == "Ann").user_id = "user_ann"
    session.commit()

    load_archive(fresh, dump_archive(session))
    fresh.commit()

    restored = dump_archive(fresh)["leagues"][0]
    assert restored["owner_user_id"] == "user_creator"
    assert restored["players"] == [{"name": "Ann", "user_id": "user_ann"},
                                   {"name": "Bob", "user_id": None}]


def test_an_archive_with_bare_player_names_still_loads(fresh):
    """The players list held bare strings before slots could be claimed.

    Accepted so a backup taken then is still restorable -- a backup format that stops
    reading its own older files is not a backup format.
    """
    load_archive(fresh, {"format": ARCHIVE_FORMAT, "leagues": [{
        "name": "Old", "year": 2027, "rounds": 1, "status": "setup",
        "draft_order": ["Ann"], "pick_seconds": 60, "players": ["Ann", "Bob"],
        "entries": [],
    }]})
    fresh.commit()
    assert sorted(p.name for p in fresh.query(Player).all()) == ["Ann", "Bob"]
    assert all(p.user_id is None for p in fresh.query(Player).all())


def test_clock_state_is_not_carried(session, fresh):
    """A restored draft starts a fresh clock rather than inheriting a stale deadline."""
    build_league(session)
    assert "clock_started_at" not in dump_archive(session)["leagues"][0]

    load_archive(fresh, dump_archive(session))
    fresh.commit()
    assert fresh.get(League, 1).clock_started_at is None


# ---------------------------------------------------------------------------
# format handling
# ---------------------------------------------------------------------------

def test_load_rejects_an_unknown_format(fresh):
    with pytest.raises(ValueError, match="unrecognised archive format"):
        load_archive(fresh, {"format": "something-else/9", "leagues": []})


def test_load_rejects_a_legacy_document(fresh):
    """The two formats must not be confused: a legacy file has no league settings at all."""
    with pytest.raises(ValueError, match="import_league"):
        load_archive(fresh, {"owners": ["Ann"], "movies": []})


def test_repeated_dumps_are_identical(session):
    """The diffability claim: an unchanged league exports the same bytes every time."""
    build_league(session)
    first, second = dump_archive(session), dump_archive(session)
    assert first["leagues"] == second["leagues"]


def test_load_skips_an_entry_whose_owner_is_not_a_player(fresh):
    """A hand-edited file should lose one row, not invent a player."""
    doc = {"format": ARCHIVE_FORMAT, "leagues": [{
        "name": "T", "year": 2027, "rounds": 1, "status": "setup", "draft_order": ["Ann"],
        "pick_seconds": 60, "players": ["Ann"],
        "entries": [{"owner": "Nobody", "round": 1, "title": "X", "watches": []}],
    }]}
    load_archive(fresh, doc)
    fresh.commit()
    assert fresh.query(Entry).count() == 0
    assert [p.name for p in fresh.query(Player).all()] == ["Ann"]


# ---------------------------------------------------------------------------
# the endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def client(never_touch_the_real_database):
    # Export is scoped to the caller now, so the tests must ask as the league's owner.
    from app import auth
    app.dependency_overrides[auth.current_user] = lambda: OWNER
    app.dependency_overrides[auth.current_user_optional] = lambda: OWNER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_export_endpoint_returns_a_downloadable_archive(client, never_touch_the_real_database):
    with never_touch_the_real_database() as s:
        build_league(s)

    response = client.get("/api/export")
    assert response.status_code == 200
    assert response.json()["format"] == ARCHIVE_FORMAT
    assert len(response.json()["leagues"]) == 1
    assert "attachment" in response.headers["content-disposition"]
    assert "movie-league-backup-" in response.headers["content-disposition"]


def test_league_export_endpoint_names_the_file_after_the_league(client,
                                                                never_touch_the_real_database):
    with never_touch_the_real_database() as s:
        build_league(s)

    response = client.get("/api/leagues/1/export")
    assert response.status_code == 200
    assert response.json()["leagues"][0]["name"] == "Movie League 2027"
    assert "movie-league-2027-" in response.headers["content-disposition"]


def test_league_export_404s_on_an_unknown_league(client):
    assert client.get("/api/leagues/999/export").status_code == 404


def test_a_league_name_cannot_inject_response_headers(client, never_touch_the_real_database):
    """League names are free text and land in Content-Disposition.

    A name carrying a quote or a CRLF would otherwise let a user append their own headers.
    """
    with never_touch_the_real_database() as s:
        build_league(s, name='ev"il\r\nX-Injected: yes')

    response = client.get("/api/leagues/1/export")
    disposition = response.headers["content-disposition"]
    assert "X-Injected" not in disposition
    assert "x-injected" not in {k.lower() for k in response.headers}
    assert '"' not in disposition.split("filename=")[1].strip('"')

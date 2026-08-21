"""End-to-end draft behaviour through the repository layer.

Covers the rules a draft cannot bend -- turn order, one film per league, no picking before
the draft opens or after it closes -- and the concurrency case the JSON store got wrong.
"""
import random
import threading

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import repo
from app.db.models import Base, STATUS_COMPLETE, STATUS_DRAFTING, STATUS_SETUP
from app.db.session import create_db_engine

PLAYERS = ["Ann", "Bob", "Cal"]


@pytest.fixture
def maker(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'draft.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def session(maker):
    with maker() as s:
        yield s


def _league(session, rounds=2, players=PLAYERS):
    league = repo.create_league(session, name="T", year=2026, players=players,
                                rounds=rounds)
    session.commit()
    return league


# ---------------------------------------------------------------------------
# creation
# ---------------------------------------------------------------------------

def test_new_league_starts_in_setup_with_no_order(session):
    league = _league(session)
    assert league.status == STATUS_SETUP
    assert league.draft_order is None       # nothing is decided until the draft opens


@pytest.mark.parametrize("players,rounds", [
    (["Solo"], 6), (["Ann", "ann"], 6), (["Ann", "Bob"], 0), (["Ann", ""], 6),
])
def test_invalid_leagues_are_rejected(session, players, rounds):
    with pytest.raises(ValueError):
        repo.create_league(session, name="T", year=2026, players=players, rounds=rounds)


# ---------------------------------------------------------------------------
# starting
# ---------------------------------------------------------------------------

def test_starting_randomizes_order_and_opens_the_draft(session):
    league = _league(session)
    repo.start_draft(session, league.id, rng=random.Random(3))
    assert league.status == STATUS_DRAFTING
    assert sorted(league.draft_order) == sorted(PLAYERS)


def test_a_draft_cannot_be_started_twice(session):
    """Restarting would reshuffle the order mid-draft and invalidate the picks made."""
    league = _league(session)
    repo.start_draft(session, league.id)
    with pytest.raises(ValueError, match="cannot start"):
        repo.start_draft(session, league.id)


def test_picking_before_the_draft_opens_is_rejected(session):
    league = _league(session)
    with pytest.raises(ValueError, match="not drafting"):
        repo.make_pick(session, league.id, player="Ann", tmdb_id=1, title="X")


# ---------------------------------------------------------------------------
# picking
# ---------------------------------------------------------------------------

def _run_full_draft(session, league):
    repo.start_draft(session, league.id, rng=random.Random(1))
    state = repo.draft_state(session, league.id)
    picked = []
    while state["on_the_clock"]:
        clock = state["on_the_clock"]
        movie_id = 100 + len(picked)
        state = repo.make_pick(session, league.id, player=clock["player"],
                               tmdb_id=movie_id, title=f"Film {movie_id}")
        picked.append((clock["player"], movie_id))
    return picked


def test_a_full_draft_fills_every_slot_and_completes(session):
    league = _league(session, rounds=2)
    picked = _run_full_draft(session, league)
    assert len(picked) == 6                       # 3 players x 2 rounds
    assert league.status == STATUS_COMPLETE
    counts = {p: sum(1 for who, _ in picked if who == p) for p in PLAYERS}
    assert set(counts.values()) == {2}            # everyone got the same number


def test_the_draft_snakes(session):
    league = _league(session, rounds=2)
    picked = _run_full_draft(session, league)
    order = league.draft_order
    assert [p for p, _ in picked[:3]] == order
    assert [p for p, _ in picked[3:]] == list(reversed(order))


def test_picking_out_of_turn_is_rejected(session):
    league = _league(session)
    repo.start_draft(session, league.id, rng=random.Random(1))
    not_up = [p for p in PLAYERS if p != league.draft_order[0]][0]
    with pytest.raises(ValueError, match="pick"):
        repo.make_pick(session, league.id, player=not_up, tmdb_id=1, title="X")


def test_the_same_film_cannot_be_taken_twice(session):
    league = _league(session)
    repo.start_draft(session, league.id, rng=random.Random(1))
    first = league.draft_order[0]
    repo.make_pick(session, league.id, player=first, tmdb_id=42, title="Dune")
    second = league.draft_order[1]
    with pytest.raises(ValueError, match="already been drafted"):
        repo.make_pick(session, league.id, player=second, tmdb_id=42, title="Dune")


def test_picking_after_the_draft_completes_is_rejected(session):
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    with pytest.raises(ValueError, match="not drafting"):
        repo.make_pick(session, league.id, player=PLAYERS[0], tmdb_id=999, title="Late")


def test_an_unknown_player_cannot_pick(session):
    league = _league(session)
    repo.start_draft(session, league.id)
    with pytest.raises(ValueError, match="no player"):
        repo.make_pick(session, league.id, player="Intruder", tmdb_id=1, title="X")


def test_state_is_derived_from_picks_not_a_stored_cursor(session):
    """draft_state must agree with the pick list even if nothing tracks position."""
    league = _league(session, rounds=2)
    repo.start_draft(session, league.id, rng=random.Random(5))
    state = repo.draft_state(session, league.id)
    assert state["picks_made"] == 0 and state["on_the_clock"]["pick"] == 1
    repo.make_pick(session, league.id, player=state["on_the_clock"]["player"],
                   tmdb_id=7, title="Seven")
    state = repo.draft_state(session, league.id)
    assert state["picks_made"] == 1 and state["on_the_clock"]["pick"] == 2
    assert state["drafted_ids"] == [7]


# ---------------------------------------------------------------------------
# the concurrency the JSON store could not handle
# ---------------------------------------------------------------------------

def test_simultaneous_watch_toggles_do_not_overwrite_each_other(maker, tmp_path):
    """The JSON store lost 3 of 4 here, because each write rewrote the file wholesale."""
    with maker() as setup:
        league = repo.create_league(setup, name="T", year=2026, players=PLAYERS, rounds=1)
        repo.start_draft(setup, league.id, rng=random.Random(1))
        first = league.draft_order[0]
        repo.make_pick(setup, league.id, player=first, tmdb_id=1, title="Film")
        setup.commit()
        league_id, owner = league.id, first

    def toggle(viewer):
        with maker() as s:
            repo.set_watched(s, league_id, owner=owner, round_number=1,
                             viewer=viewer, watched=True)
            s.commit()

    threads = [threading.Thread(target=toggle, args=(p,)) for p in PLAYERS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with maker() as s:
        row = repo.owner_movies(s, league_id, owner)[0]
        assert sorted(row["who_watched"]) == sorted(PLAYERS)


def test_watch_points_follow_the_viewer_through_the_repo(maker):
    with maker() as s:
        league = repo.create_league(s, name="T", year=2026, players=PLAYERS, rounds=1)
        repo.start_draft(s, league.id, rng=random.Random(1))
        owner = league.draft_order[0]
        other = league.draft_order[1]
        repo.make_pick(s, league.id, player=owner, tmdb_id=1, title="Film")
        repo.set_watched(s, league.id, owner=owner, round_number=1,
                         viewer=other, watched=True)
        s.commit()
        board = {r["owner"]: r for r in repo.leaderboard(s, league.id)}
        assert board[other]["other_watch_points"] == 1
        assert board[other]["total"] == 1
        assert board[owner]["watch_points"] == 0        # the owner did not watch it

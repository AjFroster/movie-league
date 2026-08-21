"""End-to-end draft behaviour through the repository layer.

Covers the rules a draft cannot bend -- turn order, one film per league, no picking before
the draft opens or after it closes -- and the concurrency case the JSON store got wrong.
"""
import random
import threading
from datetime import date

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


def test_a_pick_keeps_the_artwork_the_pool_supplied(session):
    """Drafting knows the poster; discarding it left new leagues with no images at all
    until someone thought to run enrichment."""
    league = _league(session)
    repo.start_draft(session, league.id, rng=random.Random(1))
    first = league.draft_order[0]
    repo.make_pick(session, league.id, player=first, tmdb_id=42, title="Dune",
                   poster_path="/abc.jpg")
    row = repo.owner_movies(session, league.id, first)[0]
    assert row["poster_path"] == "/abc.jpg"
    assert row["poster_url"].endswith("/abc.jpg")


def test_a_pick_without_artwork_stores_none_not_an_empty_string(session):
    """Many future films have no poster; None is what the client tests for."""
    league = _league(session)
    repo.start_draft(session, league.id, rng=random.Random(1))
    first = league.draft_order[0]
    repo.make_pick(session, league.id, player=first, tmdb_id=43, title="Untitled",
                   poster_path="")
    row = repo.owner_movies(session, league.id, first)[0]
    assert row["poster_path"] is None and row["poster_url"] is None


# ---------------------------------------------------------------------------
# renaming and deleting
# ---------------------------------------------------------------------------

def test_a_league_can_be_renamed(session):
    league = _league(session)
    repo.rename_league(session, league.id, name="  Renamed Season  ")
    assert league.name == "Renamed Season"          # trimmed


@pytest.mark.parametrize("name", ["", "   ", None])
def test_a_league_cannot_be_renamed_to_nothing(session, name):
    league = _league(session)
    with pytest.raises(ValueError):
        repo.rename_league(session, league.id, name=name)


def test_renaming_a_drafted_league_keeps_its_picks(session):
    """A rename is cosmetic; nothing about the season may move."""
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    before = [(m["owner"], m["round"], m["movie"]) for m in
              repo.league_movies(session, league.id)]
    repo.rename_league(session, league.id, name="New Name")
    assert [(m["owner"], m["round"], m["movie"]) for m in
            repo.league_movies(session, league.id)] == before


def test_deleting_a_league_removes_its_entries_and_watches(session):
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    other = repo.create_league(session, name="Survivor", year=2027,
                               players=PLAYERS, rounds=1)
    session.flush()
    repo.delete_league(session, league.id)
    assert repo.league_movies(session, other.id) == []      # untouched, still exists
    with pytest.raises(LookupError):
        repo.draft_state(session, league.id)


def test_deleting_an_unknown_league_raises(session):
    with pytest.raises(LookupError):
        repo.delete_league(session, 9999)


# ---------------------------------------------------------------------------
# freezing a settled season
# ---------------------------------------------------------------------------

def test_freezing_stops_enrichment_from_rewriting_scores(session):
    """The whole point: a settled season's numbers must stop moving."""
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    documents, index = repo.entries_as_documents(session, league.id)
    repo.freeze_league(session, league.id)
    with pytest.raises(ValueError, match="frozen"):
        repo.apply_documents(session, league.id, documents, index)


def test_a_refusal_rather_than_a_silent_skip(session):
    """A caller must not be able to believe it refreshed a season that did not move."""
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    documents, index = repo.entries_as_documents(session, league.id)
    repo.freeze_league(session, league.id)
    try:
        repo.apply_documents(session, league.id, documents, index)
        raise AssertionError("expected a refusal")
    except ValueError as e:
        assert league.name in str(e)      # says which league, not just "frozen"


def test_unfreezing_lets_a_season_finish_counting(session):
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    repo.freeze_league(session, league.id)
    repo.freeze_league(session, league.id, frozen=False)
    assert league.frozen_at is None
    documents, index = repo.entries_as_documents(session, league.id)
    repo.apply_documents(session, league.id, documents, index)   # no longer raises


def test_freezing_does_not_alter_any_score(session):
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    before = [(m["owner"], m["total"]) for m in repo.league_movies(session, league.id)]
    repo.freeze_league(session, league.id)
    assert [(m["owner"], m["total"]) for m in
            repo.league_movies(session, league.id)] == before


def test_freezing_one_league_leaves_others_refreshable(session):
    frozen = _league(session, rounds=1)
    _run_full_draft(session, frozen)
    repo.freeze_league(session, frozen.id)

    live = repo.create_league(session, name="Live", year=2027, players=PLAYERS, rounds=1)
    session.flush()
    documents, index = repo.entries_as_documents(session, live.id)
    repo.apply_documents(session, live.id, documents, index)      # unaffected


# ---------------------------------------------------------------------------
# when a season's books close
# ---------------------------------------------------------------------------

def test_a_league_defaults_to_settling_at_the_end_of_its_year(session):
    league = repo.create_league(session, name="T", year=2026, players=PLAYERS, rounds=1)
    assert league.settles_on == date(2026, 12, 31)


def test_a_league_can_settle_on_its_own_date(session):
    """A roster whose last film opens at Christmas needs longer than the calendar year."""
    league = repo.create_league(session, name="T", year=2026, players=PLAYERS, rounds=1,
                                settles_on=date(2027, 3, 31))
    assert league.settles_on == date(2027, 3, 31)


def test_the_settle_date_can_be_changed_after_the_draft(session):
    """The roster decides the right date, and the roster is not known until drafting ends."""
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    repo.set_settles_on(session, league.id, on=date(2027, 3, 31))
    assert league.settles_on == date(2027, 3, 31)


def test_a_season_cannot_settle_before_it_starts(session):
    league = repo.create_league(session, name="T", year=2026, players=PLAYERS, rounds=1)
    with pytest.raises(ValueError, match="before it starts"):
        repo.set_settles_on(session, league.id, on=date(2025, 6, 1))


def test_changing_the_settle_date_moves_nothing_else(session):
    league = _league(session, rounds=1)
    _run_full_draft(session, league)
    before = [(m["owner"], m["total"]) for m in repo.league_movies(session, league.id)]
    repo.set_settles_on(session, league.id, on=date(2027, 3, 31))
    assert [(m["owner"], m["total"]) for m in
            repo.league_movies(session, league.id)] == before

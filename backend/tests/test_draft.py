"""Tests for snake draft ordering and pick validation.

The property worth protecting is fairness: over an even number of rounds every player's
pick positions must sum to the same number, which is the entire reason a draft snakes.
"""
import random

import pytest

from app import draft

FOUR = ["Ann", "Bob", "Cal", "Dee"]


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------

def test_odd_rounds_run_forward_and_even_rounds_run_backward():
    assert draft.round_order(FOUR, 1) == ["Ann", "Bob", "Cal", "Dee"]
    assert draft.round_order(FOUR, 2) == ["Dee", "Cal", "Bob", "Ann"]
    assert draft.round_order(FOUR, 3) == ["Ann", "Bob", "Cal", "Dee"]


def test_pick_sequence_numbers_every_pick_once_in_order():
    sequence = draft.pick_sequence(FOUR, 3)
    assert len(sequence) == 12
    assert [s["pick"] for s in sequence] == list(range(1, 13))
    assert sequence[0] == {"pick": 1, "round": 1, "slot": 1, "player": "Ann"}
    assert sequence[4] == {"pick": 5, "round": 2, "slot": 1, "player": "Dee"}
    assert sequence[8] == {"pick": 9, "round": 3, "slot": 1, "player": "Ann"}


def test_everyone_picks_the_same_number_of_times():
    sequence = draft.pick_sequence(FOUR, 5)
    counts = {p: sum(1 for s in sequence if s["player"] == p) for p in FOUR}
    assert set(counts.values()) == {5}


@pytest.mark.parametrize("players,rounds", [(4, 6), (3, 4), (5, 2), (8, 10)])
def test_snake_is_fair_over_an_even_number_of_rounds(players, rounds):
    """The fairness guarantee: equal sum of pick numbers, so no seat is advantaged."""
    names = [f"P{i}" for i in range(players)]
    sequence = draft.pick_sequence(names, rounds)
    totals = {n: sum(s["pick"] for s in sequence if s["player"] == n) for n in names}
    assert len(set(totals.values())) == 1, totals


def test_odd_rounds_advantage_the_first_seat_as_expected():
    """With an odd round count the snake cannot balance -- worth pinning, not a bug."""
    sequence = draft.pick_sequence(FOUR, 3)
    totals = {n: sum(s["pick"] for s in sequence if s["player"] == n) for n in FOUR}
    assert totals["Ann"] < totals["Dee"]


# ---------------------------------------------------------------------------
# randomisation
# ---------------------------------------------------------------------------

def test_randomize_order_is_a_permutation():
    assert sorted(draft.randomize_order(FOUR)) == sorted(FOUR)


def test_randomize_order_is_deterministic_under_a_seeded_rng():
    a = draft.randomize_order(FOUR, rng=random.Random(7))
    b = draft.randomize_order(FOUR, rng=random.Random(7))
    assert a == b


def test_randomize_order_does_not_mutate_the_input():
    original = list(FOUR)
    draft.randomize_order(FOUR, rng=random.Random(1))
    assert FOUR == original


def test_randomize_order_actually_shuffles_over_many_runs():
    """A shuffle that always returns input order would pass every test above."""
    seen = {tuple(draft.randomize_order(FOUR, rng=random.Random(s))) for s in range(50)}
    assert len(seen) > 1


# ---------------------------------------------------------------------------
# on the clock
# ---------------------------------------------------------------------------

def test_on_the_clock_walks_the_snake():
    assert draft.on_the_clock(FOUR, 2, 0)["player"] == "Ann"
    assert draft.on_the_clock(FOUR, 2, 3)["player"] == "Dee"
    assert draft.on_the_clock(FOUR, 2, 4)["player"] == "Dee"   # round 2 turns
    assert draft.on_the_clock(FOUR, 2, 7)["player"] == "Ann"


def test_on_the_clock_is_none_once_every_pick_is_made():
    assert draft.on_the_clock(FOUR, 2, 8) is None
    assert draft.on_the_clock(FOUR, 2, 99) is None


# ---------------------------------------------------------------------------
# setup validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("players,rounds,reason", [
    (["Solo"], 6, "too few players"),
    ([f"P{i}" for i in range(21)], 6, "too many players"),
    (["Ann", "Ann"], 6, "duplicate names"),
    (["Ann", "ann"], 6, "duplicates differing only by case"),
    (["Ann", "  "], 6, "blank name"),
    (["Ann", "Bob"], 0, "no rounds"),
    (["Ann", "Bob"], 31, "too many rounds"),
])
def test_invalid_setups_are_rejected(players, rounds, reason):
    with pytest.raises(ValueError):
        draft.validate_setup(players, rounds)


def test_a_sane_setup_passes():
    draft.validate_setup(FOUR, 6)


# ---------------------------------------------------------------------------
# pick validation
# ---------------------------------------------------------------------------

def _picks(*pairs):
    return [{"player": p, "movie_id": m} for p, m in pairs]


def test_pick_out_of_turn_is_rejected():
    with pytest.raises(ValueError, match="Ann's pick"):
        draft.validate_pick(order=FOUR, rounds=2, picks=[], player="Bob", movie_id=1)


def test_picking_an_already_drafted_film_is_rejected():
    with pytest.raises(ValueError, match="already been drafted"):
        draft.validate_pick(order=FOUR, rounds=2, picks=_picks(("Ann", 10)),
                            player="Bob", movie_id=10)


def test_duplicate_check_survives_id_type_mismatch():
    """A film picked as 10 must not be re-pickable as "10" from a JSON body."""
    with pytest.raises(ValueError, match="already been drafted"):
        draft.validate_pick(order=FOUR, rounds=2, picks=_picks(("Ann", 10)),
                            player="Bob", movie_id="10")


def test_picking_after_the_draft_ends_is_rejected():
    full = draft.pick_sequence(FOUR, 1)
    picks = _picks(*[(s["player"], i) for i, s in enumerate(full)])
    with pytest.raises(ValueError, match="already complete"):
        draft.validate_pick(order=FOUR, rounds=1, picks=picks, player="Ann", movie_id=99)


def test_a_valid_pick_returns_the_slot_it_fills():
    slot = draft.validate_pick(order=FOUR, rounds=2, picks=_picks(("Ann", 1)),
                               player="Bob", movie_id=2)
    assert slot == {"pick": 2, "round": 1, "slot": 2, "player": "Bob"}

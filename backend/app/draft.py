"""Snake draft order and pick validation. Pure logic -- no I/O, no persistence.

A snake draft reverses direction every round, so the player who picks last in round 1 picks
first in round 2. That is what keeps an early pick from compounding: over an even number of
rounds every player's pick positions sum to the same number.

Everything here is a function of (order, rounds, picks_made), so the draft state can always
be recomputed from the stored pick list rather than trusted from a stored cursor -- a cursor
and a list can disagree, and then the draft is wrong in a way nobody notices until later.
"""
import random

MIN_PLAYERS = 2
MAX_PLAYERS = 20
MIN_ROUNDS = 1
MAX_ROUNDS = 30


def randomize_order(players: list[str], *, rng: random.Random | None = None) -> list[str]:
    """Shuffle draft order. `rng` is injectable so tests can pin the outcome."""
    shuffled = list(players)
    (rng or random).shuffle(shuffled)
    return shuffled


def round_order(order: list[str], round_number: int) -> list[str]:
    """Pick order for one round, 1-indexed. Even rounds run backwards."""
    return list(order) if round_number % 2 == 1 else list(reversed(order))


def pick_sequence(order: list[str], rounds: int) -> list[dict]:
    """Every pick in the draft, in order: [{pick, round, slot, player}, ...].

    `pick` is the overall pick number (1-indexed) and `slot` is the position within its
    round, so a board can render "Round 2, pick 3" without recomputing the snake.
    """
    sequence = []
    number = 0
    for round_number in range(1, rounds + 1):
        for slot, player in enumerate(round_order(order, round_number), start=1):
            number += 1
            sequence.append({"pick": number, "round": round_number,
                             "slot": slot, "player": player})
    return sequence


def total_picks(players: int, rounds: int) -> int:
    return players * rounds


def on_the_clock(order: list[str], rounds: int, picks_made: int) -> dict | None:
    """The pick that happens next, or None when the draft is complete.

    Derived from how many picks exist rather than from a stored pointer, so the answer
    cannot drift out of sync with the pick list.
    """
    sequence = pick_sequence(order, rounds)
    if picks_made >= len(sequence):
        return None
    return sequence[picks_made]


def validate_setup(players: list[str], rounds: int) -> None:
    """Raise ValueError if a league could not run a sane draft."""
    if len(players) < MIN_PLAYERS:
        raise ValueError(f"a draft needs at least {MIN_PLAYERS} players")
    if len(players) > MAX_PLAYERS:
        raise ValueError(f"a draft supports at most {MAX_PLAYERS} players")
    stripped = [p.strip() for p in players]
    if any(not p for p in stripped):
        raise ValueError("player names cannot be blank")
    lowered = [p.lower() for p in stripped]
    if len(set(lowered)) != len(lowered):
        raise ValueError("player names must be unique")
    if not (MIN_ROUNDS <= rounds <= MAX_ROUNDS):
        raise ValueError(f"rounds must be between {MIN_ROUNDS} and {MAX_ROUNDS}")


def validate_pick(*, order: list[str], rounds: int, picks: list[dict],
                  player: str, movie_id) -> dict:
    """Check a proposed pick and return the slot it fills.

    Enforces the two rules a draft cannot bend: you may only pick when you are on the
    clock, and a film already taken is gone. Both are checked against the pick list itself,
    so a replayed or out-of-order request cannot slip through.
    """
    slot = on_the_clock(order, rounds, len(picks))
    if slot is None:
        raise ValueError("the draft is already complete")
    if player != slot["player"]:
        raise ValueError(f"it is {slot['player']}'s pick, not {player}'s")
    if any(str(p.get("movie_id")) == str(movie_id) for p in picks):
        raise ValueError("that film has already been drafted")
    return slot

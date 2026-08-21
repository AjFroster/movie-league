"""Tests for the league scoring formula.

The headline test is `test_formula_reproduces_the_hand_scored_rows`, which runs the formula
against the real league_data.json and asserts it reproduces every hand-entered score. That
is the only real evidence the transcription is faithful; unit tests below only pin the
individual tiers.
"""
import json
from pathlib import Path

import pytest

from app import scoring

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "league_data.json"

# Confirmed by the user as scored before budget/gross were corrected, not formula gaps.
# Mark R4 stores 5 -- exactly the gross tier with no ROI points -- against a current ROI of
# 27.7; Mark R3 stores 12 with no financials recorded at all.
KNOWN_STALE_FINANCIAL = {("Mark", 3), ("Mark", 4)}


def _entry(**fields):
    base = {"owner": "A", "who_watched": [], "imdb": None, "letterboxd": None,
            "rt_crit": None, "rt_aud": None, "budget": None, "gross": None, "roi": None}
    base.update(fields)
    return base


# ---------------------------------------------------------------------------
# rating_score
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("imdb,expected", [
    (None, 0), (7.4, 0), (7.5, 4), (7.9, 4), (8.0, 7), (8.4, 7), (8.5, 12), (10.0, 12),
])
def test_imdb_tiers(imdb, expected):
    assert scoring.rating_score(_entry(imdb=imdb)) == expected


@pytest.mark.parametrize("lb,expected", [
    (3.4, 0), (3.5, 4), (4.0, 7), (4.5, 12), (5.0, 12),
])
def test_letterboxd_tiers(lb, expected):
    assert scoring.rating_score(_entry(letterboxd=lb)) == expected


@pytest.mark.parametrize("rt,expected", [(74, 0), (75, 4), (85, 7), (95, 12), (100, 12)])
def test_rt_tiers_apply_to_both_critic_and_audience(rt, expected):
    assert scoring.rating_score(_entry(rt_crit=rt)) == expected
    assert scoring.rating_score(_entry(rt_aud=rt)) == expected


def test_rating_sources_stack():
    """All four sources contribute independently -- the real 38-point row."""
    assert scoring.rating_score(
        _entry(imdb=8.0, letterboxd=4.3, rt_crit=98, rt_aud=95)) == 7 + 7 + 12 + 12


# ---------------------------------------------------------------------------
# financial_score
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gross,expected", [
    (None, 0), (49, 0), (50, 1), (100, 3), (250, 5), (500, 7), (1000, 9), (2500, 9),
])
def test_gross_tiers(gross, expected):
    assert scoring.financial_score(_entry(gross=gross)) == expected


@pytest.mark.parametrize("roi,expected", [
    (None, 0), (1.9, 0), (2, 3), (3, 5), (5, 8), (10, 12), (27.7, 12),
])
def test_roi_tiers(roi, expected):
    assert scoring.financial_score(_entry(roi=roi)) == expected


def test_gross_and_roi_stack():
    """The real 17-point row: $1007M gross (9) plus 9.155x return (8)."""
    assert scoring.financial_score(_entry(gross=1007, roi=9.155)) == 17


# ---------------------------------------------------------------------------
# penalties
# ---------------------------------------------------------------------------

def test_recoup_penalties_stack_to_25():
    points, notes = scoring.penalties(_entry(roi=0.466))
    assert points == -25
    assert notes == "Didnt recoup budget (-10), Didnt recoup 75% of budget (-15)"


def test_roi_between_75_percent_and_break_even_takes_only_the_first_penalty():
    points, notes = scoring.penalties(_entry(roi=0.9))
    assert (points, notes) == (-10, "Didnt recoup budget (-10)")


def test_missing_roi_is_not_a_failure_to_recoup():
    """An unmeasured film has not flopped -- it simply has no financials yet."""
    assert scoring.penalties(_entry(roi=None)) == (0, "")


def test_rating_penalties_combine():
    points, notes = scoring.penalties(_entry(letterboxd=2.3, rt_crit=31))
    assert points == -20
    assert notes == "Letterboxd < 2.5 (-10), RT Critics < 50% (-10)"


# ---------------------------------------------------------------------------
# watch_points
# ---------------------------------------------------------------------------

def test_watch_points_require_the_owner_not_just_any_viewer():
    assert scoring.watch_points(_entry(owner="A", who_watched=["A"])) == 5
    assert scoring.watch_points(_entry(owner="A", who_watched=["A", "B", "C"])) == 5
    assert scoring.watch_points(_entry(owner="A", who_watched=["B", "C", "D"])) == 0
    assert scoring.watch_points(_entry(owner="A", who_watched=[])) == 0


# ---------------------------------------------------------------------------
# compute_movie_scores
# ---------------------------------------------------------------------------

def test_total_is_the_sum_of_the_four_components():
    entry = scoring.compute_movie_scores(
        _entry(owner="A", who_watched=["A"], imdb=8.0, rt_crit=40, gross=300, roi=0.5))
    assert entry["total"] == (entry["rating_score"] + entry["financial_score"]
                              + entry["penalties"] + entry["watch_points"])


def test_compute_regenerates_penalty_notes_rather_than_trusting_stored_text():
    entry = _entry(roi=5.0, penalty_notes="Didnt recoup budget (-10)")
    scoring.compute_movie_scores(entry)
    assert entry["penalties"] == 0
    assert entry["penalty_notes"] == ""


# ---------------------------------------------------------------------------
# the real dataset -- the actual proof the transcription is right
# ---------------------------------------------------------------------------

def test_formula_reproduces_the_hand_scored_rows():
    """Every hand-entered score must fall out of the formula, bar two known-stale rows."""
    data = json.loads(DATA_PATH.read_text())
    rating_misses, financial_misses, penalty_misses, watch_misses = [], [], [], []

    for m in data["movies"]:
        key = (m["owner"], m["round"])
        if scoring.rating_score(m) != m["rating_score"]:
            rating_misses.append(key)
        if scoring.financial_score(m) != m["financial_score"] and key not in KNOWN_STALE_FINANCIAL:
            financial_misses.append(key)
        if scoring.penalties(m)[0] != m["penalties"]:
            penalty_misses.append(key)
        if scoring.watch_points(m) != m["watch_points"]:
            watch_misses.append(key)

    assert rating_misses == [], f"rating_score diverged on {rating_misses}"
    assert financial_misses == [], f"financial_score diverged on {financial_misses}"
    assert penalty_misses == [], f"penalties diverged on {penalty_misses}"
    assert watch_misses == [], f"watch_points diverged on {watch_misses}"


def test_the_two_known_stale_rows_are_still_stale():
    """If a future data fix makes these agree, delete them from KNOWN_STALE_FINANCIAL.

    Guards against the exemption silently masking a real regression later.
    """
    data = json.loads(DATA_PATH.read_text())
    by_key = {(m["owner"], m["round"]): m for m in data["movies"]}
    for key in KNOWN_STALE_FINANCIAL:
        m = by_key[key]
        assert scoring.financial_score(m) != m["financial_score"], (
            f"{key} now agrees with the formula -- remove it from KNOWN_STALE_FINANCIAL")


# ---------------------------------------------------------------------------
# score_breakdown -- the per-row explanation rendered in the detail panel
# ---------------------------------------------------------------------------

def test_breakdown_points_sum_to_the_stored_total():
    """The table must reconcile: if it does not, the UI is lying about the arithmetic."""
    entry = _entry(owner="A", who_watched=["A"], imdb=8.5, letterboxd=4.6,
                   rt_crit=96, rt_aud=80, gross=1200.0, roi=6.0)
    scoring.compute_movie_scores(entry)
    assert sum(r["points"] for r in scoring.score_breakdown(entry)) == entry["total"]


def test_breakdown_covers_every_scoring_input():
    rows = scoring.score_breakdown(_entry())
    labels = [r["label"] for r in rows]
    assert labels == ["IMDb", "Letterboxd", "RT Critics", "RT Audience",
                      "Worldwide gross", "Return on budget", "Penalties", "Owner watched"]


def test_breakdown_distinguishes_missing_data_from_a_zero_score():
    """"no data" and "below the lowest tier" both score 0 but mean different things."""
    rows = {r["label"]: r for r in scoring.score_breakdown(_entry(imdb=None, rt_crit=10))}
    assert rows["IMDb"]["value"] == "—" and rows["IMDb"]["tier"] == "no data"
    assert rows["RT Critics"]["value"] == "10%" and rows["RT Critics"]["tier"] == "< 75%"


def test_breakdown_reconciles_across_the_whole_real_dataset():
    data = json.loads(DATA_PATH.read_text())
    for m in data["movies"]:
        scored = dict(m)
        scoring.compute_movie_scores(scored)
        assert sum(r["points"] for r in scoring.score_breakdown(scored)) == scored["total"], \
            f"breakdown does not reconcile for {m['owner']} R{m['round']}"


# ---------------------------------------------------------------------------
# watch points follow the watcher, not the owner
# ---------------------------------------------------------------------------

def _league(*rows):
    return [{"owner": o, "round": r, "who_watched": list(w)} for o, r, w in rows]


def test_viewer_earns_five_for_their_own_pick_and_one_for_others():
    movies = _league(("A", 1, ["A", "B"]), ("B", 1, ["A", "B"]))
    assert scoring.viewer_watch_points(movies, "A") == 5 + 1
    assert scoring.viewer_watch_points(movies, "B") == 1 + 5


def test_watching_nothing_earns_nothing():
    assert scoring.viewer_watch_points(_league(("A", 1, ["B"])), "A") == 0


def test_a_completionist_earns_own_picks_plus_everything_else():
    """Six own picks and 24 others is the full-season ceiling: 6*5 + 24*1 = 54."""
    movies = _league(*[("A", r, ["A"]) for r in range(1, 7)],
                     *[("B", r, ["A"]) for r in range(1, 25)])
    assert scoring.viewer_watch_points(movies, "A") == 6 * 5 + 24 * 1


def test_row_watch_points_stay_owner_only():
    """The row's own component must exclude other viewers, or the league double-counts."""
    assert scoring.watch_points({"owner": "A", "who_watched": ["A", "B", "C"]}) == 5
    assert scoring.watch_points({"owner": "A", "who_watched": ["B", "C"]}) == 0


def test_leaderboard_attributes_cross_owner_watches_to_the_watcher():
    """B watching A's pick must move B's total, not A's."""
    from app import storage
    data = {"owners": ["A", "B"], "movies": [
        {"owner": "A", "round": 1, "movie": "x", "imdb": None, "who_watched": ["A", "B"],
         "rating_score": 0, "financial_score": 0, "penalties": 0, "watch_points": 5,
         "total": 5},
        {"owner": "B", "round": 1, "movie": "y", "imdb": None, "who_watched": [],
         "rating_score": 0, "financial_score": 0, "penalties": 0, "watch_points": 0,
         "total": 0},
    ]}
    board = {r["owner"]: r for r in storage.compute_leaderboard(data)}
    assert board["A"]["total"] == 5          # own pick, own watch
    assert board["A"]["own_watch_points"] == 5
    assert board["B"]["total"] == 1          # earned purely by watching A's film
    assert board["B"]["other_watch_points"] == 1


def test_leaderboard_does_not_double_count_the_owners_own_watch():
    from app import storage
    data = {"owners": ["A"], "movies": [
        {"owner": "A", "round": 1, "movie": "x", "imdb": None, "who_watched": ["A"],
         "rating_score": 10, "financial_score": 0, "penalties": 0, "watch_points": 5,
         "total": 15},
    ]}
    board = storage.compute_leaderboard(data)[0]
    assert board["total"] == 15 and board["watch_points"] == 5

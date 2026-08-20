"""The league scoring formula.

Transcribed from the commissioner's spreadsheet and validated against the 16 hand-scored
rows in league_data.json: rating_score reproduces 16/16 exactly, financial_score 14/16.
The two financial misses (Mark R3, Mark R4) were confirmed by the user as stale entries --
scored before budget/gross were corrected -- not gaps in the rules.

Every score here is a pure function of the fields enrichment fills (imdb, letterboxd,
rt_crit, rt_aud, budget, gross, roi) plus who_watched. Nothing here calls a provider or
touches the network; scoring runs on data that is already in the entry.
"""

# Each source contributes independently; a film clearing several thresholds banks all of
# them. Tiers are ordered high-to-low so the first match is the best one.
RATING_TIERS: dict[str, list[tuple[float, int]]] = {
    "imdb":       [(8.5, 12), (8.0, 7), (7.5, 4)],
    "letterboxd": [(4.5, 12), (4.0, 7), (3.5, 4)],
    "rt_crit":    [(95, 12), (85, 7), (75, 4)],
    "rt_aud":     [(95, 12), (85, 7), (75, 4)],
}

# Worldwide gross in millions, and return on budget. A film scores on both axes: a cheap
# film that earns a lot banks the gross tier AND the ROI tier.
GROSS_TIERS: list[tuple[float, int]] = [(1000, 9), (500, 7), (250, 5), (100, 3), (50, 1)]
ROI_TIERS: list[tuple[float, int]] = [(10, 12), (5, 8), (3, 5), (2, 3)]

# (field, threshold, points, note). Penalties stack: a film that fails to recoup 75% of its
# budget takes both recoup penalties, which is how -25 arises.
PENALTY_RULES: list[tuple[str, float, int, str]] = [
    ("roi", 1.0, -10, "Didnt recoup budget (-10)"),
    ("roi", 0.75, -15, "Didnt recoup 75% of budget (-15)"),
    ("letterboxd", 2.5, -10, "Letterboxd < 2.5 (-10)"),
    ("rt_crit", 50, -10, "RT Critics < 50% (-10)"),
]

WATCH_POINTS = 5


def _tier(value, tiers: list[tuple[float, int]]) -> int:
    """Points for the highest threshold `value` clears. Missing data scores nothing."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    for threshold, points in tiers:
        if value >= threshold:
            return points
    return 0


def rating_score(entry: dict) -> int:
    """Sum of the four rating sources' tiers."""
    return sum(_tier(entry.get(field), tiers) for field, tiers in RATING_TIERS.items())


def financial_score(entry: dict) -> int:
    """Gross tier plus ROI tier."""
    return _tier(entry.get("gross"), GROSS_TIERS) + _tier(entry.get("roi"), ROI_TIERS)


def penalties(entry: dict) -> tuple[int, str]:
    """Total penalty points and the matching notes, in the order the rules are declared.

    A threshold only fires when the underlying value exists: a film with no ROI recorded
    has not "failed to recoup", it simply has not been measured yet.
    """
    total = 0
    notes: list[str] = []
    for field, threshold, points, note in PENALTY_RULES:
        value = entry.get(field)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value < threshold:
            total += points
            notes.append(note)
    return total, ", ".join(notes)


def watch_points(entry: dict) -> int:
    """Points for the owner having watched their own pick.

    Flat, not per-viewer: the one row where three people watched but the owner did not
    scores zero, and the row watched by only the owner scores full marks.
    """
    watched = entry.get("who_watched") or []
    return WATCH_POINTS if entry.get("owner") in watched else 0


def compute_movie_scores(entry: dict) -> dict:
    """Recompute every score on `entry` in place and return it.

    Scores are always derived -- never provenance-protected like the rating and financial
    inputs are. A stored score is a cached calculation, not a human's data entry, so it is
    safe to overwrite; the inputs it is computed from are what provenance guards.
    """
    entry["rating_score"] = rating_score(entry)
    entry["financial_score"] = financial_score(entry)
    entry["penalties"], entry["penalty_notes"] = penalties(entry)
    entry["watch_points"] = watch_points(entry)
    entry["total"] = (entry["rating_score"] + entry["financial_score"]
                      + entry["penalties"] + entry["watch_points"])
    return entry

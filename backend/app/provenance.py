"""Per-field provenance for movie rows, and the no-clobber rule.

RESEARCH section 4: `main.py::enrich_movie` overwrites imdb/budget/gross unconditionally,
16 of 30 rows carry hand-entered ratings, and nothing distinguishes a human's number from a
machine's. This module is that distinction.

Three origins, and the difference between the last two is the entire point:

  manual   A human entered it. Automated enrichment never touches it without force=True.
  fetched  A provider wrote it. Freely refreshable.
  unknown  Pre-provenance legacy value of ambiguous origin. Refreshable, because it may be
           wrong -- the `imdb` field in particular may hold a TMDB vote_average rather than
           a real IMDb rating (RESEARCH section 1). The pre-migration number is kept under
           `legacy_value` so correcting it never destroys anything.

Shape stored on each movie row:

    "sources": {
      "<field>": {"origin": "manual"|"fetched"|"unknown",
                  "provider": "omdb"|"tmdb"|"derived"|"",
                  "at": "<iso8601 utc>",
                  "legacy_value": <pre-migration value>}   # unknown entries only
    }
"""
from datetime import datetime, timezone

MANUAL = "manual"
FETCHED = "fetched"
UNKNOWN = "unknown"

# The only fields an automated enrichment run is allowed to write.
ENRICHABLE_FIELDS = ("imdb", "rt_crit", "budget", "gross", "roi")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sources(entry: dict) -> dict:
    """Return the entry's sources dict, creating it if absent."""
    sources = entry.get("sources")
    if not isinstance(sources, dict):
        sources = {}
        entry["sources"] = sources
    return sources


def get_source(entry: dict, field: str) -> dict | None:
    source = _sources(entry).get(field)
    return source if isinstance(source, dict) else None


def set_source(entry: dict, field: str, origin: str, *, provider: str = "",
               at: str | None = None, legacy_value=None) -> dict:
    """Record provenance for `field`. Preserves an existing legacy_value unless one is given."""
    sources = _sources(entry)
    previous = sources.get(field) if isinstance(sources.get(field), dict) else {}
    source = {"origin": origin, "provider": provider, "at": at or now_iso()}
    carried = legacy_value if legacy_value is not None else previous.get("legacy_value")
    if carried is not None:
        source["legacy_value"] = carried
    sources[field] = source
    return source


def can_write(entry: dict, field: str, *, force: bool = False) -> bool:
    """The no-clobber rule.

    force=True overrides everything. Otherwise: manual is protected; fetched and unknown are
    writable; and a field with no recorded provenance is writable only if it is currently
    empty -- an unrecorded existing value is treated as a human's until proven otherwise.
    """
    if force:
        return True
    source = get_source(entry, field)
    if source is None:
        return entry.get(field) is None
    return source.get("origin") != MANUAL


def apply_fetched(entry: dict, field: str, value, *, provider: str,
                  force: bool = False) -> bool:
    """Write a provider value if the no-clobber rule allows. Returns True if written."""
    if value is None:
        return False
    if not can_write(entry, field, force=force):
        return False
    entry[field] = value
    set_source(entry, field, FETCHED, provider=provider)
    return True


def mark_manual(entry: dict, field: str) -> None:
    """Stamp a field as hand-entered (used by the PUT endpoint in Plan 02-05)."""
    set_source(entry, field, MANUAL, provider="")

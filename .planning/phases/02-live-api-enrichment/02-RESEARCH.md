# Phase 2 Research: Live API Enrichment + Caching

**Researched:** 2026-08-18
**Branch:** `research/live-api-enrichment`
**Question:** Which free APIs can supply per-film ratings and financials, and how should results be cached to keep call volume low?

---

## 1. Field-by-field API coverage

The scoring inputs in `backend/app/models.py` are: `imdb`, `letterboxd`, `rt_crit`, `rt_aud`, `budget`, `gross`, `roi`, `bo_rank`, `awards`.

| Field | Free source | Notes |
|-------|-------------|-------|
| `imdb` (0–10) | **OMDb** `imdbRating` | Real IMDb rating. Today the code stores TMDB `vote_average` in this field — a *different* number on the same 0–10 scale. OMDb is the accuracy fix. |
| `rt_crit` (0–100) | **OMDb** `Ratings[]` → "Rotten Tomatoes" | Returned as a string like `"72%"`; must be parsed. Critic score only. |
| `rt_aud` (0–100) | ❌ **none** | No free API exposes the RT *audience* score. Stays manual entry. |
| `letterboxd` (0–5) | ❌ **none practical** | API is request-only (email `api@letterboxd.com`, OAuth2, no guaranteed approval, explicitly "unable to individually reply"). Not something to design a build around. Stays manual. |
| `budget` (millions) | **TMDB** `budget` | OMDb has **no** budget field at all. TMDB is the only free option. |
| `gross` (millions) | **TMDB** `revenue` | Worldwide. OMDb's `BoxOffice` is **domestic US only** — TMDB is the better fit for an ROI metric. |
| `roi` | computed | `gross / budget`, already implemented in `_compute_roi`. |
| `bo_rank`, `awards` | ❌ not covered | Out of scope; no clean free source. |

**Conclusion: a two-provider split.** TMDB for financials (already wired), OMDb for ratings (new). Together they cover 4 of the 6 scoring inputs. `rt_aud` and `letterboxd` have no free path and must remain manual — this is a hard ceiling, not an implementation gap.

## 2. Provider details

### TMDB — already integrated (`backend/app/services/tmdb.py`)
- Free for personal/non-commercial use; commercial use needs a license.
- Rate limit ~40 req/sec, ~100k/day — effectively unlimited for a 30-film league.
- Returns `budget`, `revenue`, `vote_average`, `imdb_id`.
- **`imdb_id` is the key asset**: it lets us look the film up in OMDb by ID instead of by title, which removes fuzzy-title-match risk entirely.

### OMDb — new integration
- Free tier: **1,000 requests/day**, one key, from https://www.omdbapi.com/apikey.aspx
- Returns `Ratings[]` (IMDb / Rotten Tomatoes / Metacritic), `imdbRating`, `Metascore`, `BoxOffice`, `imdbID`.
- Lookup by `?i=tt1234567` (IMDb ID) is exact; `?t=Title` is fuzzy.

### Rejected options
| Option | Why rejected |
|--------|--------------|
| Letterboxd API | Request-only, no guaranteed approval. Can't build on it. |
| Scraping RT/Letterboxd | Against ToS, fragile, already rejected in `HANDOFF.md`. |
| Apify Box Office Tracker | Wraps Box Office Mojo; actor-based, not a free stable API, adds a vendor dependency for data TMDB already gives. |
| The Numbers / Saturation.io | Websites/datasets, not free APIs. |
| IMDb official API | Paid. |

## 3. ⚠ Blocking finding: there is no scoring formula in code

`backend/app/storage.py::compute_leaderboard` only **sums** already-stored values:

```python
row["total"] += m["total"]
row["rating_score"] += m["rating_score"]
row["financial_score"] += m["financial_score"]
```

`rating_score`, `financial_score`, `penalties`, and `total` are hand-entered from the spreadsheet (confirmed in `HANDOFF.md` §3: *"There is no formula in code."*).

**Consequence:** wiring live APIs will refresh `imdb`, `rt_crit`, `budget`, `gross`, and `roi` — but **every displayed score and the league standings will not move**, because nothing recomputes them from those inputs. The stated goal ("values … dynamically populate themselves") is only half-achievable without also implementing `compute_movie_scores()`.

The formula lives in the user's spreadsheet and is not derivable from the repo. Deriving it by fitting the 16 scored rows would be guesswork and is explicitly **not** recommended.

→ Split into two requirements: data fetching (independent) and score computation (needs the formula from the user).

## 4. ⚠ Data-safety finding: current enrich clobbers manual entries

`main.py::enrich_movie` overwrites unconditionally:

```python
if financials.get("vote_average") is not None:
    m["imdb"] = financials["vote_average"]
```

16/30 films have hand-entered ratings and 15/30 have hand-entered financials. A bulk enrich today would silently overwrite that work, and there is no provenance field to tell manual values from fetched ones, and no undo.

**Required mitigation:** add per-field provenance (`manual` vs `fetched`, with timestamp) and default to *never* overwriting a `manual` value unless explicitly forced. This must land **before** any bulk-enrich endpoint exists.

## 5. Caching design

**Why cache:** film metadata is near-static (budget/gross settle after theatrical run; ratings drift slowly). Without caching, a bulk refresh of 30 films = 60 calls (TMDB + OMDb each); repeated refreshes would burn the 1,000/day OMDb budget for no new data.

**Chosen approach: persistent JSON file cache** at `backend/data/api_cache.json`.

Rationale: matches the project's existing "flat file, no database" architecture (`league_data.json` + `threading.Lock` + atomic `os.replace`) and can reuse that exact write pattern. In-process dicts lose everything on restart; SQLite adds a dependency and a schema for what is a ~30-entry key/value store.

**Design:**
- **Key:** `{provider}:{imdb_id}` where available, else `{provider}:title:{normalized_title}:{year}`. Prefer IMDb ID — stable and exact.
- **Entry:** `{ "fetched_at": iso8601, "payload": {...}, "status": "hit"|"miss" }`
- **TTL, tiered by volatility:**
  - Released > 1 year ago → 30 days (financials final, ratings stable)
  - Released < 1 year ago → 7 days
  - Unreleased / no match → 24 h (**negative caching** — stops repeated lookups for films with no data yet, which matters here: 14 of 30 rows are unscored/unreleased)
- **Concurrency:** reuse `storage.py`'s lock + atomic-replace write pattern.
- **Manual invalidation:** `?force=true` on the enrich endpoint bypasses and refreshes the entry.
- **Rate discipline:** bulk enrich processes sequentially with a small delay and a per-run call cap, so one accidental loop can't exhaust the daily OMDb quota.

## 6. Secrets

`OMDB_API_KEY` joins `TMDB_API_KEY` in `backend/.env` (already gitignored; `.env.example` documents both). Keys must never be logged — `HANDOFF.md` notes an API-key-leak-in-logs bug was already fixed once, so preserve that.

## 7. Recommended scope split

| Req | Scope | Blocked on user? |
|-----|-------|------------------|
| API-01 | OMDb service module (`imdbRating`, `rt_crit`), IMDb-ID lookup via TMDB | no |
| API-02 | JSON file cache w/ tiered TTL + negative caching | no |
| API-03 | Field provenance (`manual` vs `fetched`) + no-clobber rule | no |
| API-04 | Bulk enrich endpoint w/ rate limiting + per-run cap | no |
| API-05 | `.env.example` + README/setup docs for both keys | no |
| API-06 | `compute_movie_scores()` — makes standings actually dynamic | **yes — needs the spreadsheet formula** |

API-01 through API-05 are independently buildable and deliver correct, cached, non-destructive data. API-06 is what makes the *scores* live, and needs the formula.

---

## Sources

- [OMDb API — key/pricing](https://omdbapi.com/apikey.aspx)
- [OMDb API — docs](https://www.omdbapi.com/)
- [TMDB — rate limiting](https://developer.themoviedb.org/docs/rate-limiting)
- [Letterboxd API (request-only beta)](https://letterboxd.com/api-beta/)
- [Best movie APIs comparison, 2026](https://api.market/blog/sleeyax/entertainment/best-movie-apis)
- [IMDb vs TMDb vs OMDb](https://dev.to/zuplo/whats-the-best-movie-database-api-imdb-vs-tmdb-vs-omdb-b24)

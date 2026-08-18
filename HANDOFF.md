# Movie League — Handoff Notes

## Current State

- **5 players**, 6 rounds each, **30 total movie slots**
- **16/30** movies have ratings (IMDb, RT, Letterboxd) — entered manually
- **15/30** movies have budget/gross — entered manually
- Backend: FastAPI, data lives in `backend/data/league_data.json` (flat file, no database)
- Frontend: React + Vite, dark gaming leaderboard aesthetic, movie cards with expandable score breakdowns

---

## What Was Done This Session

- Fixed 6 critical backend bugs (atomic file writes, CORS wildcard, API key leak in logs, PUT corruption, leaderboard crash on orphaned owner)
- Fixed 3 warning-level issues (async error handling, save failure error code, accessibility)
- Redesigned frontend: player cards with embedded movie cards, full score breakdown on click
- Wired ROI auto-computation (`gross / budget`) — triggers on both `/enrich` and manual `PUT`
- TMDB `vote_average` now returned by `/enrich` and stored as `imdb` field
- `python-dotenv` added — backend loads `backend/.env` at startup

---

## Next Steps

### 1. Activate TMDB enrichment (30 min)

Get a free key at https://www.themoviedb.org/settings/api then:

```bash
echo "TMDB_API_KEY=your_key_here" > backend/.env
```

Restart the backend, then enrich movies one at a time:
```bash
curl -X POST http://localhost:8000/api/movies/Andrew/1/enrich
```

Or ask Claude to add a **bulk enrich endpoint** (`POST /api/enrich-all`) that loops all movies with missing budget/gross and calls TMDB for each with a small delay to avoid rate limits.

**What TMDB fills in:** `budget`, `gross`, `roi` (computed), `imdb` (TMDB community rating — same 0-10 scale as IMDb, slightly different values)

**Note:** `imdb` field currently stores TMDB's `vote_average`, not the actual IMDb user rating. If you want the real IMDb score, add an OMDb API call (also free: https://www.omdbapi.com) using the `imdb_id` that TMDB returns.

---

### 2. RT + Letterboxd scores (no public API)

These fields have no official API. Options:

| Option | Effort | Risk |
|--------|--------|------|
| Keep manual entry | None | Fine for a small league |
| OMDb API | Low — free key, one HTTP call | Has RT score, no Letterboxd |
| BeautifulSoup scraping | Medium | Fragile, against ToS, may break any time |

**Recommended:** Use OMDb for RT scores. It returns `Rotten Tomatoes` percentage in its response alongside IMDb rating. Letterboxd has no API — keep manual.

To add OMDb: create `backend/app/services/omdb.py`, call `http://www.omdbapi.com/?t={title}&apikey={key}`, parse `Ratings` array for the RT entry, store in `rt_crit`.

---

### 3. Scoring formula (currently manual)

Right now `rating_score`, `financial_score`, `penalties`, `watch_points`, and `total` are **pre-calculated and stored in the JSON**. There is no formula in code.

To make scoring automatic, add a `compute_movie_scores(movie: dict) -> dict` function in `storage.py` and call it from the `PUT` and `enrich` endpoints. The formula lives in your spreadsheet — you'd just be transcribing it into Python.

Example structure:
```python
def compute_movie_scores(m: dict) -> dict:
    rating_score  = ...  # derive from imdb, rt_crit, rt_aud, letterboxd
    financial_score = ... # derive from roi, gross
    penalties     = ...  # derive from rt_crit threshold, etc.
    watch_points  = len(m.get("who_watched", [])) * POINTS_PER_WATCH
    m["rating_score"]   = rating_score
    m["financial_score"] = financial_score
    m["penalties"]      = penalties
    m["watch_points"]   = watch_points
    m["total"]          = rating_score + financial_score + penalties + watch_points
    return m
```

---

### 4. Deployment

- **Backend:** Render, Fly.io, or any VPS running a long-lived Python process. Swap `league_data.json` for a mounted persistent volume.
- **Frontend:** `npm run build` → deploy `dist/` to Netlify/Vercel/Cloudflare Pages. Set the `/api` proxy to point at your deployed backend URL in `vite.config.js` (for prod, set `VITE_API_BASE` env var instead of hardcoding).
- **Secrets:** Never commit `backend/.env`. Set `TMDB_API_KEY` and `CORS_ORIGIN` as environment variables in your hosting platform.

---

## File Map

```
backend/
  app/
    main.py          — API routes (leaderboard, owner, round, enrich)
    storage.py       — load/save JSON, compute leaderboard totals
    models.py        — Pydantic Movie model
    services/
      tmdb.py        — TMDB API: budget, gross, vote_average
      critic_scores_stub.py  — RT + Letterboxd stubs (not implemented)
  data/
    league_data.json — source of truth (30 movies, 5 owners)
  .env               — TMDB_API_KEY (create this, do not commit)
  .env.example       — template

frontend/
  src/
    App.jsx          — root, fetches leaderboard
    api.js           — fetch helpers
    components/
      Leaderboard.jsx  — renders list of PlayerCards
      PlayerCard.jsx   — player summary + movie grid, fetches own movies
      MovieCard.jsx    — movie card + expandable detail panel
    styles.css       — gaming leaderboard dark theme
```

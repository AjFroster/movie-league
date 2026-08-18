# Coding Conventions

**Analysis Date:** 2026-07-08

## Language Overview

The project is split into two distinct language environments with no TypeScript anywhere:

- **Backend:** Python 3.11+ (`backend/`)
- **Frontend:** JavaScript (ES2020+ modules) with JSX (`frontend/src/`)

No TypeScript is present. No type-checking tooling (mypy, tsc) is configured.

---

## Naming Patterns

### Python (Backend)

**Files:**
- `snake_case` module names: `main.py`, `models.py`, `storage.py`, `critic_scores_stub.py`, `tmdb.py`
- Descriptive `_stub` suffix for placeholder/not-yet-implemented modules: `critic_scores_stub.py`

**Functions:**
- `snake_case` for all functions: `load_data()`, `save_data()`, `compute_leaderboard()`, `fetch_movie_financials()`, `fetch_rt_scores()`
- Private helpers prefixed with `_`: `_api_key()` in `backend/app/services/tmdb.py`
- Route handler names mirror HTTP verb + resource: `get_leaderboard()`, `get_owner()`, `get_round()`, `update_movie()`, `enrich_movie()`

**Variables:**
- `snake_case` throughout: `round_number`, `movie_id`, `budget_millions`, `gross_millions`
- Module-level constants in `UPPER_SNAKE_CASE`: `DATA_PATH`, `TMDB_BASE`
- Module-level private singletons prefixed with `_`: `_lock` in `backend/app/storage.py`

**Classes:**
- `PascalCase`: `Movie`, `LeagueData` in `backend/app/models.py`

**Pydantic Fields:**
- `snake_case` field names matching JSON keys directly: `rating_score`, `financial_score`, `penalty_notes`, `who_watched`, `bo_rank`

### JavaScript/JSX (Frontend)

**Files:**
- `PascalCase` for React component files: `App.jsx`, `Leaderboard.jsx`, `OwnerDetail.jsx`
- `camelCase` for non-component modules: `api.js`
- `camelCase` for CSS: `styles.css`

**Functions and Components:**
- React components use `PascalCase` function declarations: `function FilmStrip()`, `export default function App()`, `export default function Leaderboard()`
- Internal helper functions use `PascalCase` only when they return JSX (treated as components): `FilmStrip` in `frontend/src/App.jsx`
- Pure logic helpers use `camelCase`: `totalClass()` in `frontend/src/components/Leaderboard.jsx`, `get()` in `frontend/src/api.js`

**Variables:**
- `camelCase`: `ownerMovies`, `setExpanded`, `roundNumber`
- React state variables follow `[value, setValue]` convention: `[rows, setRows]`, `[expanded, setExpanded]`, `[ownerMovies, setOwnerMovies]`

**Props:**
- `camelCase` prop names matching data shape: `rows`, `movies`

---

## Code Style

### Python

**Formatting:**
- No formatter config file found (no `black`, `ruff`, or similar config). Style is consistent with PEP 8 by observation:
  - 4-space indentation
  - Blank lines between top-level functions
  - Single blank line between logical blocks inside functions

**Imports:**
- Standard library first, then third-party, then relative:
  ```python
  # backend/app/main.py
  from fastapi import FastAPI, HTTPException
  from fastapi.middleware.cors import CORSMiddleware
  from .storage import load_data, save_data, compute_leaderboard
  from .models import Movie
  from .services import tmdb, critic_scores_stub
  ```
- Relative imports used consistently for intra-package imports (`.storage`, `.models`, `.services`)
- Services imported as modules, not individual functions: `from .services import tmdb` then called as `tmdb.fetch_movie_financials()`

**Type Hints:**
- Used throughout the backend, including Python 3.10+ union syntax (`str | None` not `Optional[str]`):
  ```python
  def load_data() -> dict:
  def save_data(data: dict) -> None:
  def fetch_movie_financials(title: str, year: int | None = None) -> dict | None:
  ```
- Pydantic models use inline defaults for optional fields: `imdb: float | None = None`
- Return types always annotated on service and storage functions; omitted on FastAPI route handlers (FastAPI infers response type)

### JavaScript/JSX

**Formatting:**
- No ESLint, Prettier, or Biome config files present. Style is hand-consistent:
  - 2-space indentation
  - Single quotes for strings
  - No trailing semicolons (ASI relied upon)
  - Arrow functions for callbacks and map/filter expressions
  - `async function` keyword syntax for named async functions inside components (not arrow-async)

**No linting tooling configured.** There is no `.eslintrc`, `eslint.config.*`, `.prettierrc`, or `biome.json` in the project.

---

## Import/Export Patterns

### Python

- Package `__init__.py` files are present but empty (zero-byte): `backend/app/__init__.py`, `backend/app/services/__init__.py`
- All imports in `main.py` use relative package imports (`from .storage import ...`)
- Service modules are imported as module objects to keep call sites readable: `tmdb.fetch_movie_financials()` not `from .services.tmdb import fetch_movie_financials`

### JavaScript

- Named exports for singleton objects: `export const api = { ... }` in `frontend/src/api.js`
- Default exports for all React components: `export default function Leaderboard(...)`, `export default function OwnerDetail(...)`
- Internal-only components (not exported): `function FilmStrip()` in `frontend/src/App.jsx` — defined locally, used once, not exported
- Import extensions are always explicit: `.jsx`, `.js`, `.css` always included in import paths

---

## Error Handling

### Python (Backend)

- HTTP errors raised with FastAPI's `HTTPException` with explicit `status_code` and a human-readable `detail` string:
  ```python
  raise HTTPException(status_code=404, detail=f"No owner named {owner}")
  raise HTTPException(status_code=404, detail="Movie entry not found")
  ```
- External API calls (`httpx`) use `.raise_for_status()` — HTTP errors propagate as exceptions, not wrapped
- Missing env vars handled gracefully by returning `None` early: `_api_key()` returns `None` and callers check `if not key: return None`
- No try/except blocks — errors surface as unhandled exceptions (FastAPI returns 500 automatically)
- File I/O errors (e.g., missing `league_data.json`) are not caught — would crash the process

### JavaScript (Frontend)

- Promise errors caught with `.catch()` at the call site:
  ```javascript
  api.leaderboard().then(setRows).catch((e) => setError(e.message))
  ```
- Error state displayed in UI as a plain message string; no error boundary component used
- Fetch helper throws on non-OK status: `if (!res.ok) throw new Error(...)`
- No global error handler or logging

---

## Comments

### Python

- Module-level docstrings used for context on files that need explanation, particularly stubs and external service integrations:
  ```python
  # backend/app/services/critic_scores_stub.py — explains why the module is a no-op
  # backend/app/services/tmdb.py — explains API key setup and which fields are available
  ```
- Function docstrings used selectively for non-obvious public functions:
  ```python
  def compute_leaderboard(data: dict) -> list[dict]:
      """Aggregate totals per owner across all rounds."""
  ```
  ```python
  async def fetch_movie_financials(title: str, year: int | None = None) -> dict | None:
      """Search TMDB for a title and return budget/gross (in millions) if found. ..."""
  ```
- Inline comments used for intent clarification on `# tighten this once you have a real deployed frontend origin` in `main.py`
- Stub function docstrings describe what the function WILL return once implemented, not what it does now

### JavaScript

- No JSDoc annotations anywhere in the frontend
- No inline comments in any `.jsx` or `.js` files
- Code is written to be self-documenting through naming

---

## Module Design

**Python packages** follow standard layout with `__init__.py` as empty markers (no re-exports). Callers import directly from the module they need.

**JavaScript modules** are kept small and single-purpose:
- `api.js` — all HTTP calls, single export
- `App.jsx` — root layout and data fetch
- `Leaderboard.jsx` — table rendering + expand logic
- `OwnerDetail.jsx` — expanded row content

No barrel `index.js` files. All imports reference the file directly.

---

## Function Design

**Python:**
- Functions are short (all under ~20 lines)
- Single responsibility — `load_data` only reads, `save_data` only writes, `compute_leaderboard` only computes
- Synchronous vs. async is explicit: TMDB calls are `async def`, everything else is `def`

**JavaScript:**
- Components are concise (all under 65 lines)
- State-fetching logic lives in the component that renders it (`Leaderboard` owns `ownerMovies` fetch)
- No custom hooks — logic is inline

---

*Convention analysis: 2026-07-08*

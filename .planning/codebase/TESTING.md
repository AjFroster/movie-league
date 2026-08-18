# Testing Patterns

**Analysis Date:** 2026-07-08

## Testing Frameworks Present

**None.** There are zero testing frameworks installed or configured in this project.

- **Frontend (`frontend/package.json`):** No test runner listed in `dependencies` or `devDependencies`. No Vitest, Jest, React Testing Library, Playwright, or Cypress.
- **Backend (`backend/requirements.txt`):** No pytest, unittest extras, httpx test client configuration, or any testing library.
- **No config files:** No `jest.config.*`, `vitest.config.*`, `pytest.ini`, `conftest.py`, `setup.cfg`, or `pyproject.toml` anywhere in the project.

---

## Test Files

**There are no test files.** A full recursive search of the project found zero files matching:
- `*.test.js`, `*.test.jsx`, `*.test.ts`, `*.test.tsx`
- `*.spec.js`, `*.spec.jsx`
- `test_*.py`, `*_test.py`

---

## What Is Tested

**Nothing is formally tested.** The entire application runs without any automated test coverage.

---

## What Is Not Tested

Every layer of the application lacks test coverage:

**Backend (`backend/`):**

- `backend/app/storage.py` — `load_data()`, `save_data()`, and `compute_leaderboard()` are untested. `compute_leaderboard` contains ranking logic (sorting, aggregation, `rounds_played` counting) that would benefit from unit tests with fixture data.
- `backend/app/main.py` — All six API route handlers (`GET /api/leaderboard`, `GET /api/owners/{owner}`, `GET /api/rounds/{round_number}`, `GET /api/movies`, `PUT /api/movies/{owner}/{round_number}`, `POST /api/movies/{owner}/{round_number}/enrich`) are untested. FastAPI ships with a `TestClient` (via `httpx`) that makes route-level integration tests trivial to write.
- `backend/app/models.py` — Pydantic model validation is untested. Edge cases (negative scores, null fields, empty `who_watched` list) are not exercised.
- `backend/app/services/tmdb.py` — `fetch_movie_financials()` makes live HTTP calls and is untested. No mock of `httpx.AsyncClient` exists.
- `backend/app/services/critic_scores_stub.py` — Currently no-ops (`return None`), so no test value yet, but the module's interface should be tested before implementation.

**Frontend (`frontend/src/`):**

- `frontend/src/api.js` — `get()` fetch wrapper and all three `api.*` methods untested.
- `frontend/src/App.jsx` — Data-fetching lifecycle (`useEffect` + `useState` with loading/error/success states), `FilmStrip` rendering, error display — all untested.
- `frontend/src/components/Leaderboard.jsx` — `toggle()` expand/collapse logic, `totalClass()` helper, row rendering, keyboard interaction (`onKeyDown`) — all untested.
- `frontend/src/components/OwnerDetail.jsx` — Loading state (`movies === null`), round row rendering, sign formatting, `penalty_notes` conditional — all untested.

---

## Test Coverage Gaps by Priority

**High — Core business logic:**
- `compute_leaderboard()` in `backend/app/storage.py`: ranking calculation is the heart of the app. No test means score aggregation bugs would go undetected.
- `totalClass()` in `frontend/src/components/Leaderboard.jsx`: small function with clear contract (positive/negative/zero), trivial to test.
- `PUT /api/movies/{owner}/{round_number}` route: mutates the data file; correctness is critical and currently unverified.

**High — Error paths:**
- 404 handling in `get_owner()` and `get_round()` — these raise `HTTPException` but are never exercised.
- Frontend error state when API returns non-OK — the `.catch()` branch in `App.jsx` sets `error` state but is never tested.

**Medium — External integrations:**
- `fetch_movie_financials()` in `backend/app/services/tmdb.py`: async HTTP call with no-key early-return path and result mapping are both untestable without mocking. The no-key path (`if not key: return None`) is the safest to test immediately.

**Medium — UI interaction:**
- `toggle()` in `Leaderboard.jsx`: lazy-loads owner data on expand, caches in `ownerMovies` state, collapses on second click. Three distinct behaviors, zero coverage.

**Low — Stubs:**
- `critic_scores_stub.py` stubs return `None` now — no test value until implemented.

---

## CI/CD Testing Setup

**None.** There is no `.github/workflows/`, no `Makefile`, no CI configuration of any kind. The project has no automated test pipeline.

---

## How to Add Tests (Recommended Starting Point)

### Backend — pytest + httpx TestClient

Install:
```bash
pip install pytest pytest-asyncio httpx
```

Recommended test layout:
```
backend/
└── tests/
    ├── __init__.py
    ├── test_storage.py      # unit tests for compute_leaderboard(), load_data(), save_data()
    ├── test_routes.py       # integration tests via FastAPI TestClient
    └── test_tmdb.py         # async tests with mocked httpx
```

Minimal route test pattern (no config needed):
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### Frontend — Vitest + React Testing Library

Install:
```bash
npm install -D vitest @testing-library/react @testing-library/user-event jsdom
```

Add to `frontend/vite.config.js`:
```javascript
test: {
  environment: 'jsdom',
  globals: true,
  setupFiles: './src/test-setup.js',
}
```

Recommended test layout (co-located):
```
frontend/src/
├── api.js
├── api.test.js
├── components/
│   ├── Leaderboard.jsx
│   ├── Leaderboard.test.jsx
│   ├── OwnerDetail.jsx
│   └── OwnerDetail.test.jsx
```

Minimal component test pattern:
```javascript
import { render, screen } from '@testing-library/react'
import OwnerDetail from './OwnerDetail'

test('shows loading state when movies is null', () => {
  render(<OwnerDetail movies={null} />)
  expect(screen.getByText('Loading rounds…')).toBeInTheDocument()
})
```

---

## Mocking Patterns (Currently Absent — Needed)

**Backend — httpx mocking** for `tmdb.py`:
- Use `pytest-mock` or `unittest.mock.patch` to mock `httpx.AsyncClient.get`
- Or use `respx` library for route-level httpx mocking

**Frontend — fetch mocking** for `api.js`:
- Use `vitest`'s built-in `vi.fn()` to mock `global.fetch`
- Or use `msw` (Mock Service Worker) for API-level mocking in integration tests

Neither approach is set up. Any new test writing should establish one of these patterns first.

---

*Testing analysis: 2026-07-08*

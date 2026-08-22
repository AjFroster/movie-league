import { defineConfig, devices } from '@playwright/test'

/** Browser tests against a real backend, a real database, and the real UI.
 *
 *  No auth stubbing: with CLERK_ISSUER empty the app runs in local mode -- one real user,
 *  permissions still enforced. That is a legitimate mode rather than a bypass, which is
 *  what makes it usable as a test fixture.
 *
 *  The backend gets its own file database under /tmp, so a run cannot touch real leagues.
 */
const API_PORT = 8123
const WEB_PORT = 5273
const DB = process.env.E2E_DB || '/tmp/movie-league-e2e.db'
// The venv locally; CI installs into the runner's own python and overrides this.
const PY = process.env.E2E_PYTHON || '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  // A draft is a sequence of turns; running specs in parallel against one database would
  // have them stepping on each other's leagues.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: [
    {
      command:
        `rm -f ${DB} && ` +
        `DATABASE_URL=sqlite:///${DB} ${PY} -m alembic upgrade head && ` +
        `DATABASE_URL=sqlite:///${DB} ${PY} -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: '../backend',
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      // Empty rather than absent: main.py calls load_dotenv(), and backend/.env would put
      // CLERK_ISSUER back -- load_dotenv does not override a variable that is already set.
      env: { CLERK_ISSUER: '', CLERK_JWKS_URL: '', CORS_ORIGIN: `http://127.0.0.1:${WEB_PORT}` },
    },
    {
      command: `npx vite --mode test --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { VITE_API_PORT: String(API_PORT) },
    },
  ],
})

import { defineConfig, devices } from '@playwright/test'

/** Two people, one draft.
 *
 *  The single-user suite cannot test this: local mode is one identity per process, so one
 *  browser can only ever be one person. Two backend processes on ONE database, each with
 *  its own LEAGUE_LOCAL_USER, gives two real users sharing real state -- no Clerk, no
 *  secrets, no dependency on anyone else's uptime.
 *
 *  What it proves that nothing else can: a pick made by one person appears on the other
 *  person's board without a reload, and the person whose turn it is not gets no button.
 */
const DB = process.env.E2E_DB || '/tmp/movie-league-multiuser.db'
const PY = process.env.E2E_PYTHON || '.venv/bin/python'

export const PLAYERS = [
  { name: 'alice', api: 8131, web: 5281 },
  { name: 'bob', api: 8132, web: 5282 },
]

const backend = ({ name, api, web }) => ({
  command: `${PY} -m uvicorn app.main:app --port ${api}`,
  cwd: '../backend',
  url: `http://127.0.0.1:${api}/api/health`,
  reuseExistingServer: false,
  timeout: 120_000,
  stdout: 'pipe',
  stderr: 'pipe',
  env: {
    ...process.env,
    DATABASE_URL: `sqlite:///${DB}`,
    LEAGUE_LOCAL_USER: name,
    CLERK_ISSUER: '',
    CLERK_JWKS_URL: '',
    CORS_ORIGIN: `http://127.0.0.1:${web}`,
  },
})

const frontend = ({ api, web }) => ({
  command: `npx vite --mode test --host 127.0.0.1 --port ${web} --strictPort`,
  url: `http://127.0.0.1:${web}`,
  reuseExistingServer: false,
  timeout: 120_000,
  stdout: 'pipe',
  stderr: 'pipe',
  env: { ...process.env, VITE_API_PORT: String(api) },
})

export default defineConfig({
  testDir: './e2e-multiuser',
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  // Two browsers taking turns, with a 2-second poll between them, is slower than one.
  timeout: 90_000,
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [...PLAYERS.map(backend), ...PLAYERS.map(frontend)],
})

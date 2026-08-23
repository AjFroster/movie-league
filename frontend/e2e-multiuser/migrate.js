import { execFileSync } from 'node:child_process'
import { rmSync } from 'node:fs'

/** Build the shared database. Run BEFORE playwright, never as a globalSetup hook.
 *
 *  Playwright starts its webServers around globalSetup, so a hook that deletes and
 *  recreates the database does it underneath two already-running backends. They keep
 *  their handle on the removed inode and every query afterwards is either a disk I/O
 *  error or a lookup against an empty file -- which showed up as "no league with id 1"
 *  immediately after creating that league.
 *
 *  Both backends share one file, so the migration has to happen once, before either.
 */
const db = process.env.E2E_DB || '/tmp/movie-league-multiuser.db'
const py = process.env.E2E_PYTHON || '.venv/bin/python'

// The sidecars too: SQLite runs in WAL mode here, and a stale -wal against a freshly
// created database is a "disk I/O error" that looks like a disk problem and is not.
for (const suffix of ['', '-wal', '-shm']) rmSync(`${db}${suffix}`, { force: true })

execFileSync(py, ['-m', 'alembic', 'upgrade', 'head'], {
  cwd: '../backend',
  stdio: 'inherit',
  env: { ...process.env, DATABASE_URL: `sqlite:///${db}`, CLERK_ISSUER: '', CLERK_JWKS_URL: '' },
})
console.log('shared e2e database ready')

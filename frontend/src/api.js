const BASE = '/api'

// Every request funnels through get/send/post/download, so attaching credentials is one
// place rather than thirty. Left as a hook rather than importing Clerk directly: the app
// runs with no identity provider at all on a laptop, and api.js should not know or care.
let tokenProvider = async () => null

export function setTokenProvider(fn) {
  tokenProvider = fn
}

async function authHeaders() {
  const token = await tokenProvider()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// The server explains a rejected pick ("Frozen III has already been drafted"); surfacing
// that verbatim is far more useful than a status code, and the draft board shows it inline.
async function describe(res, path) {
  let detail = null
  try { detail = (await res.json()).detail } catch { /* non-JSON error body */ }
  const error = new Error(detail || `${path} failed: ${res.status}`)
  error.status = res.status
  return error
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: await authHeaders() })
  if (!res.ok) throw await describe(res, path)
  return res.json()
}

async function send(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...(await authHeaders()) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw await describe(res, path)
  return res.status === 204 ? null : res.json()
}

/** Fetch a file, keeping the server's filename from Content-Disposition. */
async function download(path) {
  const res = await fetch(`${BASE}${path}`, { headers: await authHeaders() })
  if (!res.ok) throw await describe(res, path)
  const match = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')
  return { blob: await res.blob(), filename: match ? match[1] : 'movie-league.json' }
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await describe(res, path)
  return res.json()
}

export const api = {
  leagues: () => get('/leagues'),
  exportArchive: () => download('/export'),
  exportLeague: (id) => download(`/leagues/${id}/export`),
  claimSlot: (id, player) => post(`/leagues/${id}/claim`, { player }),
  releaseSlot: (id, player) =>
    send('DELETE', `/leagues/${id}/claim/${encodeURIComponent(player)}`),
  renameLeague: (id, name) => send('PATCH', `/leagues/${id}`, { name }),
  setSettlesOn: (id, settlesOn) => send('PATCH', `/leagues/${id}`, { settles_on: settlesOn }),
  setPickSeconds: (id, seconds) => send('PATCH', `/leagues/${id}`, { pick_seconds: seconds }),
  setVisibility: (id, visibility) => send('PATCH', `/leagues/${id}`, { visibility }),
  autopick: (id) => post(`/leagues/${id}/draft/autopick`, {}),
  freezeLeague: (id, frozen = true) =>
    send('POST', `/leagues/${id}/freeze?frozen=${frozen}`),
  deleteLeague: (id) => send('DELETE', `/leagues/${id}`),
  leagueLeaderboard: (id) => get(`/leagues/${id}/leaderboard`),
  leagueOwner: (id, name) => get(`/leagues/${id}/owners/${encodeURIComponent(name)}`),
  leagueEnrich: (id) => post(`/leagues/${id}/enrich-all`, {}),
  createLeague: (body) => post('/leagues', body),
  poolSize: (year) => get(`/leagues/pool-size?year=${year}`),
  draft: (id) => get(`/leagues/${id}/draft`),
  startDraft: (id) => post(`/leagues/${id}/draft/start`, {}),
  makePick: (id, player, tmdbId, title, posterPath) =>
    post(`/leagues/${id}/draft/pick`,
         { player, tmdb_id: tmdbId, title, poster_path: posterPath ?? null }),
  pool: (id, size = 300) => get(`/leagues/${id}/pool?size=${size}`),
  poolSearch: (id, q) => get(`/leagues/${id}/pool/search?q=${encodeURIComponent(q)}`),
  setWatched: (leagueId, owner, round, viewer, watched) =>
    post(`/leagues/${leagueId}/movies/${encodeURIComponent(owner)}/${round}/watch`,
         { viewer, watched }),
}

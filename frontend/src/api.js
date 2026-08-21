const BASE = '/api'

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
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw await describe(res, path)
  return res.json()
}

async function send(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw await describe(res, path)
  return res.status === 204 ? null : res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await describe(res, path)
  return res.json()
}

export const api = {
  leagues: () => get('/leagues'),
  renameLeague: (id, name) => send('PATCH', `/leagues/${id}`, { name }),
  setSettlesOn: (id, settlesOn) => send('PATCH', `/leagues/${id}`, { settles_on: settlesOn }),
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
  setWatched: (owner, round, viewer, watched, leagueId) =>
    post(leagueId
      ? `/leagues/${leagueId}/movies/${encodeURIComponent(owner)}/${round}/watch`
      : `/movies/${encodeURIComponent(owner)}/${round}/watch`, { viewer, watched }),
  leaderboard: () => get('/leaderboard'),
  owner: (name) => get(`/owners/${encodeURIComponent(name)}`),
  round: (n) => get(`/rounds/${n}`),
}

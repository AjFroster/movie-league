const BASE = '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`)
  return res.json()
}

export const api = {
  setWatched: (owner, round, viewer, watched) =>
    post(`/movies/${encodeURIComponent(owner)}/${round}/watch`, { viewer, watched }),
  leaderboard: () => get('/leaderboard'),
  owner: (name) => get(`/owners/${encodeURIComponent(name)}`),
  round: (n) => get(`/rounds/${n}`),
}

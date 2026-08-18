const BASE = '/api'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`)
  return res.json()
}

export const api = {
  leaderboard: () => get('/leaderboard'),
  owner: (name) => get(`/owners/${encodeURIComponent(name)}`),
  round: (n) => get(`/rounds/${n}`),
}

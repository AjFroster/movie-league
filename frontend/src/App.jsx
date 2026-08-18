import { useEffect, useState } from 'react'
import Leaderboard from './components/Leaderboard.jsx'
import { api } from './api.js'

export default function App() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.leaderboard().then(setRows).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>Fantasy Movie League</h1>
        <p>Season standings · click any movie for full breakdown</p>
      </header>

      {error && <div className="state-msg">Couldn't reach the backend — is it running on :8000?</div>}
      {!error && !rows && <div className="state-msg">Loading…</div>}
      {rows && <Leaderboard rows={rows} />}
    </div>
  )
}

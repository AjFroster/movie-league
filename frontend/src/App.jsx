import { useEffect, useState } from 'react'
import Leaderboard from './components/Leaderboard.jsx'
import ThisWeekSidebar from './components/ThisWeekSidebar.jsx'
import { api } from './api.js'

export default function App() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  const refresh = () => api.leaderboard().then(setRows).catch((e) => setError(e.message))

  useEffect(() => { refresh() }, [])

  return (
    <div className="app">
      <header className="header">
        <span className="header-mark" />
        <div>
          <h1>Fantasy Movie League</h1>
          <p>Season standings · click any round for full breakdown</p>
        </div>
      </header>

      {error && (
        <div className="state-msg">
          Couldn't reach the backend — confirm the API is running on :8000 and refresh.
        </div>
      )}
      {!error && !rows && <div className="state-msg">Loading…</div>}
      {!error && rows && rows.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-heading">No standings yet</div>
          <div className="empty-state-body">Add players and movie picks to the league data to see rankings here.</div>
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="app-layout">
          <main className="app-main">
            <Leaderboard rows={rows} onWatchChange={refresh} />
          </main>
          <ThisWeekSidebar />
        </div>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import Leaderboard from './components/Leaderboard.jsx'
import ThisWeekSidebar from './components/ThisWeekSidebar.jsx'
import LeagueList from './components/LeagueList.jsx'
import CreateLeague from './components/CreateLeague.jsx'
import DraftBoard from './components/DraftBoard.jsx'
import { api } from './api.js'

export default function App() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  // A four-view app does not need a router; a tagged view keeps the whole navigation
  // model readable in one place.
  const [view, setView] = useState({ name: 'leagues' })

  const refresh = () => api.leaderboard().then(setRows).catch((e) => setError(e.message))

  useEffect(() => { refresh() }, [])

  if (view.name === 'leagues') {
    return (
      <div className="app">
        <LeagueList
          onCreate={() => setView({ name: 'create' })}
          onOpenLeague={(league) => setView({ name: 'draft', leagueId: league.id })}
          onOpenStandings={() => { refresh(); setView({ name: 'standings' }) }}
        />
      </div>
    )
  }

  if (view.name === 'create') {
    return (
      <div className="app">
        <CreateLeague
          onCancel={() => setView({ name: 'leagues' })}
          onCreated={(state) => setView({ name: 'draft', leagueId: state.league_id })}
        />
      </div>
    )
  }

  if (view.name === 'draft') {
    return (
      <div className="app">
        <DraftBoard
          leagueId={view.leagueId}
          onExit={() => setView({ name: 'leagues' })}
          onFinished={() => { refresh() }}
        />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="header">
        <span className="header-mark" />
        <div>
          <h1>Fantasy Movie League</h1>
          <p>
            <button className="linkish" onClick={() => setView({ name: 'leagues' })}>
              All leagues
            </button>
            {' · '}Season standings · click any round for full breakdown
          </p>
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

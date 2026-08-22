import { useEffect, useState } from 'react'
import ThemeToggle from './components/ThemeToggle.jsx'
import Leaderboard from './components/Leaderboard.jsx'
import ThisWeekSidebar from './components/ThisWeekSidebar.jsx'
import LeagueList from './components/LeagueList.jsx'
import CreateLeague from './components/CreateLeague.jsx'
import DraftBoard from './components/DraftBoard.jsx'
import { api } from './api.js'

export default function App() {
  // Rows carry the league they describe. Effects run after render, so clearing them in
  // an effect still lets one render through with the previous league's players, and
  // every card fetches a player that season never had. Matching on the id instead
  // means stale rows are simply never rendered.
  const [board, setBoard] = useState(null)
  const [error, setError] = useState(null)
  // A four-view app does not need a router; a tagged view keeps the whole navigation
  // model readable in one place.
  const [view, setView] = useState({ name: 'leagues' })

  const refresh = (leagueId) =>
    api.leagueLeaderboard(leagueId)
      .then((rows) => setBoard({ leagueId, rows }))
      .catch((e) => setError(e.message))

  useEffect(() => {
    setError(null)
    refresh(view.leagueId)
  }, [view.name, view.leagueId])

  // Only rows fetched for the league currently on screen.
  const rows = board && board.leagueId === view.leagueId ? board.rows : null

  if (view.name === 'leagues') {
    return (
      <div className="app">
        <LeagueList
          onCreate={() => setView({ name: 'create' })}
          onOpenLeague={(league) => setView({ name: 'draft', leagueId: league.id })}
          onOpenStandings={(league) =>
            setView({ name: 'standings', leagueId: league.id, leagueName: league.name })}
        />
        <ThemeToggle />
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
        <ThemeToggle />
      </div>
    )
  }

  if (view.name === 'draft') {
    return (
      <div className="app">
        <DraftBoard
          leagueId={view.leagueId}
          onExit={() => setView({ name: 'leagues' })}
          onFinished={() => {}}
          onStandings={(leagueId, leagueName) =>
            setView({ name: 'standings', leagueId, leagueName })}
        />
        <ThemeToggle />
      </div>
    )
  }

  return (
    <div className="app">
      <header className="header">
        <span className="header-mark" />
        <div>
          <h1>{view.leagueName || 'Fantasy Movie League'}</h1>
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
            <Leaderboard
              rows={rows}
              leagueId={view.leagueId}
              onWatchChange={() => refresh(view.leagueId)}
            />
          </main>
          <ThisWeekSidebar />
        </div>
      )}
      <ThemeToggle />
    </div>
  )
}

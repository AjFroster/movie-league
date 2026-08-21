import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABEL = { setup: 'SETUP', drafting: 'DRAFTING', complete: 'COMPLETE' }

function ordinalSuffix(n) {
  return n === 1 ? '' : 's'
}

/** Progress means different things before and after a draft finishes.
 *  Mid-draft the number that matters is picks; once every slot is filled the season is
 *  running and the live number becomes how many films have ratings in yet. */
function progressFor(league) {
  if (league.status === 'complete') {
    return { done: league.films_scored, total: league.films_total,
             caption: `Season running · ${league.films_scored} of ${league.films_total} films scored` }
  }
  if (league.status === 'setup') {
    return { done: 0, total: league.total_picks,
             caption: `Order not drawn · ${league.players.length} player${ordinalSuffix(league.players.length)} invited` }
  }
  return { done: league.picks_made, total: league.total_picks,
           caption: league.players.join(', ') }
}

function actionFor(league) {
  if (league.status === 'drafting') return { label: 'RESUME DRAFT', primary: true }
  if (league.status === 'setup') return { label: 'OPEN', primary: false }
  return { label: 'STANDINGS', primary: false }
}

export default function LeagueList({ onOpenLeague, onCreate, onOpenStandings }) {
  const [leagues, setLeagues] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.leagues().then(setLeagues).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="state-msg" role="alert">{error}</div>
  if (!leagues) return <div className="state-msg">Loading leagues…</div>

  const drafting = leagues.filter((l) => l.status === 'drafting').length

  return (
    <div className="league-page">
      <header className="league-header">
        <div>
          <h1 className="league-wordmark"><span className="header-mark" />Movie League</h1>
          <p className="league-subtitle">
            {leagues.length} league{ordinalSuffix(leagues.length)}
            {drafting > 0 && ` · ${drafting} draft${ordinalSuffix(drafting)} in progress`}
          </p>
        </div>
        <button className="btn" onClick={onCreate}>NEW LEAGUE</button>
      </header>

      {leagues.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-heading">No leagues yet</div>
          <div className="empty-state-body">
            Create one to name your players and draft a season.
          </div>
        </div>
      ) : (
        <div className="league-table">
          <div className="league-row league-head">
            <span>League</span><span>Year</span><span>Status</span>
            <span className="num">Players</span><span>Draft progress</span><span />
          </div>
          {leagues.map((league) => {
            const progress = progressFor(league)
            const action = actionFor(league)
            // "Archived" is not a stored status -- a completed league that is no longer the
            // current season simply reads as history, so it is dimmed rather than flagged.
            const archived = league.status === 'complete' && league.id !== leagues[0].id
            const percent = progress.total
              ? Math.round((progress.done / progress.total) * 100) : 0
            return (
              <div className={`league-row${archived ? ' archived' : ''}`} key={league.id}>
                <span className="league-name-cell">
                  <span className="league-name">{league.name}</span>
                  <span className="league-meta">{progress.caption}</span>
                </span>
                <span className="league-year">{league.year}</span>
                <span className="league-status">
                  <span className={`status-dot ${league.status}`} />
                  {STATUS_LABEL[league.status]}
                </span>
                <span className="num league-players">{league.players.length}</span>
                <span className="league-progress">
                  <span className="league-progress-bar">
                    <span className="league-progress-fill" style={{ width: `${percent}%` }} />
                  </span>
                  <span className="league-progress-count">
                    {progress.done} / {progress.total}
                  </span>
                </span>
                <span className="league-action">
                  <button
                    className={`btn${action.primary ? ' btn-primary' : ''}`}
                    onClick={() => (league.status === 'complete'
                      ? onOpenStandings(league)
                      : onOpenLeague(league))}
                  >
                    {action.label}
                  </button>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

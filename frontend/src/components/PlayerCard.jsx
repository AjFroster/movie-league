import { useEffect, useState } from 'react'
import MovieCard from './MovieCard.jsx'
import { api } from '../api.js'

const ORDINALS = ['', '1ST', '2ND', '3RD', '4TH', '5TH', '6TH', '7TH', '8TH', '9TH', '10TH']

function ordinal(n) {
  return ORDINALS[n] || `${n}TH`
}

function signed(v) {
  return v > 0 ? `+${v}` : `${v}`
}

export default function PlayerCard({ summary, ownerCount, owners, onWatchChange, leagueId }) {
  const [movies, setMovies] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    // Scoped to a league when one is named, so reviewing an older season shows that
    // season rather than whichever league happens to be current.
    const request = leagueId
      ? api.leagueOwner(leagueId, summary.owner)
      : api.owner(summary.owner)
    request.then(d => setMovies(d.movies)).catch(e => setError(e.message))
  }, [summary.owner, leagueId])

  return (
    <div className={`player-card${summary.rank === 1 ? ' rank-1' : ''}`}>
      <div className="player-header">
        <div className="player-rank">#{summary.rank}</div>
        <div className="player-identity">
          <div className="player-meta-line">
            {ordinal(summary.rank)} OF {ownerCount} · {summary.rounds_played} ROUND{summary.rounds_played === 1 ? '' : 'S'}
          </div>
          <div className="player-name">{summary.owner}</div>
        </div>
        <div className="player-stats">
          <div className="stat-block">
            <span className="stat-block-label">TOTAL</span>
            <span className={`stat-block-value ${summary.total > 0 ? 'positive' : summary.total < 0 ? 'negative' : ''}`}>
              {signed(summary.total)}
            </span>
          </div>
          <div className="stat-block">
            <span className="stat-block-label">RATING</span>
            <span className="stat-block-value">{signed(summary.rating_score)}</span>
          </div>
          <div className="stat-block">
            <span className="stat-block-label">FINANCIAL</span>
            <span className="stat-block-value">{signed(summary.financial_score)}</span>
          </div>
          <div className="stat-block">
            <span className="stat-block-label">WATCH</span>
            <span className="stat-block-value">+{summary.watch_points}</span>
          </div>
          {summary.penalties !== 0 && (
            <div className="stat-block">
              <span className="stat-block-label">PENALTIES</span>
              <span className="stat-block-value negative">{signed(summary.penalties)}</span>
            </div>
          )}
        </div>
      </div>

      <div className="roster-table">
        <div className="roster-header-row">
          <span>ROUND</span>
          <span>TITLE</span>
          <span>STATUS</span>
          <span>PTS</span>
          <span>WATCHED</span>
        </div>
        {error && <div className="card-error" role="alert">{error}</div>}
        {!movies && !error && <div className="state-msg">Loading rounds…</div>}
        {movies && movies.map(m => (
          <MovieCard
            key={m.round}
            movie={m}
            ownerCount={ownerCount}
            owners={owners}
            leagueId={leagueId}
            onWatched={(updated) => {
              // Patch the row in place so the panel reflects the toggle immediately,
              // then let the parent refresh standings -- a cross-owner watch scores for
              // someone whose card is not this one.
              setMovies((prev) =>
                prev.map((x) => (x.round === updated.round ? updated : x)))
              onWatchChange?.()
            }}
          />
        ))}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import MovieCard from './MovieCard.jsx'
import { api } from '../api.js'

const RANK_COLORS = {
  1: '#fbbf24',
  2: '#67e8f9',
  3: '#fb923c',
}

const MAX_SCORE = 120 // approximate season max for progress bar

function ScoreChip({ label, value, type }) {
  return (
    <span className={`score-chip ${type}`}>
      {label} <strong>{value > 0 ? `+${value}` : value}</strong>
    </span>
  )
}

export default function PlayerCard({ summary }) {
  const [movies, setMovies] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.owner(summary.owner)
      .then(d => setMovies(d.movies))
      .catch(e => setError(e.message))
  }, [summary.owner])

  const rankColor = RANK_COLORS[summary.rank]
  const scorePct = `${Math.min(Math.max(summary.total, 0) / MAX_SCORE * 100, 100).toFixed(1)}%`

  return (
    <div
      className={`player-card rank-${summary.rank}`}
      style={rankColor ? { '--rank-color': rankColor } : undefined}
    >
      <div className="player-header">
        <div className="player-rank">#{summary.rank}</div>

        <div className="player-meta">
          <div className="player-name">{summary.owner}</div>
          <div className="player-chips">
            <ScoreChip label="★ Rating"   value={summary.rating_score}    type="rating" />
            <ScoreChip label="$ Finance"  value={summary.financial_score} type="financial" />
            <ScoreChip label="👁 Watch"   value={summary.watch_points}    type="watch" />
            {summary.penalties !== 0 && (
              <ScoreChip label="⚠ Penalty" value={summary.penalties} type="penalty" />
            )}
            <span className="rounds-badge">{summary.rounds_played}/6 rounds</span>
          </div>
          <div className="player-score-bar">
            <div
              className="player-score-bar-fill"
              style={{ '--score-pct': scorePct }}
            />
          </div>
        </div>

        <div
          className={`player-total ${summary.total > 0 ? 'positive' : summary.total < 0 ? 'negative' : 'zero'}`}
          style={rankColor ? { '--rank-color': rankColor } : undefined}
        >
          {summary.total > 0 ? `+${summary.total}` : summary.total}
          <span className="total-label">pts</span>
        </div>
      </div>

      <div className="movie-grid">
        {error && <div className="card-error" role="alert">{error}</div>}
        {!movies && !error && (
          [1,2,3,4,5,6].map(n => <div key={n} className="movie-card skeleton" />)
        )}
        {movies && movies.map(m => (
          <MovieCard key={m.round} movie={m} />
        ))}
      </div>
    </div>
  )
}

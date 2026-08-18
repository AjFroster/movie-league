import { useState } from 'react'

function MovieDetail({ m }) {
  const hasRatings = m.imdb !== null || m.letterboxd !== null || m.rt_crit !== null || m.rt_aud !== null
  const hasFinancials = m.budget !== null || m.gross !== null

  return (
    <div className="movie-detail">
      {hasRatings && (
        <div className="detail-section">
          <div className="detail-section-title">Ratings</div>
          <div className="detail-stats">
            {m.imdb !== null && (
              <div className="stat-item">
                <span className="stat-key">IMDb</span>
                <span className="stat-val">{m.imdb}</span>
              </div>
            )}
            {m.letterboxd !== null && (
              <div className="stat-item">
                <span className="stat-key">Letterboxd</span>
                <span className="stat-val">{m.letterboxd}</span>
              </div>
            )}
            {m.rt_crit !== null && (
              <div className="stat-item">
                <span className="stat-key">RT Critics</span>
                <span className="stat-val">{m.rt_crit}%</span>
              </div>
            )}
            {m.rt_aud !== null && (
              <div className="stat-item">
                <span className="stat-key">RT Audience</span>
                <span className="stat-val">{m.rt_aud}%</span>
              </div>
            )}
          </div>
          <div className="detail-points rating">
            → Rating score: {m.rating_score > 0 ? `+${m.rating_score}` : m.rating_score} pts
          </div>
        </div>
      )}

      {hasFinancials && (
        <div className="detail-section">
          <div className="detail-section-title">Financials</div>
          <div className="detail-stats">
            {m.budget !== null && (
              <div className="stat-item">
                <span className="stat-key">Budget</span>
                <span className="stat-val">${m.budget}M</span>
              </div>
            )}
            {m.gross !== null && (
              <div className="stat-item">
                <span className="stat-key">Gross</span>
                <span className="stat-val">${m.gross}M</span>
              </div>
            )}
            {m.roi !== null && (
              <div className="stat-item">
                <span className="stat-key">ROI</span>
                <span className="stat-val">{m.roi.toFixed(1)}×</span>
              </div>
            )}
          </div>
          <div className="detail-points financial">
            → Financial score: {m.financial_score > 0 ? `+${m.financial_score}` : m.financial_score} pts
          </div>
        </div>
      )}

      {m.who_watched && m.who_watched.length > 0 && (
        <div className="detail-section">
          <div className="detail-section-title">Watched by</div>
          <div className="detail-watched">{m.who_watched.join(', ')}</div>
          <div className="detail-points watch">
            → Watch points: +{m.watch_points} pts
          </div>
        </div>
      )}

      {m.penalties !== 0 && (
        <div className="detail-section">
          <div className="detail-section-title">Penalty</div>
          <div className="detail-watched">{m.penalty_notes}</div>
          <div className="detail-points penalty">
            → {m.penalties} pts
          </div>
        </div>
      )}

      <div className="detail-total-row">
        <span>Round total</span>
        <strong className={m.total > 0 ? 'positive' : m.total < 0 ? 'negative' : 'zero'}>
          {m.total > 0 ? `+${m.total}` : m.total} pts
        </strong>
      </div>
    </div>
  )
}

export default function MovieCard({ movie: m }) {
  const [open, setOpen] = useState(false)
  const isPending = m.imdb === null && m.gross === null && m.rt_crit === null

  function handleToggle() {
    if (!isPending) setOpen(o => !o)
  }

  return (
    <div
      className={`movie-card${isPending ? ' pending' : ''}${open ? ' expanded' : ''}`}
      onClick={handleToggle}
      role={isPending ? undefined : 'button'}
      tabIndex={isPending ? undefined : 0}
      aria-expanded={isPending ? undefined : open}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleToggle()
        }
      }}
    >
      <div className="movie-card-top">
        <span className="movie-round-badge">R{m.round}</span>
        <span className={`movie-title${isPending ? ' dim' : ''}`}>
          {m.movie || 'Not yet picked'}
        </span>
        <span className={`movie-pts ${m.total > 0 ? 'positive' : m.total < 0 ? 'negative' : 'zero'}`}>
          {isPending ? '—' : m.total > 0 ? `+${m.total}` : m.total || '—'}
        </span>
      </div>

      {!isPending && (
        <div className="movie-mini-chips">
          {m.rating_score !== 0 && (
            <span className="mini-chip rating">★ {m.rating_score > 0 ? `+${m.rating_score}` : m.rating_score}</span>
          )}
          {m.financial_score !== 0 && (
            <span className="mini-chip financial">$ {m.financial_score > 0 ? `+${m.financial_score}` : m.financial_score}</span>
          )}
          {m.watch_points !== 0 && (
            <span className="mini-chip watch">👁 +{m.watch_points}</span>
          )}
          {m.penalties !== 0 && (
            <span className="mini-chip penalty">⚠ {m.penalties}</span>
          )}
        </div>
      )}

      {open && <MovieDetail m={m} />}
    </div>
  )
}

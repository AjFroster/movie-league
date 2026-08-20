import { Fragment, useState } from 'react'

function statusFor(m) {
  if (!m.movie) return { dot: 'no-pick', label: 'NO PICK' }
  if (m.penalties !== 0) return { dot: 'at-risk', label: 'AT RISK' }
  if (m.imdb === null && m.gross === null && m.rt_crit === null) return { dot: 'awaiting', label: 'AWAITING SCORE' }
  return { dot: 'scored', label: 'SCORED' }
}

function MovieDetail({ m, ownerCount }) {
  // Supplied by GET /api/owners/{owner}; absent means an older payload, so render nothing
  // rather than recomputing the tiers here and risking drift from scoring.py.
  const breakdown = m.breakdown || []
  const ratingCaption = [
    m.rt_crit !== null ? `RT ${m.rt_crit}%` : null,
    m.rt_aud !== null ? `RT AUD ${m.rt_aud}%` : null,
    m.letterboxd !== null ? `LB ${m.letterboxd}` : null,
  ].filter(Boolean).join(' · ') || '—'

  const financialCaption = (m.budget === null && m.gross === null)
    ? '—'
    : `BUDGET $${m.budget ?? '—'}M / GROSS $${m.gross ?? '—'}M`

  const watchedNames = m.who_watched.length > 0 ? m.who_watched.join(', ') : 'Not yet watched'

  return (
    <div className="movie-detail">
      <div className="movie-hero" />
      <div className="movie-detail-title">{m.movie}</div>
      <div className="movie-detail-meta">R{m.round} · {m.owner}'s pick</div>

      <div className="stat-strip">
        <div className="stat-block">
          <span className="stat-block-label">ROUND TOTAL</span>
          <span className={`stat-block-value ${m.total > 0 ? 'positive' : m.total < 0 ? 'negative' : ''}`}>
            {m.total > 0 ? `+${m.total}` : m.total}
          </span>
          <span className="stat-block-caption">
            RATING {m.rating_score > 0 ? `+${m.rating_score}` : m.rating_score} · FIN {m.financial_score > 0 ? `+${m.financial_score}` : m.financial_score} · WATCH +{m.watch_points}
          </span>
        </div>
        <div className="stat-block">
          <span className="stat-block-label">RATING</span>
          <span className="stat-block-value">{m.imdb !== null ? m.imdb : '—'}</span>
          <span className="stat-block-caption">{ratingCaption}</span>
        </div>
        <div className="stat-block">
          <span className="stat-block-label">ROI</span>
          <span className="stat-block-value">{m.roi !== null ? `${m.roi.toFixed(2)}×` : '—'}</span>
          <span className="stat-block-caption">{financialCaption}</span>
        </div>
        <div className="stat-block">
          <span className="stat-block-label">WATCHED</span>
          <span className="stat-block-value">{m.who_watched.length}/{ownerCount}</span>
          <span className="stat-block-caption">{watchedNames}</span>
        </div>
      </div>

      <div className="detail-columns">
        <div className="detail-col">
          <div className="detail-section-title">SCORE BREAKDOWN</div>
          {breakdown.length === 0 ? (
            <div className="stat-block-caption">No score entered yet.</div>
          ) : (
            <table className="breakdown-table">
              <thead>
                <tr><th>Source</th><th>Value</th><th>Tier</th><th className="num">Pts</th></tr>
              </thead>
              <tbody>
                {GROUPS.map(g => {
                  const rows = breakdown.filter(r => r.group === g.key)
                  if (rows.length === 0) return null
                  const subtotal = rows.reduce((n, r) => n + r.points, 0)
                  return (
                    <Fragment key={g.key}>
                      {rows.map(r => (
                        <tr key={r.label} className={r.points === 0 ? 'zero' : ''}>
                          <td>{r.label}</td>
                          <td className="val">{r.value}</td>
                          <td className="tier">{r.tier}</td>
                          <td className={`num ${r.points > 0 ? 'positive' : r.points < 0 ? 'negative' : ''}`}>
                            {r.points > 0 ? `+${r.points}` : r.points}
                          </td>
                        </tr>
                      ))}
                      <tr className="subtotal">
                        <td colSpan={3}>{g.label}</td>
                        <td className={`num ${subtotal > 0 ? 'positive' : subtotal < 0 ? 'negative' : ''}`}>
                          {subtotal > 0 ? `+${subtotal}` : subtotal}
                        </td>
                      </tr>
                    </Fragment>
                  )
                })}
                <tr className="grand-total">
                  <td colSpan={3}>ROUND TOTAL</td>
                  <td className={`num ${m.total > 0 ? 'positive' : m.total < 0 ? 'negative' : ''}`}>
                    {m.total > 0 ? `+${m.total}` : m.total}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
          {m.penalties !== 0 && m.penalty_notes && (
            <div className="penalty-note">{m.penalty_notes}</div>
          )}
        </div>

        <div className="detail-col">
          <div className="detail-section-title">CAMPAIGN TRACKER</div>
          <div className="illustrative-note">Illustrative — not live data</div>
          <div className="campaign-tracker">
            <div className="tracker-item">
              <span className="tracker-dot amber" />
              <div>
                <div className="tracker-headline">Movie picked</div>
                <div className="tracker-detail">Selected for this round</div>
              </div>
            </div>
            <div className="tracker-item">
              <span className="tracker-dot blue" />
              <div>
                <div className="tracker-headline">Scores entered</div>
                <div className="tracker-detail">Manual entry after release</div>
              </div>
            </div>
            <div className="tracker-item">
              <span className="tracker-dot gray" />
              <div>
                <div className="tracker-headline">TMDB enrichment available</div>
                <div className="tracker-detail">Budget & gross can be pulled from TMDB</div>
              </div>
            </div>
          </div>
        </div>

        <div className="detail-col">
          <div className="detail-section-title">LEAGUE OWNERSHIP</div>
          <div className="ownership-callout">
            Picked by <strong>{m.owner}</strong> · Round {m.round}
          </div>
        </div>
      </div>
    </div>
  )
}

const GROUPS = [
  { key: 'rating', label: 'Rating subtotal' },
  { key: 'financial', label: 'Financial subtotal' },
  { key: 'penalty', label: 'Penalties' },
  { key: 'watch', label: 'Watch points' },
]

export default function MovieCard({ movie: m, ownerCount }) {
  const [open, setOpen] = useState(false)
  const isPending = m.imdb === null && m.gross === null && m.rt_crit === null
  const status = statusFor(m)

  function handleToggle() {
    if (!isPending) setOpen(o => !o)
  }

  return (
    <>
      <div
        className={`roster-row${isPending ? ' pending' : ''}${open ? ' expanded' : ''}`}
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
        <span className="roster-col-round">R{m.round}</span>
        <span className={`roster-col-title${!m.movie ? ' dim' : ''}`}>{m.movie || 'Not yet picked'}</span>
        <span className="status-pill">
          <span className={`status-dot ${status.dot}`} />
          <span className="status-label">{status.label}</span>
        </span>
        <span className={`roster-col-pts ${m.total > 0 ? 'positive' : m.total < 0 ? 'negative' : 'zero'}`}>
          {!m.movie ? '—' : (m.total > 0 ? `+${m.total}` : m.total)}
        </span>
        <span className="roster-col-watched">{m.who_watched.length}/{ownerCount}</span>
      </div>
      {open && <MovieDetail m={m} ownerCount={ownerCount} />}
    </>
  )
}

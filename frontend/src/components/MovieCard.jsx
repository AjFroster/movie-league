import { useState } from 'react'

function statusFor(m) {
  if (!m.movie) return { dot: 'no-pick', label: 'NO PICK' }
  if (m.penalties !== 0) return { dot: 'at-risk', label: 'AT RISK' }
  if (m.imdb === null && m.gross === null && m.rt_crit === null) return { dot: 'awaiting', label: 'AWAITING SCORE' }
  return { dot: 'scored', label: 'SCORED' }
}

function MovieDetail({ m, ownerCount }) {
  // Placeholder — Task 2 replaces this body with the full expanded panel
  // (hero, meta, stat strip, points ledger, campaign tracker, ownership callout).
  return (
    <div className="movie-detail">
      <div>{m.total} pts</div>
    </div>
  )
}

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

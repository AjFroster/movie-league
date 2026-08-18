export default function OwnerDetail({ movies }) {
  if (!movies) return <div className="detail state-msg">Loading rounds…</div>

  return (
    <div className="detail">
      {movies.map((m) => (
        <div className="round-row" key={m.round}>
          <span className="round-num">R{m.round}</span>
          <span className={`movie-name ${m.imdb === null ? 'blank' : ''}`}>
            {m.movie || 'Not yet picked'}
          </span>
          <span className="round-total">
            {m.imdb === null ? '—' : (m.total > 0 ? `+${m.total}` : m.total)}
          </span>
          {m.penalty_notes ? (
            <span className="penalty-note">{m.penalty_notes}</span>
          ) : null}
        </div>
      ))}
    </div>
  )
}

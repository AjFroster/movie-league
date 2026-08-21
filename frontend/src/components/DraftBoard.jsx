import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

function formatDate(iso) {
  if (!iso) return 'TBA'
  const [y, m, d] = iso.split('-').map(Number)
  const month = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'][m - 1]
  return `${month} ${d}, ${y}`
}

/** Poster or a placeholder of the same dimensions.
 *  Most films a year or more out have no artwork, so the empty case is the common one and
 *  has to hold its space -- a missing image that collapses would reflow the whole list. */
function Poster({ film }) {
  const [failed, setFailed] = useState(false)
  if (!film.poster_url || failed) {
    return <span className="poster poster-empty" aria-hidden="true">NO<br />ART</span>
  }
  return (
    <img className="poster" src={film.poster_url} alt=""
         loading="lazy" onError={() => setFailed(true)} />
  )
}

function SetupState({ state, onStart, starting, error }) {
  return (
    <div className="draft-setup">
      <div className="setup-main">
        <span className="field-label">Draft order</span>
        <div className="setup-headline">Not drawn</div>
        <p className="setup-body">
          Starting the draft shuffles all {state.order.length} players into a random order
          and locks it. The order cannot be edited once the draft is running, and there is
          no undo — do this with everyone in the room.
        </p>
        {error && <p className="field-error" role="alert">{error}</p>}
        <div className="setup-actions">
          <button className="btn btn-primary" onClick={onStart} disabled={starting}>
            {starting ? 'RANDOMIZING…' : 'START DRAFT · RANDOMIZE ORDER'}
          </button>
          <span className="warn-inline">CANNOT BE UNDONE</span>
        </div>
      </div>
      <aside className="setup-aside">
        <span className="field-label">Players in the draw</span>
        <ul className="draw-list">
          {state.order.map((player) => (
            <li key={player}>
              <span className="draw-dash">—</span>
              <span className="draw-name">{player}</span>
              <span className="draw-picks">0 picks</span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}

function SnakeGrid({ state }) {
  const clock = state.on_the_clock
  return (
    // The column count is the player count; auto-fit cannot infer it and silently
    // collapses the grid into a single vertical column.
    <div className="snake" style={{ '--players': state.order.length }}>
      <div className="snake-head">
        <span className="snake-head-label">Snake order</span>
        <span className="field-hint">Reverses each round</span>
      </div>
      {state.board.map((row) => (
        <div className="snake-row" key={row.round}>
          <span className={`snake-round${clock && clock.round === row.round ? ' current' : ''}`}>
            <span className="snake-round-label">RD {row.round}</span>
            <span className="snake-direction">{row.direction}</span>
          </span>
          {row.cells.map((cell) => {
            const isNow = clock && clock.pick === cell.pick
            const done = cell.pick <= state.picks_made
            return (
              <span
                key={cell.pick}
                className={`snake-cell${isNow ? ' now' : ''}${done ? ' done' : ''}`}
              >
                <span className="snake-player">{cell.player}</span>
                <span className="snake-pick">
                  {isNow ? 'NOW' : String(cell.pick).padStart(2, '0')}
                </span>
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function CompleteState({ state, onStandings, onExit, onScore, scoring, scored }) {
  return (
    <section className="draft-done">
      <span className="field-label">Draft complete</span>
      <div className="done-headline">{state.name}</div>
      <p className="done-body">
        All {state.total_picks} picks are in and every roster is final. The draft order is
        locked and cannot be re-run.
      </p>
      {scored && (
        <p className="done-body">
          {scored.fields_updated} fields filled from {scored.api_calls_used} API calls
          {scored.unmatched?.length ? `, ${scored.unmatched.length} film(s) unmatched` : ''}.
        </p>
      )}
      <div className="setup-actions">
        <button className="btn btn-primary" onClick={onStandings}>VIEW STANDINGS</button>
        <button className="btn" onClick={onScore} disabled={scoring}>
          {scoring ? 'FETCHING RATINGS…' : 'FETCH RATINGS & SCORE'}
        </button>
        <button className="btn" onClick={onExit}>BACK TO LEAGUES</button>
      </div>
      <p className="summary-note">
        A season this far out has no ratings yet, so every score starts at zero. Fetching
        pulls whatever exists today; run it again whenever films release.
      </p>
    </section>
  )
}

export default function DraftBoard({ leagueId, onExit, onFinished, onStandings }) {
  const [state, setState] = useState(null)
  const [films, setFilms] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [rejected, setRejected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [scoringNow, setScoringNow] = useState(false)
  const [scored, setScored] = useState(null)

  useEffect(() => {
    api.draft(leagueId).then(setState).catch((e) => setError(e.message))
  }, [leagueId])

  useEffect(() => {
    if (!state || state.status === 'setup') return
    api.pool(leagueId).then((r) => setFilms(r.films)).catch((e) => setError(e.message))
  }, [leagueId, state?.status])

  // Debounced so typing a title does not fire a request per keystroke.
  useEffect(() => {
    if (!query.trim()) { setResults(null); return }
    const timer = setTimeout(() => {
      api.poolSearch(leagueId, query).then((r) => setResults(r.films)).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [query, leagueId])

  async function start() {
    setBusy(true)
    setError(null)
    try {
      setState(await api.startDraft(leagueId))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function scoreLeague() {
    setScoringNow(true)
    try {
      setScored(await api.leagueEnrich(leagueId))
    } catch (e) {
      setError(e.message)
    } finally {
      setScoringNow(false)
    }
  }

  async function pick(film) {
    const player = state.on_the_clock?.player
    if (!player || busy) return
    setBusy(true)
    setRejected(null)
    try {
      const next = await api.makePick(leagueId, player, film.tmdb_id, film.title,
                                      film.poster_path)
      setState(next)
      // Refresh the pool so the film shows as taken, by whom, at which pick.
      const refreshed = await api.pool(leagueId)
      setFilms(refreshed.films)
      if (results) {
        const again = await api.poolSearch(leagueId, query)
        setResults(again.films)
      }
      if (next.status === 'complete') onFinished?.(next)
    } catch (e) {
      // A rejection means someone else took the film or it is not this player's turn.
      // Both are recoverable, so the board stays exactly where it was and explains.
      setRejected(e.message)
      const [next, refreshed] = await Promise.all([
        api.draft(leagueId), api.pool(leagueId),
      ])
      setState(next)
      setFilms(refreshed.films)
    } finally {
      setBusy(false)
    }
  }

  const shown = results ?? films
  const clock = state?.on_the_clock
  const percent = useMemo(() => (
    state && state.total_picks
      ? Math.round((state.picks_made / state.total_picks) * 100) : 0
  ), [state])

  if (error && !state) return <div className="state-msg" role="alert">{error}</div>
  if (!state) return <div className="state-msg">Loading draft…</div>

  return (
    <div className="draft-page">
      <header className="draft-header">
        <div className="draft-identity">
          <button className="linkish" onClick={onExit}>Leagues</button>
          <h1 className="draft-name">{state.name}</h1>
          <span className="league-status">
            <span className={`status-dot ${state.status}`} />
            {state.status.toUpperCase()}
          </span>
        </div>
        {state.status !== 'setup' && (
          <div className="draft-progress">
            <span className="field-label">
              {state.picks_made} of {state.total_picks} picks made
            </span>
            <span className="league-progress-bar">
              <span className="league-progress-fill" style={{ width: `${percent}%` }} />
            </span>
          </div>
        )}
      </header>

      {state.status === 'setup' ? (
        <SetupState state={state} onStart={start} starting={busy} error={error} />
      ) : state.status === 'complete' ? (
        <CompleteState
          state={state}
          scored={scored}
          scoring={scoringNow}
          onScore={scoreLeague}
          onStandings={() => onStandings(leagueId, state.name)}
          onExit={onExit}
        />
      ) : (
        <>
          <section className="clock-strip">
            <div className="clock-main">
              <span className="field-label">
                {clock ? 'On the clock' : 'Draft complete'}
              </span>
              <div className="clock-name">{clock ? clock.player : 'All picks in'}</div>
              {clock && (
                <div className="clock-detail">
                  ROUND {clock.round} · PICK {clock.pick} OF {state.total_picks} ·
                  SLOT {clock.slot}
                </div>
              )}
              {clock?.back_to_back && (
                <p className="clock-note">
                  {clock.player} picks now and again at the top of round {clock.round + 1}
                  {' '}— back-to-back.
                </p>
              )}
            </div>

            {rejected ? (
              <div className="reject-panel" role="alert">
                <span className="reject-title">
                  <span className="status-dot at-risk" />Pick not saved
                </span>
                <p className="reject-body">
                  {rejected} Nothing else changed — the board is still on {clock?.player}.
                </p>
                <div className="reject-actions">
                  <button className="btn" onClick={() => setRejected(null)}>
                    BACK TO THE POOL
                  </button>
                </div>
              </div>
            ) : state.upcoming.length > 0 && (
              <div className="upcoming">
                <span className="field-label">Then, in order</span>
                {state.upcoming.map((slot) => (
                  <div className="upcoming-row" key={slot.pick}>
                    <span className="upcoming-pick">
                      PICK {String(slot.pick).padStart(2, '0')}
                    </span>
                    <span className="upcoming-player">{slot.player}</span>
                    <span className="upcoming-tag">
                      {slot.back_to_back ? `ROUND ${slot.round} ENDS · BACK-TO-BACK`
                        : slot.round_ends ? `ROUND ${slot.round} ENDS`
                        : `ROUND ${slot.round}`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <div className="draft-columns">
            <aside className="draft-left"><SnakeGrid state={state} /></aside>

            <section className="draft-pool">
              <div className="pool-head">
                <input
                  className="input"
                  placeholder={`Search ${films ? films.length : ''} films for ${state.year}…`}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <span className="field-hint">By anticipation</span>
              </div>

              <div className="pool-row pool-head-row">
                <span>Rank</span><span /><span>Film</span>
                <span>Release</span><span className="num">Status</span>
              </div>

              {!shown && <div className="state-msg">Loading films…</div>}
              {shown && shown.length === 0 && (
                <div className="state-msg">No films match “{query}”.</div>
              )}
              {shown && shown.map((film, index) => (
                <div className={`pool-row${film.drafted ? ' taken' : ''}`} key={film.tmdb_id}>
                  <span className="pool-rank">{String(index + 1).padStart(2, '0')}</span>
                  <Poster film={film} />
                  <span className="pool-film">
                    <span className="pool-title">{film.title}</span>
                    <span className="pool-sub">
                      {film.drafted
                        ? `TAKEN — ${film.taken_by} · PICK ${film.taken_at_pick}`
                        : film.poster_url ? '' : 'NO ARTWORK YET'}
                    </span>
                  </span>
                  <span className="pool-release">{formatDate(film.release_date)}</span>
                  <span className="num">
                    {film.drafted ? (
                      <span className="taken-badge">DRAFTED</span>
                    ) : clock ? (
                      <button className="btn btn-primary btn-small"
                              disabled={busy} onClick={() => pick(film)}>
                        DRAFT
                      </button>
                    ) : null}
                  </span>
                </div>
              ))}
            </section>

            <aside className="draft-right">
              <span className="field-label">Rosters</span>
              {state.rosters.map((roster) => (
                <div className="roster" key={roster.player}>
                  <div className="roster-head">
                    <span className={`roster-name${clock && clock.player === roster.player
                      ? ' current' : ''}`}>{roster.player}</span>
                    <span className="roster-count">{roster.count} / {roster.of}</span>
                  </div>
                  {roster.picks.map((p) => (
                    <div className="roster-pick" key={p.pick}>
                      <span className="roster-pick-no">
                        {String(p.pick).padStart(2, '0')}
                      </span>
                      <span className="roster-title">{p.title}</span>
                    </div>
                  ))}
                </div>
              ))}
            </aside>
          </div>
        </>
      )}
    </div>
  )
}

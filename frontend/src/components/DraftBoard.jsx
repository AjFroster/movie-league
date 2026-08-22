import { useEffect, useMemo, useRef, useState } from 'react'
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

/** Seconds left on the current pick, recomputed from the server's deadline every tick.
 *  Not a local countdown: a refresh, a slow load, or a sleeping laptop would all drift a
 *  browser-owned stopwatch, and the deadline has to be the same for everyone in the room. */
const POLL_MS = 2000

/** Keeps the board in step with everyone else's picks.
 *
 *  Polling rather than a socket: a draft is six people and a pick every minute or two, so
 *  a 2-second poll is indistinguishable from live and runs on any host. The request is
 *  conditional, so a poll that finds nothing sends no body and triggers no re-render --
 *  without that, the board would rebuild every two seconds and lose text selection,
 *  hover, and any open dropdown mid-draft.
 *
 *  Stops while the tab is hidden, and refetches the moment it comes back. A backgrounded
 *  phone should not queue up requests it will throw away, and should be current the
 *  instant you look at it.
 */
function useLiveDraft(leagueId, state, setState) {
  const etag = useRef(null)
  const active = state?.status === 'drafting'

  useEffect(() => {
    if (!active) return

    let stopped = false
    const poll = async () => {
      if (stopped || document.hidden) return
      try {
        const result = await api.draftIfChanged(leagueId, etag.current)
        if (stopped) return
        etag.current = result.etag
        if (result.changed) setState(result.data)
      } catch {
        // A failed poll is not worth reporting: the next one is two seconds away, and an
        // error banner that appears and vanishes on a flaky connection is worse than
        // silence. A pick that fails still reports, because that one the user asked for.
      }
    }

    const timer = setInterval(poll, POLL_MS)
    // A tab returning to the foreground should be current immediately, not in two seconds.
    const onVisible = () => { if (!document.hidden) poll() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      stopped = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [leagueId, active, setState])
}


/** The draftable pool, plus the search over it.
 *
 *  Three pieces of state that only ever move together: the full pool, the query, and the
 *  matches for it. `shown` is what the board renders -- matches when searching, the whole
 *  pool otherwise.
 */
function useFilmPool(leagueId, active, onError) {
  const [films, setFilms] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)

  const load = () => api.pool(leagueId)
    .then((r) => { setFilms(r.films); return r.films })
    .catch((e) => onError(e.message))

  useEffect(() => {
    if (active) load()
  }, [leagueId, active])

  // Debounced so typing a title does not fire a request per keystroke.
  useEffect(() => {
    if (!query.trim()) { setResults(null); return }
    const timer = setTimeout(() => {
      api.poolSearch(leagueId, query).then((r) => setResults(r.films)).catch(() => {})
    }, 300)
    return () => clearTimeout(timer)
  }, [query, leagueId])

  /** Re-read the pool after a pick, keeping any active search in step. */
  async function refresh() {
    await load()
    if (results) {
      const again = await api.poolSearch(leagueId, query)
      setResults(again.films)
    }
  }

  return { films, query, setQuery, shown: results ?? films, refresh }
}


function useClock(state, onExpire) {
  const [left, setLeft] = useState(null)

  useEffect(() => {
    if (!state || state.status !== 'drafting' || !state.pick_seconds
        || !state.clock_started_at) {
      setLeft(null)
      return
    }
    const deadline = new Date(state.clock_started_at).getTime()
      + state.pick_seconds * 1000
    // Ask repeatedly while overdue rather than once at zero. Client and server clocks
    // differ by a fraction, so a single shot at 0:00 gets "not yet" from the server and
    // then never retries -- which is exactly what left a draft stuck on TIME.
    let asking = false
    let lastAsk = 0
    const tick = () => {
      const seconds = Math.round((deadline - Date.now()) / 1000)
      setLeft(seconds)
      if (seconds > 0 || asking || Date.now() - lastAsk < 2000) return
      asking = true
      lastAsk = Date.now()
      Promise.resolve(onExpire?.()).finally(() => { asking = false })
    }
    tick()
    const id = setInterval(tick, 250)
    return () => clearInterval(id)
  }, [state?.clock_started_at, state?.pick_seconds, state?.status, state?.picks_made])

  return left
}

function Clock({ left, seconds }) {
  if (left === null) return null
  const overdue = left <= 0
  const urgent = !overdue && left <= Math.max(10, seconds * 0.2)
  const shown = Math.abs(left)
  return (
    <div className={`clock-timer${overdue ? ' overdue' : urgent ? ' urgent' : ''}`}>
      <span className="clock-digits">
        {overdue ? 'TIME' : `${Math.floor(shown / 60)}:${String(shown % 60).padStart(2, '0')}`}
      </span>
      <span className="clock-timer-label">
        {overdue ? 'auto-picking…' : 'on the clock'}
      </span>
    </div>
  )
}

export default function DraftBoard({ leagueId, onExit, onFinished, onStandings }) {
  const [state, setState] = useState(null)
  const [error, setError] = useState(null)
  const [rejected, setRejected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [scoringNow, setScoringNow] = useState(false)
  const [scored, setScored] = useState(null)
  const [autopicked, setAutopicked] = useState(null)
  useLiveDraft(leagueId, state, setState)
  const pool = useFilmPool(leagueId, Boolean(state) && state?.status !== 'setup',
                           (message) => setError(message))
  const { films, query, setQuery, shown } = pool

  async function expire() {
    if (busy) return
    setBusy(true)
    try {
      const result = await api.autopick(leagueId)
      setAutopicked(result.autopicked)
      setState(result)
      await pool.refresh()
      if (result.status === 'complete') onFinished?.(result)
    } catch (e) {
      // 409 means the player picked in the moment the clock ran out -- their pick wins,
      // so re-read rather than treating it as a failure.
      const next = await api.draft(leagueId).catch(() => null)
      if (next) setState(next)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    api.draft(leagueId).then(setState).catch((e) => setError(e.message))
  }, [leagueId])


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
      await pool.refresh()
      if (next.status === 'complete') onFinished?.(next)
    } catch (e) {
      // A rejection means someone else took the film or it is not this player's turn.
      // Both are recoverable, so the board stays exactly where it was and explains.
      setRejected(e.message)
      const [next] = await Promise.all([api.draft(leagueId), pool.refresh()])
      setState(next)
    } finally {
      setBusy(false)
    }
  }

  const secondsLeft = useClock(state, expire)
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
              <div className="clock-headline">
                <div className="clock-name">{clock ? clock.player : 'All picks in'}</div>
                <Clock left={secondsLeft} seconds={state.pick_seconds} />
              </div>
              {autopicked && (
                <p className="clock-note autopicked">
                  Time ran out — {autopicked.player} was given {autopicked.title}.
                </p>
              )}
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

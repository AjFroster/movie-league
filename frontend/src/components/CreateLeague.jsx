import { useEffect, useState } from 'react'
import { api } from '../api.js'

const YEARS = [2026, 2027]
const MIN_PLAYERS = 2
const MAX_PLAYERS = 20
const SECONDS_PER_PICK = 60

export default function CreateLeague({ onCreated, onCancel }) {
  const [name, setName] = useState('Movie League 2027')
  const [year, setYear] = useState(2027)
  const [rounds, setRounds] = useState(6)
  const [players, setPlayers] = useState([])
  const [draftName, setDraftName] = useState('')
  const [nameError, setNameError] = useState(null)
  const [poolCount, setPoolCount] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Quoted while the year is still being chosen, so it cannot be league-scoped.
  useEffect(() => {
    let current = true
    setPoolCount(null)
    api.poolSize(year)
      .then((r) => { if (current) setPoolCount(r.count) })
      .catch(() => { if (current) setPoolCount(null) })
    return () => { current = false }
  }, [year])

  function addPlayer() {
    const candidate = draftName.trim()
    if (!candidate) return
    // Case-insensitive, matching the server's rule -- better to say so here than to have
    // the create request rejected after everything else has been filled in.
    if (players.some((p) => p.toLowerCase() === candidate.toLowerCase())) {
      setNameError(`${candidate} is already in this league. Names have to be unique.`)
      return
    }
    if (players.length >= MAX_PLAYERS) {
      setNameError(`A draft supports at most ${MAX_PLAYERS} players.`)
      return
    }
    setPlayers([...players, candidate])
    setDraftName('')
    setNameError(null)
  }

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      const state = await api.createLeague({ name, year, players, rounds })
      onCreated(state)
    } catch (e) {
      setError(e.message)
      setSubmitting(false)
    }
  }

  const totalPicks = players.length * rounds
  const minutes = Math.round((totalPicks * SECONDS_PER_PICK) / 60)
  const ready = players.length >= MIN_PLAYERS && name.trim().length > 0

  return (
    <div className="create-page">
      <header className="create-header">
        <nav className="breadcrumb">
          <button className="linkish" onClick={onCancel}>Leagues</button>
          <span> / </span><span className="breadcrumb-current">New</span>
        </nav>
        <h1 className="create-title">CREATE LEAGUE</h1>
      </header>

      <div className="create-body">
        <div className="create-form">
          <label className="field">
            <span className="field-label">League name</span>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </label>

          <div className="field-row">
            <div className="field">
              <span className="field-label">Year</span>
              <div className="segmented">
                {YEARS.map((y) => (
                  <button
                    key={y}
                    className={`segment${y === year ? ' selected' : ''}`}
                    onClick={() => setYear(y)}
                  >
                    {y}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <span className="field-label">Rounds <span className="field-hint">1–30</span></span>
              <div className="stepper">
                <button className="step" onClick={() => setRounds(Math.max(1, rounds - 1))}>−</button>
                <span className="step-value">{rounds}</span>
                <button className="step" onClick={() => setRounds(Math.min(30, rounds + 1))}>+</button>
              </div>
            </div>
          </div>

          <div className="field">
            <span className="field-label">
              Players
              <span className="field-hint">
                {players.length} of {MAX_PLAYERS} · min {MIN_PLAYERS}
              </span>
            </span>
            <div className="add-row">
              <input
                className={`input${nameError ? ' invalid' : ''}`}
                value={draftName}
                placeholder="Add a player"
                onChange={(e) => { setDraftName(e.target.value); setNameError(null) }}
                onKeyDown={(e) => e.key === 'Enter' && addPlayer()}
              />
              <button className="btn" onClick={addPlayer}>ADD</button>
            </div>
            {nameError && <p className="field-error" role="alert">{nameError}</p>}

            <ul className="player-list">
              {players.map((player, index) => (
                <li className="player-row" key={player}>
                  <span className="player-index">{String(index + 1).padStart(2, '0')}</span>
                  <span className="player-label">{player}</span>
                  <button
                    className="player-remove"
                    aria-label={`Remove ${player}`}
                    onClick={() => setPlayers(players.filter((p) => p !== player))}
                  >×</button>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <aside className="create-summary">
          <span className="field-label">Total picks</span>
          <div className="summary-figure">{totalPicks || '—'}</div>
          <p className="summary-formula">
            {players.length} player{players.length === 1 ? '' : 's'} × {rounds} rounds
          </p>
          {totalPicks > 0 && (
            <p className="summary-note">
              At roughly a minute a pick, that is about a {minutes}-minute draft.
            </p>
          )}

          <dl className="summary-facts">
            <div><dt>Picks per player</dt><dd>{rounds}</dd></div>
            <div><dt>Draft format</dt><dd>SNAKE</dd></div>
            <div><dt>Film pool · {year}</dt>
              <dd>{poolCount === null ? '…' : poolCount}</dd></div>
          </dl>

          <p className="summary-note">
            Creating the league does not start the draft. You will start it — and randomize
            the order — from the league screen when everyone is together.
          </p>
          {error && <p className="field-error" role="alert">{error}</p>}
          <button
            className="btn btn-primary btn-block"
            disabled={!ready || submitting}
            onClick={submit}
          >
            {submitting ? 'CREATING…' : 'CREATE LEAGUE'}
          </button>
        </aside>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { saveBlob } from '../download.js'
import { AccountBadge, accountsEnabled } from '../auth.jsx'

const STATUS_LABEL = { setup: 'SETUP', drafting: 'DRAFTING', complete: 'COMPLETE' }

function ordinalSuffix(n) {
  return n === 1 ? '' : 's'
}

/** Progress means different things before and after a draft finishes.
 *  Mid-draft the number that matters is picks; once every slot is filled the season is
 *  running and the live number becomes how many films have ratings in yet. */
function progressFor(league) {
  if (league.frozen_at) {
    const on = new Date(league.frozen_at).toLocaleDateString()
    return { done: league.films_scored, total: league.films_total,
             caption: `Final · settled ${on} · scores no longer update` }
  }
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
  const [editing, setEditing] = useState(null)      // league id being renamed
  const [draftName, setDraftName] = useState('')
  const [confirming, setConfirming] = useState(null) // league id awaiting delete confirm
  const [saving, setSaving] = useState(null)        // 'all' or a league id, while exporting
  // Deliberately NOT the page-level `error`: that one replaces the whole list with a
  // dead-end message, which is right for "the backend is unreachable" and badly wrong for
  // "one download failed" -- the leagues are still there and still worth showing.
  const [saveError, setSaveError] = useState(null)

  const reload = () => api.leagues().then(setLeagues).catch((e) => setError(e.message))

  async function saveName(league) {
    const name = draftName.trim()
    if (!name || name === league.name) { setEditing(null); return }
    try {
      await api.renameLeague(league.id, name)
      setEditing(null)
      await reload()
    } catch (e) {
      setError(e.message)
    }
  }

  async function saveSettleDate(league, value) {
    if (!value || value === league.settles_on) return
    try {
      await api.setSettlesOn(league.id, value)
      await reload()
    } catch (e) {
      setError(e.message)
    }
  }

  async function savePickSeconds(league, value) {
    const seconds = Number(value)
    if (Number.isNaN(seconds) || seconds === league.pick_seconds) return
    try {
      await api.setPickSeconds(league.id, seconds)
      await reload()
    } catch (e) {
      setError(e.message)
    }
  }

  async function toggleFreeze(league) {
    try {
      await api.freezeLeague(league.id, !league.frozen_at)
      await reload()
    } catch (e) {
      setError(e.message)
    }
  }

  /** `league` omitted means the whole database -- the backup. */
  async function exportData(league) {
    const key = league ? league.id : 'all'
    setSaving(key)
    setSaveError(null)
    try {
      saveBlob(league ? await api.exportLeague(league.id) : await api.exportArchive())
    } catch (e) {
      setSaveError(`Couldn't export: ${e.message}`)
    } finally {
      setSaving(null)
    }
  }

  async function toggleVisibility(league) {
    setSaveError(null)
    try {
      await api.setVisibility(league.id, league.visibility === 'public' ? 'private' : 'public')
      await reload()
    } catch (e) {
      setSaveError(e.message)
    }
  }

  async function claim(league, player) {
    setSaveError(null)
    try {
      await api.claimSlot(league.id, player)
      await reload()
    } catch (e) {
      setSaveError(e.message)
    }
  }

  async function release(league, player) {
    setSaveError(null)
    try {
      await api.releaseSlot(league.id, player)
      await reload()
    } catch (e) {
      setSaveError(e.message)
    }
  }

  async function remove(league) {
    try {
      await api.deleteLeague(league.id)
      setConfirming(null)
      await reload()
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => { reload() }, [])

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
        <span className="header-actions">
          <button
            className="btn"
            disabled={saving === 'all' || leagues.length === 0}
            title="Download every league as a restorable JSON file"
            onClick={() => exportData(null)}
          >
            {saving === 'all' ? 'SAVING…' : 'BACK UP'}
          </button>
          <button className="btn" onClick={onCreate}>NEW LEAGUE</button>
          <AccountBadge />
        </span>
      </header>

      {saveError && (
        <div className="card-error" role="alert">
          {saveError}
          <button className="btn btn-small" onClick={() => setSaveError(null)}>DISMISS</button>
        </div>
      )}

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
                  {/* Only meaningful once there are real accounts. In local mode there is
                      one user, so "which slot are you" has no answer worth asking for. */}
                  {accountsEnabled && (
                    league.your_player ? (
                      <span className="claim-strip">
                        Playing as <strong>{league.your_player}</strong>
                        <button
                          className="btn btn-small"
                          title="Give this slot back"
                          onClick={() => release(league, league.your_player)}
                        >RELEASE</button>
                      </span>
                    ) : league.unclaimed?.length > 0 ? (
                      <span className="claim-strip">
                        Claim your slot:
                        {league.unclaimed.map((name) => (
                          <button key={name} className="btn btn-small"
                                  onClick={() => claim(league, name)}>{name}</button>
                        ))}
                      </span>
                    ) : null
                  )}
                  {editing === league.id ? (
                    <input
                      className="input input-inline"
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onBlur={() => saveName(league)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveName(league)
                        if (e.key === 'Escape') setEditing(null)
                      }}
                    />
                  ) : (
                    <button
                      className="league-name league-name-button"
                      title="Rename"
                      onClick={() => { setEditing(league.id); setDraftName(league.name) }}
                    >
                      {league.name}
                    </button>
                  )}
                  <span className="league-meta">
                    <button
                      className={`visibility-pill ${league.visibility}`}
                      title={league.visibility === 'public'
                        ? 'Anyone with the link can view the standings. Click to make private.'
                        : 'Only league members can view this. Click to make it public.'}
                      onClick={() => toggleVisibility(league)}
                    >
                      {league.visibility === 'public' ? 'PUBLIC' : 'PRIVATE'}
                    </button>
                    {' · '}
                    {progress.caption}
                    {league.status !== 'complete' && (
                      <>
                        {' · '}
                        <select
                          className="settle-date"
                          value={league.pick_seconds}
                          title="Seconds each player gets on the clock"
                          onChange={(e) => savePickSeconds(league, e.target.value)}
                        >
                          {[0, 30, 60, 120, 300].map((s) => (
                            <option key={s} value={s}>
                              {s === 0 ? 'untimed' : `${s}s per pick`}
                            </option>
                          ))}
                        </select>
                      </>
                    )}
                    {!league.frozen_at && (
                      <>
                        {' · books close '}
                        <input
                          type="date"
                          className="settle-date"
                          value={league.settles_on || ''}
                          title="When this season's scores stop updating"
                          onChange={(e) => saveSettleDate(league, e.target.value)}
                        />
                      </>
                    )}
                  </span>
                </span>
                <span className="league-year">{league.year}</span>
                <span className="league-status">
                  <span className={`status-dot ${league.frozen_at ? 'frozen' : league.status}`} />
                  {league.frozen_at ? 'FINAL' : STATUS_LABEL[league.status]}
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
                  {confirming === league.id ? (
                    <span className="confirm-strip">
                      <span className="confirm-text">
                        Delete “{league.name}” and its {league.picks_made} picks?
                      </span>
                      <button className="btn btn-danger" onClick={() => remove(league)}>
                        DELETE
                      </button>
                      <button className="btn" onClick={() => setConfirming(null)}>
                        CANCEL
                      </button>
                    </span>
                  ) : (
                    <>
                      <button
                        className="league-export"
                        title={`Download “${league.name}” as JSON`}
                        disabled={saving === league.id}
                        onClick={() => exportData(league)}
                      >{saving === league.id ? '…' : '↓'}</button>
                      <button
                        className="league-delete"
                        title="Delete league"
                        onClick={() => setConfirming(league.id)}
                      >×</button>
                    </>
                  )}
                  {(league.frozen_at || (league.season_ended
                    && league.status === 'complete')) && (
                    <button
                      className="btn btn-small"
                      title={league.frozen_at
                        ? 'Reopen so scores update again'
                        : 'Settle this season so its scores stop moving'}
                      onClick={() => toggleFreeze(league)}
                    >
                      {league.frozen_at ? 'REOPEN' : 'SETTLE SEASON'}
                    </button>
                  )}
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

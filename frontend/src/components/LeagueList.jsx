import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { saveBlob } from '../download.js'
import { AuthPanel, accountsEnabled, useSignedIn } from '../auth.jsx'
import LeagueRow from './LeagueRow.jsx'
import SupportLink from './SupportLink.jsx'
import { ordinalSuffix } from './leagueDisplay.js'

/** The rows plus their header. Module scope, not defined during render. */
function LeagueTable({ rows, newest, editing, draftName, saving, confirming, on }) {
  return (
    <div className="league-table">
      <div className="league-row league-head">
        <span>League</span><span>Year</span><span>Status</span>
        <span className="num">Players</span><span>Draft progress</span><span />
      </div>
      {rows.map((league) => (
        <LeagueRow
          key={league.id}
          league={league}
          // Not a stored status: a completed league that is no longer the current season
          // reads as history, so it is dimmed rather than flagged.
          archived={league.status === 'complete' && league.id !== newest}
          editing={editing === league.id}
          draftName={draftName}
          saving={saving === league.id}
          confirming={confirming === league.id}
          on={on}
        />
      ))}
    </div>
  )
}


export default function LeagueList({ onOpenLeague, onCreate, onOpenStandings }) {
  const signedIn = useSignedIn()
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

  /** Run a mutation, refresh, and report failure inline. Returns whether it worked.
   *
   *  Inline, not page-level: the list is still valid when one change fails, and five of
   *  these handlers used to call setError, which replaces the whole page with a dead end.
   */
  async function mutate(call) {
    setSaveError(null)
    try {
      await call()
      await reload()
      return true
    } catch (e) {
      setSaveError(e.message)
      return false
    }
  }

  async function saveName(league) {
    const name = draftName.trim()
    if (!name || name === league.name) { setEditing(null); return }
    if (await mutate(() => api.renameLeague(league.id, name))) setEditing(null)
  }

  function saveSettleDate(league, value) {
    if (!value || value === league.settles_on) return
    return mutate(() => api.setSettlesOn(league.id, value))
  }

  function savePickSeconds(league, value) {
    const seconds = Number(value)
    if (Number.isNaN(seconds) || seconds === league.pick_seconds) return
    return mutate(() => api.setPickSeconds(league.id, seconds))
  }

  const toggleFreeze = (league) =>
    mutate(() => api.freezeLeague(league.id, !league.frozen_at))

  const toggleVisibility = (league) =>
    mutate(() => api.setVisibility(
      league.id, league.visibility === 'public' ? 'private' : 'public'))

  const claim = (league, player) => mutate(() => api.claimSlot(league.id, player))

  const release = (league, player) => mutate(() => api.releaseSlot(league.id, player))

  async function remove(league) {
    if (await mutate(() => api.deleteLeague(league.id))) setConfirming(null)
  }

  /** `league` omitted means the whole database -- the backup. */
  async function exportData(league) {
    setSaving(league ? league.id : 'all')
    setSaveError(null)
    try {
      saveBlob(league ? await api.exportLeague(league.id) : await api.exportArchive())
    } catch (e) {
      setSaveError(`Couldn't export: ${e.message}`)
    } finally {
      setSaving(null)
    }
  }

  useEffect(() => { reload() }, [])

  if (error) return <div className="state-msg" role="alert">{error}</div>
  if (!leagues) return <div className="state-msg">Loading leagues…</div>

  // The server tags each row `mine`, so grouping needs no membership logic in the browser.
  const mine = leagues.filter((l) => l.mine)
  const publicLeagues = leagues.filter((l) => !l.mine)
  const drafting = mine.filter((l) => l.status === 'drafting').length
  const newest = leagues.length > 0 ? leagues[0].id : null

  const on = {
    saveName, saveSettleDate, savePickSeconds, toggleFreeze, toggleVisibility,
    claim, release, remove, exportData,
    setEditing, setDraftName, setConfirming,
    openLeague: onOpenLeague, openStandings: onOpenStandings,
  }
  const tableProps = { newest, editing, draftName, saving, confirming, on }

  return (
    <div className="league-page">
      <header className="league-header">
        <div>
          <h1 className="league-wordmark"><span className="header-mark" />Movie League</h1>
          <p className="league-subtitle">
            {signedIn
              ? `${mine.length} of yours · ${publicLeagues.length} public`
              : `${publicLeagues.length} public league${ordinalSuffix(publicLeagues.length)}`}
            {drafting > 0 && ` · ${drafting} draft${ordinalSuffix(drafting)} in progress`}
          </p>
        </div>
        {signedIn && (
          <span className="header-actions">
            <button
              className="btn"
              disabled={saving === 'all' || mine.length === 0}
              title="Download your leagues as a restorable JSON file"
              onClick={() => exportData(null)}
            >
              {saving === 'all' ? 'SAVING…' : 'BACK UP'}
            </button>
            <button className="btn" onClick={onCreate}>NEW LEAGUE</button>
          </span>
        )}
      </header>

      {saveError && (
        <div className="card-error" role="alert">
          {saveError}
          <button className="btn btn-small" onClick={() => setSaveError(null)}>DISMISS</button>
        </div>
      )}

      {/* One renderer, used for both groups: the row markup is identical, only the
          heading and the source list differ. */}
      {/* Row markup lives in LeagueRow; this is only which rows go where. */}
      <div className="league-layout">
        <div className="league-main">
          {signedIn && (
            <>
              <h2 className="league-group-title">YOUR LEAGUES</h2>
              {mine.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-heading">No leagues yet</div>
                  <div className="empty-state-body">
                    Create one to name your players and draft a season.
                  </div>
                </div>
              ) : <LeagueTable rows={mine} {...tableProps} />}
            </>
          )}

          <h2 className="league-group-title">
            PUBLIC LEAGUES
            {signedIn && publicLeagues.length > 0 && (
              <span className="league-group-note">
                Anyone can read these. You cannot change them.
              </span>
            )}
          </h2>
          {publicLeagues.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-heading">No public leagues</div>
              <div className="empty-state-body">
                {signedIn
                  ? 'Mark one of yours public to share its standings with anyone.'
                  : 'Nothing has been shared publicly yet. Sign in to see your own.'}
              </div>
            </div>
          ) : <LeagueTable rows={publicLeagues} {...tableProps} />}
        </div>

        <AuthPanel />
      </div>

      <SupportLink />
    </div>
  )
}

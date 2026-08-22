import { accountsEnabled } from '../auth.jsx'
import { STATUS_LABEL, actionFor, progressFor } from './leagueDisplay.js'

/** One league in the list.
 *
 *  Its own component rather than a closure inside LeagueList's render: a component defined
 *  during render is a new type on every pass, so React remounts it and any state inside
 *  is lost. Handlers arrive bundled as `on` because there are fifteen of them and fifteen
 *  props is not an improvement on the closure.
 */
export default function LeagueRow({ league, archived, editing, draftName, saving,
                                    confirming, on }) {
  const progress = progressFor(league)
  const action = actionFor(league)
  const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0

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
                      onClick={() => on.release(league, league.your_player)}
                    >RELEASE</button>
                  </span>
                ) : league.unclaimed?.length > 0 ? (
                  <span className="claim-strip">
                    Claim your slot:
                    {league.unclaimed.map((name) => (
                      <button key={name} className="btn btn-small"
                              onClick={() => on.claim(league, name)}>{name}</button>
                    ))}
                  </span>
                ) : null
              )}
              {!league.is_creator ? (
                <span className="league-name">{league.name}</span>
              ) : editing ? (
                <input
                  className="input input-inline"
                  autoFocus
                  value={draftName}
                  onChange={(e) => on.setDraftName(e.target.value)}
                  onBlur={() => on.saveName(league)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') on.saveName(league)
                    if (e.key === 'Escape') on.setEditing(null)
                  }}
                />
              ) : (
                <button
                  className="league-name league-name-button"
                  title="Rename"
                  onClick={() => { on.setEditing(league.id); on.setDraftName(league.name) }}
                >
                  {league.name}
                </button>
              )}
              <span className="league-meta">
                {!league.is_creator ? (
                  <span className={`visibility-pill static ${league.visibility}`}>
                    {league.visibility === 'public' ? 'PUBLIC' : 'PRIVATE'}
                  </span>
                ) : (
                <button
                  className={`visibility-pill ${league.visibility}`}
                  title={league.visibility === 'public'
                    ? 'Anyone with the link can view the standings. Click to make private.'
                    : 'Only league members can view this. Click to make it public.'}
                  onClick={() => on.toggleVisibility(league)}
                >
                  {league.visibility === 'public' ? 'PUBLIC' : 'PRIVATE'}
                </button>
                )}
                {' · '}
                {progress.caption}
                {league.status !== 'complete' && league.is_creator && (
                  <>
                    {' · '}
                    <select
                      className="settle-date"
                      value={league.pick_seconds}
                      title="Seconds each player gets on the clock"
                      onChange={(e) => on.savePickSeconds(league, e.target.value)}
                    >
                      {[0, 30, 60, 120, 300].map((s) => (
                        <option key={s} value={s}>
                          {s === 0 ? 'untimed' : `${s}s per pick`}
                        </option>
                      ))}
                    </select>
                  </>
                )}
                {!league.frozen_at && league.is_creator && (
                  <>
                    {' · books close '}
                    <input
                      type="date"
                      className="settle-date"
                      value={league.settles_on || ''}
                      title="When this season's scores stop updating"
                      onChange={(e) => on.saveSettleDate(league, e.target.value)}
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
              {league.is_creator && (confirming ? (
                <span className="confirm-strip">
                  <span className="confirm-text">
                    Delete “{league.name}” and its {league.picks_made} picks?
                  </span>
                  <button className="btn btn-danger" onClick={() => on.remove(league)}>
                    DELETE
                  </button>
                  <button className="btn" onClick={() => on.setConfirming(null)}>
                    CANCEL
                  </button>
                </span>
              ) : (
                <>
                  <button
                    className="league-export"
                    title={`Download “${league.name}” as JSON`}
                    disabled={saving}
                    onClick={() => on.exportData(league)}
                  >{saving ? '…' : '↓'}</button>
                  <button
                    className="league-delete"
                    title="Delete league"
                    onClick={() => on.setConfirming(league.id)}
                  >×</button>
                </>
              ))}
              {league.is_creator
                && (league.frozen_at || (league.season_ended
                    && league.status === 'complete')) && (
                <button
                  className="btn btn-small"
                  title={league.frozen_at
                    ? 'Reopen so scores update again'
                    : 'Settle this season so its scores stop moving'}
                  onClick={() => on.toggleFreeze(league)}
                >
                  {league.frozen_at ? 'REOPEN' : 'SETTLE SEASON'}
                </button>
              )}
              <button
                className={`btn${action.primary ? ' btn-primary' : ''}`}
                onClick={() => (league.status === 'complete'
                  ? on.openStandings(league)
                  : on.openLeague(league))}
              >
                {action.label}
              </button>
            </span>
          </div>
  )
}

/** Display helpers shared by the league list and its rows. */
export const STATUS_LABEL = { setup: 'SETUP', drafting: 'DRAFTING', complete: 'COMPLETE' }

export function ordinalSuffix(n) {
  return n === 1 ? '' : 's'
}

/** Progress means different things before and after a draft finishes.
 *  Mid-draft the number that matters is picks; once every slot is filled the season is
 *  running and the live number becomes how many films have ratings in yet. */
export function progressFor(league) {
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

export function actionFor(league) {
  if (league.status === 'drafting') return { label: 'RESUME DRAFT', primary: true }
  if (league.status === 'setup') return { label: 'OPEN', primary: false }
  return { label: 'STANDINGS', primary: false }
}

import { mkdirSync } from 'node:fs'

import { expect, test } from '@playwright/test'

const SHOTS = 'e2e-screenshots'
mkdirSync(SHOTS, { recursive: true })

/** Capture the screen for a human to glance at.
 *
 *  Assertions say a thing is present; they cannot say it looks right. A blank page with
 *  one correct element still passes. These go to the CI summary so a green run can be
 *  confirmed by eye in a second.
 */
async function capture(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
}

/** The app driven the way a person drives it.
 *
 *  Everything else in this repo tests the API. This is the only layer that knows whether
 *  the frontend renders, whether a click reaches the server, and whether the board updates
 *  when it should.
 *
 *  The film pool is stubbed. It comes from TMDB, which means a key, a quota, and a list
 *  that changes under us -- none of which belongs in a test of our own UI. Everything
 *  below the pool is real: real server, real database, real migrations.
 */
const FILMS = [
  { tmdb_id: 9001, title: 'Test Film Alpha', release_date: '2027-01-01', poster_path: null },
  { tmdb_id: 9002, title: 'Test Film Beta', release_date: '2027-02-01', poster_path: null },
  { tmdb_id: 9003, title: 'Test Film Gamma', release_date: '2027-03-01', poster_path: null },
  { tmdb_id: 9004, title: 'Test Film Delta', release_date: '2027-04-01', poster_path: null },
  { tmdb_id: 9005, title: 'Test Film Epsilon', release_date: '2027-05-01', poster_path: null },
  { tmdb_id: 9006, title: 'Test Film Zeta', release_date: '2027-06-01', poster_path: null },
  { tmdb_id: 9007, title: 'Test Film Eta', release_date: '2027-07-01', poster_path: null },
  { tmdb_id: 9008, title: 'Test Film Theta', release_date: '2027-08-01', poster_path: null },
  { tmdb_id: 9009, title: 'Test Film Iota', release_date: '2027-09-01', poster_path: null },
  { tmdb_id: 9010, title: 'Test Film Kappa', release_date: '2027-01-01', poster_path: null },
  { tmdb_id: 9011, title: 'Test Film Lambda', release_date: '2027-02-01', poster_path: null },
  { tmdb_id: 9012, title: 'Test Film Mu', release_date: '2027-03-01', poster_path: null },
]

async function stubPool(page) {
  // Stateful, because the board refetches the pool after every pick and the real endpoint
  // marks what has gone. A static stub would show a drafted film as still available.
  const drafted = new Map()
  const pickOrder = []

  await page.route('**/api/leagues/*/draft/pick', async (route) => {
    const body = route.request().postDataJSON()
    const response = await route.fetch()
    if (response.ok()) {
      drafted.set(body.tmdb_id, body.player)
      pickOrder.push(body.player)
    }
    await route.fulfill({ response })
  })

  await page.route('**/api/leagues/*/pool*', async (route) => {
    const q = new URL(route.request().url()).searchParams.get('q')
    const chosen = q
      ? FILMS.filter((f) => f.title.toLowerCase().includes(q.toLowerCase()))
      : FILMS
    await route.fulfill({
      json: {
        year: 2027,
        films: chosen.map((f) => ({
          ...f,
          drafted: drafted.has(f.tmdb_id),
          taken_by: drafted.get(f.tmdb_id) ?? null,
          taken_at_pick: drafted.has(f.tmdb_id) ? 1 : null,
        })),
      },
    })
  })

  await page.route('**/api/leagues/pool-size*', (route) =>
    route.fulfill({ json: { year: 2027, count: FILMS.length } }))

  // Handed back so a test can assert the turn order the board actually produced.
  return pickOrder
}


async function createLeague(page, name, { players = ['Ann', 'Bob'], rounds = 1 } = {}) {
  await page.goto('/')
  await page.getByRole('button', { name: 'NEW LEAGUE' }).click()
  await expect(page.getByRole('heading', { name: 'CREATE LEAGUE' })).toBeVisible()

  await page.getByRole('textbox').first().fill(name)
  for (const player of players) {
    await page.getByPlaceholder('Add a player').fill(player)
    await page.getByRole('button', { name: 'ADD' }).click()
  }
  for (let i = 6; i > rounds; i--) await page.getByRole('button', { name: '−' }).click()
  await page.getByRole('button', { name: 'CREATE LEAGUE' }).click()
  await expect(page.getByRole('button', { name: /START DRAFT/ })).toBeVisible()
}


test('the app renders without an account', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /Movie League/i })).toBeVisible()
  // Local mode: one user, so there is nothing to sign in to.
  await expect(page.getByRole('button', { name: 'SIGN IN' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'NEW LEAGUE' })).toBeVisible()
  await capture(page, '1-league-list')
})


test('a league is created, snake-drafted over three rounds, and read back', async ({ page }) => {
  const pickOrder = await stubPool(page)
  const name = `Browser ${Date.now()}`

  await createLeague(page, name, { players: ['Ann', 'Bob'], rounds: 3 })

  await page.getByRole('button', { name: /START DRAFT/ }).click()

  for (let pick = 0; pick < 6; pick++) {
    const row = page.locator('.pool-row', { hasText: FILMS[pick].title })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'DRAFT' }).click()
  }

  await expect(page.getByRole('button', { name: 'VIEW STANDINGS' })).toBeVisible()
  await capture(page, '2-draft-complete')

  // Three rounds of two: the snake shows as back-to-back picks at each round boundary. A
  // straight repeating order would alternate the whole way through and never do that.
  expect(pickOrder).toHaveLength(6)
  const [r1, r2, r3] = [pickOrder.slice(0, 2), pickOrder.slice(2, 4), pickOrder.slice(4, 6)]
  expect(r2).toEqual([...r1].reverse())
  expect(r3).toEqual(r1)
  expect(pickOrder[1]).toBe(pickOrder[2])      // last of round 1 picks first of round 2
  expect(pickOrder[3]).toBe(pickOrder[4])      // and again into round 3
  for (const round of [r1, r2, r3]) {
    expect(new Set(round).size).toBe(2)        // nobody picks twice within a round
  }

  await page.getByRole('button', { name: 'VIEW STANDINGS' }).click()
  await expect(page.getByText('Ann')).toBeVisible()
  await expect(page.getByText('Bob')).toBeVisible()

  // Three films each. This is the assertion the standings screenshot exists to show.
  await expect(page.locator('.roster-row')).toHaveCount(6)
  await capture(page, '3-standings')
})


test('a taken film cannot be taken again', async ({ page }) => {
  await stubPool(page)
  await createLeague(page, `Clash ${Date.now()}`)
  await page.getByRole('button', { name: /START DRAFT/ }).click()

  const first = page.locator('.pool-row', { hasText: FILMS[0].title })
  await first.getByRole('button', { name: 'DRAFT' }).click()

  // It stays visible, marked DRAFTED, and offers no way to take it again.
  await expect(first.getByText('DRAFTED')).toBeVisible()
  await expect(first.getByRole('button', { name: 'DRAFT' })).toHaveCount(0)
})

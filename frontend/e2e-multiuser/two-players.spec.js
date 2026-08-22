import { expect, test } from '@playwright/test'

/** Alice and Bob, one draft, two browsers.
 *
 *  Each browser talks to its own backend process, and both processes share one database.
 *  That makes them two genuinely different users without Clerk, without secrets, and
 *  without depending on anyone else's service being up.
 */
const ALICE = 'http://127.0.0.1:5281'
const BOB = 'http://127.0.0.1:5282'

const FILMS = Array.from({ length: 8 }, (_, i) => ({
  tmdb_id: 7001 + i,
  title: `Shared Film ${i + 1}`,
  release_date: '2027-05-01',
  poster_path: null,
}))

/** The pool comes from TMDB, which needs a key and changes under us. Stub it per page,
 *  keeping the drafted marks in step with what the server reports on the board. */
async function stubPool(page) {
  await page.route('**/api/leagues/*/pool*', async (route) => {
    const drafted = await page.evaluate(() => window.__draftedIds || []).catch(() => [])
    await route.fulfill({
      json: {
        year: 2027,
        films: FILMS.map((f) => ({
          ...f,
          drafted: drafted.includes(f.tmdb_id),
          taken_by: null,
          taken_at_pick: null,
        })),
      },
    })
  })
  await page.route('**/api/leagues/pool-size*', (route) =>
    route.fulfill({ json: { year: 2027, count: FILMS.length } }))
}

/** Whose turn the board says it is, read from the page rather than from the API. */
async function onTheClock(page) {
  return page.locator('.clock-player, .on-the-clock-player').first().innerText()
    .catch(() => null)
}

test('two people share one draft, and only one of them can pick', async ({ browser }) => {
  const alice = await browser.newPage()
  const bob = await browser.newPage()
  await stubPool(alice)
  await stubPool(bob)

  // Alice makes a public league so Bob can find it at all.
  await alice.goto(`${ALICE}/`)
  await alice.getByRole('button', { name: 'NEW LEAGUE' }).click()
  await alice.getByRole('textbox').first().fill('Shared Draft')
  for (const player of ['Alice', 'Bob']) {
    await alice.getByPlaceholder('Add a player').fill(player)
    await alice.getByRole('button', { name: 'ADD' }).click()
  }
  for (let i = 6; i > 2; i--) await alice.getByRole('button', { name: '−' }).click()
  await alice.getByRole('button', { name: 'PUBLIC' }).click().catch(() => {})
  await alice.getByRole('button', { name: 'CREATE LEAGUE' }).click()
  await expect(alice.getByRole('button', { name: /START DRAFT/ })).toBeVisible()

  // Bob sees it from his own process, against the same database.
  await bob.goto(`${BOB}/`)
  await expect(bob.getByText('Shared Draft')).toBeVisible({ timeout: 15_000 })

  await alice.getByRole('button', { name: /START DRAFT/ }).click()

  // Bob opens the same board.
  await bob.getByRole('button', { name: /RESUME DRAFT|OPEN|STANDINGS/ }).first().click()

  // Wait for the pool to render before counting anything -- an empty board and a
  // read-only board look identical to a bare count.
  await expect(alice.locator('.pool-row').first()).toBeVisible({ timeout: 15_000 })
  await expect(bob.locator('.pool-row').first()).toBeVisible({ timeout: 15_000 })

  // Exactly one of them is offered a pick. Alice created the league, so she can act for
  // any unclaimed slot; Bob has claimed nothing, so he can act for none.
  await expect(alice.getByRole('button', { name: 'DRAFT' }).first()).toBeVisible()
  await expect(bob.getByRole('button', { name: 'DRAFT' })).toHaveCount(0)

  // Alice picks, and Bob's board catches up on its own -- no reload, no interaction.
  const before = await bob.locator('.pool-row').count()
  await alice.locator('.pool-row', { hasText: FILMS[0].title })
    .getByRole('button', { name: 'DRAFT' }).click()

  await expect(bob.getByText('1 OF 4 PICKS MADE')).toBeVisible({ timeout: 15_000 })
  expect(before).toBeGreaterThan(0)

  await alice.screenshot({ path: 'e2e-screenshots/5-alice-picking.png', fullPage: true })
  await bob.screenshot({ path: 'e2e-screenshots/6-bob-watching.png', fullPage: true })
})

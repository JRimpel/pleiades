import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

async function nightlyAstronomy(page: Page) {
  await page.route('**/api/sky-events?**', async route => {
    const url = new URL(route.request().url())
    const date = url.searchParams.get('date')!
    const following = new Date(`${date}T12:00:00Z`)
    following.setUTCDate(following.getUTCDate() + 1)
    const next = following.toISOString().slice(0, 10)
    await route.fulfill({ json: {
      date, lat: Number(url.searchParams.get('lat')), lon: Number(url.searchParams.get('lon')),
      twilight: { sunset: `${date}T22:00:00Z`, astronomical_dusk: `${date}T23:30:00Z`,
        astronomical_dawn: `${next}T10:00:00Z`, sunrise: `${next}T12:00:00Z` },
      moon: { illumination: .1, phase_name: 'Test phase', rise: null, set: null },
      planets: [{ name: 'Saturn', max_alt_deg: 40,
        rise: date === '2026-11-07' ? `${date}T20:00:00Z` : `${next}T13:00:00Z`,
        set: date === '2026-11-07' ? `${next}T07:00:00Z` : `${next}T20:00:00Z` }],
    } })
  })
}

test('Visible tonight is optional and combines with search, category and sort filters', async ({ page }) => {
  await nightlyAstronomy(page)
  await page.goto('/tests/fixture.html')
  await expect(page.getByText(/Local night starting 2026-11-07/)).toBeVisible()
  const toggle = page.getByLabel('Visible tonight', { exact: true })
  const search = page.getByRole('searchbox', { name: 'Find an object or constellation' })
  const cards = page.locator('.explore-object-card')
  await expect(toggle).not.toBeChecked()
  await page.getByRole('button', { name: 'Planets & Moon', exact: true }).click()
  await search.fill('Neptune')
  await expect(cards).toHaveCount(1)
  await toggle.check()
  await expect(cards).toHaveCount(0)
  await expect(page.getByText(/No objects match Visible tonight and your filters/)).toBeVisible()
  await expect(search).toHaveValue('Neptune')
  await expect(page.getByRole('button', { name: 'Planets & Moon', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await search.fill('Saturn')
  await expect(cards).toHaveCount(1)
  await expect(cards.locator('h3')).toHaveText('Saturn')
  await page.getByRole('combobox', { name: 'Sort objects' }).selectOption('name')
  await expect(toggle).toBeChecked()
  await expect(cards).toHaveCount(1)
  await toggle.uncheck()
  await search.fill('Neptune')
  await expect(cards).toHaveCount(1)
  await expect(cards.locator('h3')).toHaveText('Neptune')
})

test('Visible tonight stays enabled and recomputes when the selected observing night changes', async ({ page }) => {
  await nightlyAstronomy(page)
  await page.goto('/tests/fixture.html')
  await expect(page.getByText(/Local night starting 2026-11-07/)).toBeVisible()
  const toggle = page.getByLabel('Visible tonight', { exact: true })
  const search = page.getByRole('searchbox', { name: 'Find an object or constellation' })
  const cards = page.locator('.explore-object-card')
  await toggle.check()
  await search.fill('Saturn')
  await expect(cards).toHaveCount(1)
  await page.getByLabel('Date & time (UTC)').fill('2026-11-09T04:00')
  await page.getByRole('button', { name: 'Update sky context' }).click()
  await expect(page.getByText(/Local night starting 2026-11-08/)).toBeVisible()
  await expect(toggle).toBeChecked()
  await expect(search).toHaveValue('Saturn')
  await expect(cards).toHaveCount(0)
  await page.getByLabel('Date & time (UTC)').fill('2026-11-08T04:00')
  await page.getByRole('button', { name: 'Update sky context' }).click()
  await expect(page.getByText(/Local night starting 2026-11-07/)).toBeVisible()
  await expect(cards).toHaveCount(1)
  await expect(toggle).toBeChecked()
})

test('missing nighttime astronomy is explained and turning the filter off restores browsing', async ({ page }) => {
  await page.route('**/api/sky-events?**', route => route.fulfill({ status: 503, json: { error: 'Offline astronomy test' } }))
  await page.goto('/tests/fixture.html')
  await expect(page.getByText(/Astronomy information could not be loaded/)).toBeVisible()
  const toggle = page.getByLabel('Visible tonight', { exact: true })
  const cards = page.locator('.explore-object-card')
  await expect(cards).toHaveCount(24)
  await toggle.check()
  await expect(page.getByText(/Nighttime astronomy is unavailable/)).toBeVisible()
  await expect(cards).toHaveCount(0)
  await toggle.uncheck()
  await expect(cards).toHaveCount(24)
  await expect(page.getByText(/Nighttime astronomy is unavailable/)).not.toBeVisible()
})

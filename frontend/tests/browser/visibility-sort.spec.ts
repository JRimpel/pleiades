import { test, expect } from '@playwright/test'

test('visibility is the default, updates with time, and can be changed to alphabetical order', async ({ page }) => {
  // Catalog coordinates keep fixed-object visibility useful while the API is unavailable.
  await page.route('**/api/sky-events?**', route => route.fulfill({ status: 503, json: { error: 'Offline astronomy test' } }))
  await page.goto('/tests/fixture.html')
  const sort = page.getByRole('combobox', { name: 'Sort objects' })
  await expect(sort).toHaveValue('visibility')
  const cards = page.locator('.explore-object-card')
  await expect(cards).toHaveCount(24)
  await expect(cards.locator('.explore-card-status.tone-positive')).toHaveCount(24)
  const names = () => cards.locator('h3').allTextContents()
  const evening = await names()

  await page.getByLabel('Date & time (UTC)').fill('2026-11-08T16:00')
  await page.getByRole('button', { name: 'Update sky context' }).click()
  await expect.poll(names).not.toEqual(evening)
  await expect(cards.locator('.explore-card-status.tone-positive')).toHaveCount(24)
  await expect(sort).toHaveValue('visibility')

  await sort.selectOption('name')
  const alphabetical = await names()
  expect(alphabetical).toEqual([...alphabetical].sort((a, b) => a.localeCompare(b)))
  await expect(page.getByRole('button', { name: /Show more objects/ })).toBeVisible()
})

test('visibility sorting is preserved through filtering and happens before pagination', async ({ page }) => {
  await page.route('**/api/sky-events?**', route => route.fulfill({ status: 503, json: { error: 'Offline astronomy test' } }))
  await page.goto('/tests/fixture.html')
  await expect(page.locator('.explore-card-status.tone-positive')).toHaveCount(24)
  await page.getByRole('button', { name: 'Galaxies', exact: true }).click()
  const more = page.getByRole('button', { name: /Show more objects/ })
  while (await more.count()) await more.click()
  const cards = page.locator('.explore-object-card')
  await expect(cards).toHaveCount(40)
  const states = await cards.locator('.explore-card-status').evaluateAll(elements => elements.map(element =>
    element.classList.contains('tone-positive') ? 0 : element.classList.contains('tone-muted') ? 1 : 2))
  expect(states).toEqual([...states].sort((a, b) => a - b))
  expect(states).toContain(0)
  expect(states).toContain(2)
  await expect(page.getByRole('combobox', { name: 'Sort objects' })).toHaveValue('visibility')
  await page.getByRole('searchbox', { name: 'Find an object or constellation' }).fill('Andromeda Galaxy')
  await expect(cards).toHaveCount(1)
  await expect(cards.locator('h3')).toHaveText('Andromeda Galaxy')
})

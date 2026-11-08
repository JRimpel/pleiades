import { test, expect } from '@playwright/test'

test('all 263 objects load a dedicated 2D thumbnail without fetching a 3D model', async ({ page }) => {
  await page.route('**/api/sky-events?**', route => route.fulfill({ status: 503, json: { error: 'Astronomy unavailable during thumbnail check' } }))
  const models: string[] = []
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('.glb')) models.push(request.url()) })
  await page.goto('/tests/fixture.html')
  const more = page.getByRole('button', { name: /Show more objects/ })
  while (await more.count()) await more.click()
  const images = page.locator('.explore-object-thumbnail')
  await expect(images).toHaveCount(263)
  const results = await images.evaluateAll(async elements => Promise.all(elements.map(async element => {
    const image = element as HTMLImageElement
    image.loading = 'eager'
    try { await image.decode() } catch { return { alt: image.alt, loaded: false } }
    return { alt: image.alt, loaded: image.naturalWidth > 0 && image.naturalHeight > 0 && image.currentSrc.includes('/thumbnails/') }
  })))
  expect(results.filter(result => !result.loaded)).toEqual([])
  expect(models).toEqual([])
  await page.getByRole('searchbox', { name: 'Find an object or constellation' }).fill('')
  await page.getByRole('heading', { name: 'Your sky, up close' }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/object-thumbnails.png' })
})

test('an unavailable thumbnail shows an accessible object fallback', async ({ page }) => {
  await page.route('**/explore/thumbnails/saturn.svg', route => route.abort())
  await page.goto('/tests/fixture.html')
  await page.getByRole('searchbox', { name: 'Find an object or constellation' }).fill('Saturn')
  const fallback = page.getByRole('img', { name: 'Saturn 2D thumbnail unavailable' })
  await expect(fallback).toBeVisible()
  await expect(fallback).toContainText('Saturn')
  await expect(page.getByRole('button', { name: 'Explore Saturn in 3D', exact: true })).toBeVisible()
})

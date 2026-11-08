import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { ModelViewerElement } from '@google/model-viewer'

async function astronomy(page: Page) {
  await page.route('**/api/sky-events?**', async route => {
    const url = new URL(route.request().url())
    const date = url.searchParams.get('date')!
    const next = new Date(date + 'T12:00:00Z'); next.setUTCDate(next.getUTCDate() + 1)
    await route.fulfill({ json: { date, lat: Number(url.searchParams.get('lat')), lon: Number(url.searchParams.get('lon')),
      moon: { phase_name: 'Test phase', illumination: .1, rise: null, set: null },
      twilight: { sunset: `${date}T22:00:00Z`, astronomical_dusk: `${date}T23:30:00Z`, astronomical_dawn: null, sunrise: null },
      planets: [{ name: 'Saturn', rise: `${date}T20:00:00Z`, set: `${next.toISOString().slice(0, 10)}T07:00:00Z`, max_alt_deg: 40 }] } })
  })
}

test('all five real GLBs render; keyboard controls, reset, and focus restoration work', async ({ page }) => {
  await astronomy(page)
  const models: string[] = []
  page.on('request', request => { if (request.url().endsWith('.glb')) models.push(request.url()) })
  await page.goto('/')
  await page.getByRole('heading', { name: 'Your sky, up close' }).scrollIntoViewIfNeeded()
  expect(models).toHaveLength(0)
  for (const name of ['Saturn', 'Jupiter', 'Vega', 'Pleiades', 'Andromeda Galaxy']) {
    const button = page.getByRole('button', { name: `Explore ${name} in 3D`, exact: true })
    await button.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled({ timeout: 45000 })
    const orbit = () => dialog.locator('model-viewer').evaluate(element => {
      const viewer = element as ModelViewerElement
      return { ...viewer.getCameraOrbit(), fov: viewer.getFieldOfView() }
    })
    const initial = await orbit()
    await dialog.getByRole('button', { name: 'Rotate view left' }).click()
    await expect.poll(async () => Math.abs((await orbit()).theta - initial.theta)).toBeGreaterThan(.1)
    await dialog.getByRole('button', { name: 'Zoom in', exact: true }).click()
    await expect.poll(async () => Math.abs((await orbit()).radius - initial.radius) + Math.abs((await orbit()).fov - initial.fov)).toBeGreaterThan(.01)
    await dialog.getByRole('button', { name: 'Reset view' }).click()
    await expect.poll(async () => Math.abs((await orbit()).theta - initial.theta)).toBeLessThan(.01)
    if (name === 'Saturn') {
      const box = (await dialog.locator('model-viewer').boundingBox())!
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.mouse.down()
      await page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2, { steps: 12 })
      await page.mouse.up()
      await expect.poll(async () => Math.abs((await orbit()).theta - initial.theta)).toBeGreaterThan(.1)
      await dialog.getByRole('button', { name: 'Reset view' }).click()
      await expect.poll(async () => Math.abs((await orbit()).theta - initial.theta)).toBeLessThan(.01)
    }
    await page.screenshot({ path: `test-results/${name.replaceAll(' ', '-').toLowerCase()}-desktop.png` })
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
    await expect(button).toBeFocused()
    await expect(page.locator('model-viewer')).toHaveCount(0)
  }
  expect(models.length).toBeGreaterThanOrEqual(5)
})

test('mobile controls, native dialog focus containment, reduced motion, and unknown visibility', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await astronomy(page)
  await page.goto('/')
  const trigger = page.getByRole('button', { name: 'Explore Pleiades in 3D', exact: true })
  await trigger.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Visibility not calculated', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled({ timeout: 45000 })
  await expect(dialog.getByRole('button', { name: 'Auto-rotate', exact: true })).toHaveCount(0)
  await expect(page.locator('body')).toHaveCSS('overflow', 'hidden')
  await page.screenshot({ path: 'test-results/pleiades-mobile-top.png' })
  for (let i = 0; i < 18; i++) {
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => document.querySelector('dialog')!.contains(document.activeElement))).toBe(true)
  }
  const box = await dialog.boundingBox()
  expect(box!.width).toBeLessThanOrEqual(390)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/pleiades-mobile.png' })
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
})

test('asset failure shows a reference image, and Try 3D really retries', async ({ page }) => {
  await astronomy(page)
  await page.route('**/explore/saturn.glb', route => route.abort())
  await page.goto('/')
  await page.getByRole('button', { name: 'Explore Saturn in 3D', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('The 3D model could not load. Showing the reference image.')).toBeVisible()
  await expect(dialog.locator('.explore-stage img')).toBeVisible()
  await page.unroute('**/explore/saturn.glb')
  await dialog.getByRole('button', { name: 'Try 3D view' }).click()
  await expect(dialog.getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled({ timeout: 45000 })
})

test('no WebGL and unavailable astronomy leave educational exploration usable', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type === 'webgl' || type === 'webgl2') return null
      return Reflect.apply(original, this, [type, ...args])
    } as typeof original
  })
  await page.route('**/api/sky-events?**', route => route.fulfill({ status: 503, json: { error: 'test outage' } }))
  await page.goto('/')
  await expect(page.getByText(/Astronomy information could not be loaded/)).toBeVisible()
  await page.getByRole('button', { name: 'Explore Jupiter in 3D', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('3D is unavailable in this browser. Showing the reference image.')).toBeVisible()
  await expect(dialog.getByText('Visibility not calculated', { exact: true })).toBeVisible()
  await expect(dialog.locator('.explore-stage img')).toBeVisible()
  await dialog.getByRole('button', { name: 'Close object explorer' }).click()
})

test('selected context updates the existing API request; no invented object visibility', async ({ page }) => {
  await astronomy(page)
  await page.goto('/')
  await page.getByLabel('Date & time (UTC)').fill('2026-11-08T04:00')
  await page.getByLabel('Latitude', { exact: true }).fill('42.1')
  await page.getByLabel('Longitude', { exact: true }).fill('-78.747')
  const request = page.waitForRequest(r => r.url().includes('/api/sky-events?lat=42.1&lon=-78.747&date=2026-11-07'))
  await page.getByRole('button', { name: 'Update sky context' }).click()
  await request
  await page.getByRole('button', { name: 'Explore Saturn in 3D', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Above horizon · estimated', { exact: true })).toBeVisible()
  await expect(dialog.getByText('42.1000, -78.7470', { exact: true })).toBeVisible()
})

test('unsupported objects and uncertain photo identifications have explicit states', async ({ page }) => {
  await astronomy(page)
  await page.goto('/tests/fixture.html?object=Neptune')
  await expect(page.getByRole('dialog').getByText('No supported model for this object yet')).toBeVisible()
  await page.getByRole('button', { name: 'Back to objects' }).click()
  await page.goto('/tests/fixture.html?object=saturn')
  await expect(page.getByRole('dialog').getByText(/Possible photo identification: Saturn/)).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/does not confirm that identification/)).toBeVisible()
})

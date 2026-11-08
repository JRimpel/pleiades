import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const start = '2026-11-08T04:00:00Z'
const bestTime = '2026-11-09T06:00:00Z'

async function projectApi(page: Page) {
  await page.route('http://127.0.0.1:4173/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown
    if (path === '/api/scores/range') {
      body = { min_time: start, max_time: '2026-11-10T04:00:00Z', now: start }
    } else if (path === '/api/scores') {
      body = { type: 'FeatureCollection', time: url.searchParams.get('time') ?? start, features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [-78.9, 42.9] },
          properties: { cell_id: 42, name: 'Integration Lookout', is_curated: true, score: 64, label: 'Good', bortle: 4, top_factor: 'clouds' } },
      ] }
    } else if (path === '/api/best') {
      body = { time: null, night: '2026-11-07', spots: [
        { cell_id: 42, name: 'Integration Lookout', is_curated: true, lat: 42.9, lon: -78.9, score: 78,
          label: 'Excellent', bortle: 4, valid_time: bestTime, distance_km: 12 },
      ] }
    } else if (path === '/api/spots/42') {
      body = { cell_id: 42, name: 'Integration Lookout', is_curated: true, lat: 42.9, lon: -78.9,
        elevation_m: 250, sky_brightness_mpsas: 21, bortle: 4, valid_time: url.searchParams.get('time') ?? start,
        score: 78, label: 'Excellent', nelm: 6, factors: { clouds: -12, calibration: -10 }, model_version: 3, computed_at: start,
        conditions: { fetched_at: start, cloud_total: 12, cloud_low: 3, cloud_mid: 4, cloud_high: 5, visibility_m: 20000,
          rh: 50, dew_point_c: 0, temp_c: 5, wind_kmh: 10, precip_prob: 0 },
        astro: { time: bestTime, sun_alt: -30, moon_alt: -10, moon_illum: .1, moon_phase_deg: 30 },
        explanation: { summary: 'Integration fixture explanation.', tips: ['Compare clearer hours.'] } }
    } else if (path.endsWith('/history')) {
      body = { cell_id: 42, from_time: start, to_time: bestTime, hourly: [{ time: bestTime, score: 78, nelm: 6 }], nightly: [] }
    } else if (path.endsWith('/drift')) {
      body = { cell_id: 42, night: '2026-11-08', window_start: start, window_end: bestTime, revisions: [] }
    } else if (path === '/api/sky-events') {
      const date = url.searchParams.get('date') ?? '2026-11-07'
      const next = new Date(`${date}T12:00:00Z`); next.setUTCDate(next.getUTCDate() + 1)
      body = { date, lat: Number(url.searchParams.get('lat') ?? 42.7), lon: Number(url.searchParams.get('lon') ?? -78.4),
        moon: { phase_deg: 30, phase_name: 'Waxing crescent', illumination: .1, rise: null, set: null },
        twilight: { sunset: `${date}T22:00:00Z`, astronomical_dusk: `${date}T23:30:00Z`, astronomical_dawn: `${next.toISOString().slice(0, 10)}T10:00:00Z`, sunrise: null },
        planets: [{ name: 'Saturn', rise: `${date}T20:00:00Z`, set: `${next.toISOString().slice(0, 10)}T07:00:00Z`, max_alt_deg: 40, magnitude: 1 }], events: [] }
    } else {
      await route.fulfill({ status: 404, json: { error: { code: 'not_found', message: path } } }); return
    }
    await route.fulfill({ json: body })
  })
}

test('a database outage is distinguished from an unreachable API', async ({ page }) => {
  await projectApi(page)
  await page.route('**/api/scores**', route => route.fulfill({ status: 503, json: {
    error: { code: 'database_unavailable', message: 'The backend cannot connect to its database.' },
  } }))
  await page.goto('/')
  await expect(page.getByText('Scores unavailable: the backend cannot connect to its database.', { exact: true })).toBeVisible()
})

test('best spot, forecast slider, sky summary, ML factors and 3D context stay connected', async ({ page }) => {
  await page.clock.setFixedTime(new Date(start))
  await projectApi(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  const slider = page.getByRole('slider')
  await expect(slider).toBeEnabled()
  await page.getByRole('button', { name: /Tonight's best/ }).click()
  const panel = page.getByRole('complementary', { name: 'Integration Lookout' })
  await expect(panel).toBeVisible()
  await expect(panel.getByText('Integration fixture explanation.')).toBeVisible()
  await expect(panel.getByText('Observational calibration', { exact: true })).toBeVisible()
  await expect(panel.getByText('Relative observing index · model v3', { exact: true })).toBeVisible()
  await expect(slider).toHaveValue('26')
  await expect(page.getByText('Loading the map…', { exact: true })).not.toBeVisible({ timeout: 20000 })
  await expect(page.locator('.map-error')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/integrated-map.png' })
  await page.getByRole('button', { name: 'Sky details', exact: true }).click()
  await expect(page.locator('.sky-caption')).toContainText('2026-11-08')
  await expect(page.locator('.sky-panel')).toContainText('Rise/set times unavailable')
  await page.getByRole('button', { name: 'Explore in 3D', exact: true }).click()
  await expect(page.locator('.explore-context-caption')).toContainText('Selected map spot')
  await expect(page.locator('.explore-context-caption')).toContainText('42.9000, -78.9000')
  await page.getByRole('searchbox', { name: 'Find an object or constellation' }).fill('Saturn')
  await page.getByRole('button', { name: 'Explore Saturn in 3D', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Nov 9, 1:00 AM EST', { exact: true })).toBeVisible()
  await expect(dialog.getByText('12%', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(panel).toBeVisible()
  await slider.focus()
  await page.keyboard.press('ArrowRight')
  await expect(slider).toHaveValue('27')
  await page.getByRole('button', { name: 'Explore Saturn in 3D', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('Time', { exact: true }).locator('..').locator('dd')).toHaveText('Nov 9, 2:00 AM EST')
  await expect(page.getByRole('dialog').getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled({ timeout: 45000 })
  await page.screenshot({ path: 'test-results/integrated-desktop.png' })
  expect(errors).toEqual([])
})

test('mobile layout keeps the map usable and shares GPS context with exploration', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.clock.setFixedTime(new Date(start))
  await context.grantPermissions(['geolocation'])
  await context.setGeolocation({ latitude: 42.6, longitude: -78.5 })
  await projectApi(page)
  await page.goto('/')
  await expect(page.locator('.map-frame')).toHaveJSProperty('clientHeight', 844)
  const legend = (await page.getByRole('figure', { name: 'Stargazing score color key' }).boundingBox())!
  const sliderCard = (await page.locator('.time-slider').boundingBox())!
  expect(legend.y + legend.height).toBeLessThan(sliderCard.y)
  await page.screenshot({ path: 'test-results/integrated-mobile-map.png' })
  await page.getByRole('button', { name: 'Explore in 3D', exact: true }).click()
  await expect(page.locator('.explore-context-caption')).toContainText('Your location')
  await expect(page.locator('.explore-context-caption')).toContainText('42.6000, -78.5000')
  await page.screenshot({ path: 'test-results/integrated-mobile.png' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

import { test, expect } from '@playwright/test'
import type { Page, Request } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const start = '2026-11-08T04:00:00Z'
const PIXEL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
const GPS_PHOTO = fileURLToPath(new URL('./fixtures/gps-sky.jpg', import.meta.url))
const NO_GPS_PHOTO = fileURLToPath(new URL('./fixtures/no-gps-sky.jpg', import.meta.url))
const DONE_ID = '11111111-1111-4111-8111-111111111111'
const PENDING_ID = '22222222-2222-4222-8222-222222222222'
const NEW_ID = '33333333-3333-4333-8333-333333333333'

type Status = 'pending' | 'done' | 'failed' | 'rejected'

interface FixturePhoto {
  id: string
  username: string
  lat: number
  lon: number
  taken_at: string | null
  thumb_url: string | null
  caption: string | null
  ai_status: Status
  base_votes: number
}

/** A small in-memory backend. Tests read `requests` and mutate `photos`/`presignError`. */
function photoApi() {
  const state = {
    photos: [
      { id: DONE_ID, username: 'nightowl', lat: 42.9, lon: -78.9, taken_at: '2026-11-07T03:00:00Z', thumb_url: PIXEL,
        caption: 'Orion over the lake', ai_status: 'done', base_votes: 3 },
      { id: PENDING_ID, username: 'lakeview', lat: 42.2, lon: -77.6, taken_at: null, thumb_url: null,
        caption: null, ai_status: 'pending', base_votes: 0 },
    ] as FixturePhoto[],
    votes: {} as Record<string, number>,
    presignError: null as null | { status: number; code: string; message: string },
    requests: [] as { method: string; path: string; auth: string | null; body: unknown; headers: Record<string, string> }[],
  }

  const detail = (photo: FixturePhoto, token: string | null) => ({
    id: photo.id, username: photo.username, url: photo.thumb_url, thumb_url: photo.thumb_url,
    lat: photo.lat, lon: photo.lon, cell_id: 42, taken_at: photo.taken_at,
    taken_at_source: photo.taken_at ? 'exif' : 'upload_time', uploaded_at: '2026-11-07T05:00:00Z',
    caption: photo.caption, score_at_capture: photo.taken_at ? 66 : null, ai_status: photo.ai_status,
    ai_description: photo.ai_status === 'done' ? 'A clear dark sky with Orion rising over the treeline.' : null,
    ai_objects: photo.ai_status === 'done' ? [{ name: 'Orion', type: 'constellation', confidence: 0.91 }] : null,
    ai_sky_quality: photo.ai_status === 'done' ? 7 : null,
    ai_milky_way_visible: photo.ai_status === 'done' ? false : null,
    ai_light_pollution_notes: photo.ai_status === 'done' ? 'Faint glow toward the city.' : null,
    vote_count: photo.base_votes + (state.votes[photo.id] ?? 0),
    my_vote: token ? (state.votes[photo.id] ?? 0) : null,
  })

  async function install(page: Page) {
    await page.route('http://127.0.0.1:4173/fake-storage/**', async route => {
      const request = route.request()
      state.requests.push({ method: request.method(), path: new URL(request.url()).pathname, auth: null, body: null,
        headers: await request.allHeaders() })
      await route.fulfill({ status: 200, body: '' })
    })
    await page.route('http://127.0.0.1:4173/api/**', async route => {
      const request: Request = route.request()
      const url = new URL(request.url())
      const path = url.pathname
      const method = request.method()
      const auth = request.headers().authorization ?? null
      const token = auth?.startsWith('Bearer ') ? auth.slice(7) : null
      const body = request.postData() ? request.postDataJSON() : null
      state.requests.push({ method, path, auth, body, headers: {} })
      const json = (status: number, payload: unknown) => route.fulfill({ status, json: payload })
      const needAuth = () => json(401, { error: { code: 'unauthorized', message: 'Missing or invalid token' } })

      if (path === '/api/scores/range') return json(200, { min_time: start, max_time: '2026-11-10T04:00:00Z', now: start })
      if (path === '/api/scores') {
        return json(200, { type: 'FeatureCollection', time: url.searchParams.get('time') ?? start, features: [
          { type: 'Feature', geometry: { type: 'Point', coordinates: [-78.4, 42.6] },
            properties: { cell_id: 42, name: 'Photo Lookout', is_curated: true, score: 64, label: 'Good', bortle: 4, top_factor: 'clouds' } },
        ] })
      }
      if (path === '/api/best') return json(200, { time: null, night: '2026-11-07', spots: [] })
      if (path === '/api/sky-events') return json(503, { error: { code: 'unavailable', message: 'offline' } })
      if (path === '/api/photos' && method === 'GET') {
        return json(200, { photos: state.photos.filter(photo => photo.ai_status !== 'rejected').map(photo => ({
          id: photo.id, lat: photo.lat, lon: photo.lon, thumb_url: photo.thumb_url,
          vote_count: photo.base_votes + (state.votes[photo.id] ?? 0), taken_at: photo.taken_at,
          ai_status: photo.ai_status, ai_sky_quality: photo.ai_status === 'done' ? 7 : null,
        })) })
      }
      if (path === '/api/users' && method === 'POST') {
        const username = (body as { username: string }).username
        if (username === 'taken') return json(409, { error: { code: 'username_taken', message: 'taken' } })
        return json(201, { user_id: 'u-1', username, token: `tok-${username}` })
      }
      if (path === '/api/photos/presign') {
        if (!token) return needAuth()
        if (state.presignError) {
          const { status, code, message } = state.presignError
          return json(status, { error: { code, message } })
        }
        return json(200, { upload_url: `http://127.0.0.1:4173/fake-storage/photos/${NEW_ID}.jpg`, s3_key: `photos/${NEW_ID}.jpg`,
          method: 'PUT', headers: { 'Content-Type': (body as { content_type: string }).content_type }, expires_in: 900 })
      }
      if (path === '/api/photos' && method === 'POST') {
        if (!token) return needAuth()
        const req = body as { lat: number; lon: number; taken_at?: string; caption?: string }
        state.photos.unshift({ id: NEW_ID, username: token.replace(/^tok-/, ''), lat: req.lat, lon: req.lon,
          taken_at: req.taken_at ?? null, thumb_url: null, caption: req.caption ?? null, ai_status: 'pending', base_votes: 0 })
        return json(201, { id: NEW_ID, ai_status: 'pending' })
      }
      const vote = path.match(/^\/api\/photos\/([^/]+)\/vote$/)
      if (vote && method === 'POST') {
        if (!token) return needAuth()
        const photo = state.photos.find(p => p.id === vote[1])
        if (!photo) return json(404, { error: { code: 'not_found', message: 'Photo not found' } })
        state.votes[photo.id] = (body as { value: number }).value
        return json(200, { photo_id: photo.id, vote_count: photo.base_votes + state.votes[photo.id], my_vote: state.votes[photo.id] })
      }
      const one = path.match(/^\/api\/photos\/([^/]+)$/)
      if (one && method === 'GET') {
        const photo = state.photos.find(p => p.id === one[1])
        return photo ? json(200, detail(photo, token)) : json(404, { error: { code: 'not_found', message: 'Photo not found' } })
      }
      return json(404, { error: { code: 'not_found', message: path } })
    })
  }

  return { state, install }
}

async function signIn(page: Page, username = 'stargazer') {
  await page.addInitScript(name => {
    window.localStorage.setItem('pleiades.session', JSON.stringify({ username: name, token: `tok-${name}` }))
  }, username)
}

async function waitForMap(page: Page) {
  await expect(page.getByText('Loading the map…', { exact: true })).not.toBeVisible({ timeout: 20000 })
}

test('photo pins render on the score map and the Photos toggle hides them and is remembered', async ({ page }) => {
  const api = photoApi()
  await api.install(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await waitForMap(page)
  const markers = page.locator('.photo-marker')
  await expect(markers).toHaveCount(2)
  await expect(page.locator('.photo-marker.placeholder')).toHaveCount(1)
  const toggle = page.getByRole('button', { name: /^Photos/ })
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await expect(toggle).toHaveText('Photos · 2')

  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'false')
  await expect(markers).toHaveCount(0)
  await page.reload()
  await waitForMap(page)
  await expect(page.getByRole('button', { name: /^Photos/ })).toHaveAttribute('aria-pressed', 'false')
  await expect(markers).toHaveCount(0)
  await page.getByRole('button', { name: /^Photos/ }).click()
  await expect(markers).toHaveCount(2)
  // The score map keeps working underneath.
  await expect(page.getByRole('slider')).toBeEnabled()
  expect(errors).toEqual([])
})

test('the viewer shows AI analysis, steps between photos and returns focus on Escape', async ({ page }) => {
  const api = photoApi()
  await api.install(page)
  await page.goto('/')
  await waitForMap(page)
  const marker = page.getByRole('button', { name: 'Open sky photo, taken Nov 6, 2026' })
  await marker.click()
  const viewer = page.getByRole('dialog', { name: '@nightowl' })
  await expect(viewer).toBeVisible()
  await expect(viewer.getByRole('button', { name: 'Close photo viewer' })).toBeFocused()
  await expect(viewer.getByText('Photo 1 of 2')).toBeVisible()
  await expect(viewer.getByText('Orion over the lake')).toBeVisible()
  await expect(viewer.getByText('A clear dark sky with Orion rising over the treeline.')).toBeVisible()
  await expect(viewer.getByRole('list', { name: 'Objects identified' })).toContainText('Orion · constellation 91%')
  await expect(viewer.getByText('7/10')).toBeVisible()
  await expect(viewer.getByText('Score at capture: 66')).toBeVisible()
  await expect(viewer.getByText(/from photo metadata/)).toBeVisible()

  await page.keyboard.press('ArrowRight')
  const second = page.getByRole('dialog', { name: '@lakeview' })
  await expect(second.getByText('Analyzing the sky…')).toBeVisible()
  await expect(second.getByText(/upload time/)).toBeVisible()
  await expect(second.getByRole('button', { name: 'Next photo' })).toHaveCount(0)
  await second.getByRole('button', { name: 'Previous photo' }).click()
  await expect(page.getByRole('dialog', { name: '@nightowl' })).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(marker).toBeFocused()
})

test('voting asks for a username first, sends the token, and toggles off on a second click', async ({ page }) => {
  const api = photoApi()
  await api.install(page)
  await page.goto('/')
  await waitForMap(page)
  await page.getByRole('button', { name: 'Open sky photo, taken Nov 6, 2026' }).click()
  const viewer = page.getByRole('dialog', { name: '@nightowl' })
  await viewer.getByRole('button', { name: 'Upvote' }).click()

  const prompt = page.getByRole('dialog', { name: 'Choose a username' })
  await expect(prompt).toBeVisible()
  await expect(prompt.getByText(/this browser is your account/)).toBeVisible()
  await prompt.getByLabel('Username').fill('x')
  await prompt.getByRole('button', { name: 'Continue' }).click()
  await expect(prompt.getByRole('alert')).toContainText('3–32 letters')
  await prompt.getByLabel('Username').fill('taken')
  await prompt.getByRole('button', { name: 'Continue' }).click()
  await expect(prompt.getByRole('alert')).toContainText('already taken')
  await prompt.getByLabel('Username').fill('stargazer')
  await prompt.getByRole('button', { name: 'Continue' }).click()
  await expect(prompt).toHaveCount(0)

  const upvote = viewer.getByRole('button', { name: 'Upvote' })
  await expect(upvote).toHaveAttribute('aria-pressed', 'true')
  await expect(viewer.getByLabel('4 net votes')).toBeVisible()
  const voteRequest = api.state.requests.find(r => r.path === `/api/photos/${DONE_ID}/vote`)
  expect(voteRequest?.auth).toBe('Bearer tok-stargazer')
  expect(voteRequest?.body).toEqual({ value: 1 })
  await expect(page.locator('.photo-signed-in')).toHaveText('@stargazer')

  await upvote.click()
  await expect(upvote).toHaveAttribute('aria-pressed', 'false')
  await expect(viewer.getByLabel('3 net votes')).toBeVisible()
  expect(api.state.requests.filter(r => r.path.endsWith('/vote')).at(-1)?.body).toEqual({ value: 0 })
})

test('uploading a photo with GPS EXIF pins it, stores it, and shows the analysis when it finishes', async ({ page }) => {
  const api = photoApi()
  await api.install(page)
  await signIn(page)
  await page.goto('/')
  await waitForMap(page)
  await page.getByRole('button', { name: 'Upload photo' }).click()
  const dialog = page.getByRole('dialog', { name: 'Share a sky photo' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Share photo' })).toBeDisabled()

  await dialog.locator('input[type="file"]').setInputFiles(GPS_PHOTO)
  await expect(dialog.getByText('42.85000, -78.75000')).toBeVisible()
  await expect(dialog.getByText(/from the photo’s GPS/)).toBeVisible()
  await expect(dialog.getByLabel('When was it taken? (Eastern time)')).toHaveValue('2026-11-07T22:14')
  await expect(page.locator('.draft-pin')).toHaveCount(1)
  await dialog.getByLabel('Caption (optional)').fill('First light from the backyard')
  await dialog.getByRole('button', { name: 'Share photo' }).click()

  const viewer = page.getByRole('dialog', { name: '@stargazer' })
  await expect(viewer).toBeVisible()
  await expect(viewer.getByText('Analyzing the sky…')).toBeVisible()
  await expect(viewer.getByText('First light from the backyard')).toBeVisible()

  const presign = api.state.requests.find(r => r.path === '/api/photos/presign')
  expect(presign?.auth).toBe('Bearer tok-stargazer')
  expect(presign?.body).toMatchObject({ content_type: 'image/jpeg', size: expect.any(Number) })
  const put = api.state.requests.find(r => r.method === 'PUT')
  expect(put?.path).toBe(`/fake-storage/photos/${NEW_ID}.jpg`)
  expect(put?.headers['content-type']).toBe('image/jpeg')
  const created = api.state.requests.find(r => r.method === 'POST' && r.path === '/api/photos')
  expect(created?.body).toEqual({
    s3_key: `photos/${NEW_ID}.jpg`, lat: 42.85, lon: -78.75, taken_at: '2026-11-08T03:14:00Z',
    taken_at_source: 'exif', caption: 'First light from the backyard',
  })

  // The worker finishes; the open viewer picks it up by polling.
  api.state.photos[0].ai_status = 'done'
  api.state.photos[0].thumb_url = PIXEL
  await expect(viewer.getByText('A clear dark sky with Orion rising over the treeline.')).toBeVisible({ timeout: 10000 })
  await page.keyboard.press('Escape')
  await expect(page.locator('.photo-marker')).toHaveCount(3)
  // The finished analysis refreshed the pins: only the other, still-pending photo lacks a thumbnail.
  await expect(page.locator('.photo-marker.placeholder')).toHaveCount(1)
})

test('a photo without GPS is placed by picking on the map, and storage outages are explained', async ({ page }) => {
  const api = photoApi()
  api.state.presignError = { status: 503, code: 'storage_unavailable', message: 'Photo storage is not configured' }
  await api.install(page)
  await signIn(page)
  await page.goto('/')
  await waitForMap(page)
  await page.getByRole('button', { name: 'Upload photo' }).click()
  const dialog = page.getByRole('dialog', { name: 'Share a sky photo' })
  await dialog.locator('input[type="file"]').setInputFiles(NO_GPS_PHOTO)
  await expect(dialog.getByText(/no location data/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Share photo' })).toBeDisabled()

  await dialog.getByRole('button', { name: 'Pick on map' }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('Click the map where you took this photo.')).toBeVisible()
  const map = (await page.locator('.map-container canvas').boundingBox())!
  await page.mouse.click(map.x + map.width * 0.6, map.y + map.height * 0.55)
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText(/picked on the map/)).toBeVisible()
  await expect(page.locator('.draft-pin')).toHaveCount(1)
  // Picking a location must not have opened a spot panel.
  await expect(page.getByRole('complementary')).toHaveCount(0)

  await dialog.getByRole('button', { name: 'Share photo' }).click()
  await expect(dialog.getByRole('alert')).toContainText('Photo uploads aren’t available right now')
  const created = api.state.requests.find(r => r.method === 'POST' && r.path === '/api/photos')
  expect(created).toBeUndefined()

  await dialog.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('.draft-pin')).toHaveCount(0)
})

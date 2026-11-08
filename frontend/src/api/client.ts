import type {
  ApiErrorBody,
  BestResponse,
  ScoreRangeResponse,
  ScoresResponse,
  SkyEventsResponse,
  SpotDetail,
  SpotDrift,
  SpotHistory,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'error' in body &&
    typeof (body as ApiErrorBody).error?.code === 'string'
  )
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    if (isApiErrorBody(body)) {
      throw new ApiError(response.status, body.error.code, body.error.message, body.error.details)
    }
    throw new ApiError(response.status, 'http_error', `Request failed with HTTP ${response.status}`)
  }
  if (body === null) {
    throw new ApiError(response.status, 'invalid_json', 'The server returned an unreadable response')
  }
  return body as T
}

export function fetchScoreRange(signal?: AbortSignal) {
  return getJson<ScoreRangeResponse>('/api/scores/range', signal)
}

/** `time` is an ISO-8601 UTC hour, e.g. 2026-11-08T03:00:00Z. Omit for the current hour. */
export function fetchScores(time?: string, signal?: AbortSignal) {
  const query = time ? `?${new URLSearchParams({ time })}` : ''
  return getJson<ScoresResponse>(`/api/scores${query}`, signal)
}

function withQuery(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const text = query.toString()
  return text ? `${path}?${text}` : path
}

/** Score, factors, conditions, and explanation for one cell at one UTC hour. */
export function fetchSpot(cellId: number, time?: string, signal?: AbortSignal) {
  return getJson<SpotDetail>(withQuery(`/api/spots/${cellId}`, { time }), signal)
}

/** Hourly scores (past week through the forecast) and nightly bests. */
export function fetchSpotHistory(cellId: number, signal?: AbortSignal) {
  return getJson<SpotHistory>(`/api/spots/${cellId}/history`, signal)
}

/** Every forecast revision for tonight. */
export function fetchSpotDrift(cellId: number, signal?: AbortSignal) {
  return getJson<SpotDrift>(`/api/spots/${cellId}/drift`, signal)
}

/** Top spots. Without `time`, ranks by tonight's best hour per spot. `near` is "lat,lon"; it adds `distance_km`. */
export function fetchBest(
  params: { time?: string; limit?: number; near?: string; radius_km?: number },
  signal?: AbortSignal,
) {
  return getJson<BestResponse>(withQuery('/api/best', params), signal)
}

/** Moon, twilight, planets, and events for a local night (defaults to tonight). */
export function fetchSkyEvents(signal?: AbortSignal, at?: { lat: number; lon: number }, date?: string) {
  return getJson<SkyEventsResponse>(withQuery('/api/sky-events', { lat: at?.lat, lon: at?.lon, date }), signal)
}

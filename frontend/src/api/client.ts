import type {
  ApiErrorBody,
  BestResponse,
  ChatContext,
  ChatMessage,
  ChatResponse,
  CreatePhotoRequest,
  CreatePhotoResponse,
  CreateUserResponse,
  Explanation,
  PhotoDetail,
  PhotoListResponse,
  PresignResponse,
  ScoreRangeResponse,
  ScoresResponse,
  SkyEventsResponse,
  SpotDetail,
  SpotDrift,
  SpotHistory,
  VoteResponse,
  VoteValue,
} from './types'
import { PAN_BOUNDS } from '../lib/region'
import { clearSession } from '../lib/session'

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

interface RequestOptions {
  method?: 'GET' | 'POST'
  /** Sent as JSON. */
  body?: unknown
  /** Bearer token for routes that need an account. A 401 signs this browser out. */
  token?: string
  signal?: AbortSignal
}

async function requestJson<T>(path: string, { method = 'GET', body: payload, token, signal }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (payload !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(path, {
    method,
    signal,
    headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    if (token && response.status === 401) clearSession()
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

function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { signal })
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

/** Plain-language explanation of the score. Can take a few seconds when it isn't cached yet. */
export function fetchSpotExplanation(cellId: number, time?: string, signal?: AbortSignal) {
  return getJson<Explanation>(withQuery(`/api/spots/${cellId}/explanation`, { time }), signal)
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

/** Ask the stargazing assistant. `messages` is the conversation so far, ending with the user's question. */
export function postChat(messages: ChatMessage[], context: ChatContext, signal?: AbortSignal) {
  return requestJson<ChatResponse>('/api/chat', { method: 'POST', body: { messages, context }, signal })
}

// ---- Community photos ----

/** Every visible photo in the navigable region, newest first. The region is small enough to load once. */
export function fetchPhotos(signal?: AbortSignal) {
  const [[west, south], [east, north]] = PAN_BOUNDS
  return getJson<PhotoListResponse>(
    withQuery('/api/photos', { bbox: `${west},${south},${east},${north}`, sort: 'recent', limit: 500 }),
    signal,
  )
}

/** One photo with its AI analysis. With a token, `my_vote` is filled in. */
export function fetchPhoto(id: string, token?: string, signal?: AbortSignal) {
  return requestJson<PhotoDetail>(`/api/photos/${encodeURIComponent(id)}`, { token, signal })
}

export function createUser(username: string) {
  return requestJson<CreateUserResponse>('/api/users', { method: 'POST', body: { username } })
}

/** A presigned PUT URL for one upload; the browser sends the file straight to storage. */
export function presignPhoto(token: string, contentType: string, size: number) {
  return requestJson<PresignResponse>('/api/photos/presign', {
    method: 'POST',
    token,
    body: { content_type: contentType, size },
  })
}

/** Register an uploaded object; the backend then queues thumbnail + AI analysis. */
export function createPhoto(token: string, body: CreatePhotoRequest) {
  return requestJson<CreatePhotoResponse>('/api/photos', { method: 'POST', token, body })
}

/** Demo reset: deletes every photo, its votes and its stored files. */
export function wipePhotos() {
  return requestJson<{ deleted: number }>('/api/photos/wipe', { method: 'POST' })
}

/** 1 = up, -1 = down, 0 = remove my vote. */
export function votePhoto(token: string, id: string, value: VoteValue) {
  return requestJson<VoteResponse>(`/api/photos/${encodeURIComponent(id)}/vote`, {
    method: 'POST',
    token,
    body: { value },
  })
}

/**
 * PUT the file to a presigned storage URL. XHR (not fetch) so upload progress can be shown.
 * `headers` must be exactly the presign response's headers: they are part of the signature.
 */
export function uploadToStorage(
  url: string,
  headers: Record<string, string>,
  file: Blob,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Upload cancelled', 'AbortError'))
      return
    }
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1)
        resolve()
      } else {
        reject(new ApiError(xhr.status, 'storage_upload_failed', `Photo storage rejected the upload (HTTP ${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'storage_unreachable', 'Photo storage could not be reached'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))
    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(file)
  })
}

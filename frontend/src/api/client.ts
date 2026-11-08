import type { ApiErrorBody, ScoreRangeResponse, ScoresResponse } from './types'

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

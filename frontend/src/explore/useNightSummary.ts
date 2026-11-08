import { useEffect, useState } from 'react'
import { nightDate, parseNightSummary } from './astronomy'
import type { NightSummary, ObservationContext } from './astronomy'

interface Result { key: string; data: NightSummary | null; error: string | null }

export function useNightSummary(context: ObservationContext) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const night = nightDate(context.time)
  const key = `${context.lat}:${context.lon}:${night}:${attempt}`
  useEffect(() => {
    const controller = new AbortController()
    let disposed = false
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    const params = new URLSearchParams({ lat: String(context.lat), lon: String(context.lon), date: night })
    fetch(`/api/sky-events?${params}`, { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async response => {
        if (!response.ok) throw new Error('Astronomy service is unavailable')
        return parseNightSummary(await response.json(), { lat: context.lat, lon: context.lon, time: context.time })
      })
      .then(data => { if (!disposed) setResult({ key, data, error: null }) })
      .catch(() => { if (!disposed) setResult({ key, data: null, error: 'Astronomy information could not be loaded. Educational models are still available.' }) })
      .finally(() => window.clearTimeout(timeout))
    return () => { disposed = true; window.clearTimeout(timeout); controller.abort() }
    // The API is night-based. Hour changes within the same night reuse its summary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.lat, context.lon, night, key])
  return { data: result?.key === key ? result.data : null, error: result?.key === key ? result.error : null,
    loading: result?.key !== key, retry: () => setAttempt(previous => previous + 1) }
}

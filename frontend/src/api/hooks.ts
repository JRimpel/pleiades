import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fetchBest, fetchScoreRange, fetchScores, fetchSkyEvents, fetchSpot, fetchSpotDrift, fetchSpotHistory } from './client'

export function useScoreRange() {
  return useQuery({
    queryKey: ['scores', 'range'],
    queryFn: ({ signal }) => fetchScoreRange(signal),
  })
}

/** Scores for one UTC hour. Keeps the previous hour on screen while the next one loads. */
export function useScores(time: string | undefined) {
  return useQuery({
    queryKey: ['scores', time ?? 'now'],
    queryFn: ({ signal }) => fetchScores(time, signal),
    placeholderData: keepPreviousData,
  })
}

const FIVE_MINUTES = 5 * 60 * 1000

/** One spot at one hour. Cached for a while because the Gemini explanation is slow to generate. */
export function useSpot(cellId: number | null, time: string | undefined) {
  return useQuery({
    queryKey: ['spot', cellId, time ?? 'now'],
    queryFn: ({ signal }) => fetchSpot(cellId as number, time, signal),
    enabled: cellId !== null,
    staleTime: FIVE_MINUTES,
    placeholderData: (previous) => (previous?.cell_id === cellId ? previous : undefined),
  })
}

export function useSpotHistory(cellId: number | null) {
  return useQuery({
    queryKey: ['spot', cellId, 'history'],
    queryFn: ({ signal }) => fetchSpotHistory(cellId as number, signal),
    enabled: cellId !== null,
    staleTime: FIVE_MINUTES,
  })
}

export function useSpotDrift(cellId: number | null) {
  return useQuery({
    queryKey: ['spot', cellId, 'drift'],
    queryFn: ({ signal }) => fetchSpotDrift(cellId as number, signal),
    enabled: cellId !== null,
    staleTime: FIVE_MINUTES,
  })
}

/** Keep coordinates in query keys coarse so GPS jitter doesn't trigger refetches. */
function roundTo(value: number, decimals: number) {
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}

/**
 * Tonight's top spots (nightly-best mode). Fetched only once `enabled` is true.
 * With `near`, only spots within `radiusKm` of it, each with `distance_km`.
 */
export function useBest(enabled: boolean, limit = 5, near?: { lat: number; lon: number }, radiusKm?: number) {
  // ~1 km precision.
  const nearParam = near ? `${roundTo(near.lat, 2)},${roundTo(near.lon, 2)}` : undefined
  return useQuery({
    queryKey: ['best', 'tonight', limit, nearParam ?? 'all', nearParam ? radiusKm : null],
    queryFn: ({ signal }) =>
      fetchBest({ limit, near: nearParam, radius_km: nearParam ? radiusKm : undefined }, signal),
    enabled,
    staleTime: FIVE_MINUTES,
  })
}

/** Tonight's sky at `at` (rounded to ~10 km; twilight times barely change over that) or the region centroid. */
export function useSkyEvents(enabled = true, at?: { lat: number; lon: number }) {
  const rounded = at ? { lat: roundTo(at.lat, 1), lon: roundTo(at.lon, 1) } : undefined
  return useQuery({
    queryKey: ['sky-events', 'tonight', rounded?.lat ?? 'centroid', rounded?.lon ?? 'centroid'],
    queryFn: ({ signal }) => fetchSkyEvents(signal, rounded),
    enabled,
    // Keep the previous answer visible (and the slider's Dark/Dawn ticks) while a new location loads.
    placeholderData: keepPreviousData,
    staleTime: 30 * 60 * 1000,
  })
}

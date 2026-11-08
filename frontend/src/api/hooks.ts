import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchBest,
  fetchPhoto,
  fetchPhotos,
  fetchScoreRange,
  fetchScores,
  fetchSkyEvents,
  fetchSpot,
  fetchSpotDrift,
  fetchSpotExplanation,
  fetchSpotHistory,
  votePhoto,
} from './client'
import type { PhotoDetail, VoteValue } from './types'
import type { Session } from '../lib/session'

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

/** One spot at one hour: score, factors and conditions. Fast; the explanation loads separately. */
export function useSpot(cellId: number | null, time: string | undefined) {
  return useQuery({
    queryKey: ['spot', cellId, time ?? 'now'],
    queryFn: ({ signal }) => fetchSpot(cellId as number, time, signal),
    enabled: cellId !== null,
    staleTime: FIVE_MINUTES,
    placeholderData: (previous) => (previous?.cell_id === cellId ? previous : undefined),
  })
}

/**
 * The score explanation for one spot-hour, when the spot detail didn't already include it.
 * `time` must be the spot's resolved `valid_time` so the key matches the hour being explained.
 */
export function useSpotExplanation(cellId: number | null, time: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['spot', cellId, time ?? 'now', 'explanation'],
    queryFn: ({ signal }) => fetchSpotExplanation(cellId as number, time, signal),
    enabled: enabled && cellId !== null,
    staleTime: 30 * 60 * 1000,
    retry: 1,
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

/** Selected local night's sky at `at` (rounded to ~10 km), or tonight at the region centroid. */
export function useSkyEvents(enabled = true, at?: { lat: number; lon: number }, date?: string) {
  const rounded = at ? { lat: roundTo(at.lat, 1), lon: roundTo(at.lon, 1) } : undefined
  return useQuery({
    queryKey: ['sky-events', date ?? 'tonight', rounded?.lat ?? 'centroid', rounded?.lon ?? 'centroid'],
    queryFn: ({ signal }) => fetchSkyEvents(signal, rounded, date),
    enabled,
    // Reuse nearby-location data only within the same night; never carry old-night ticks forward.
    placeholderData: previous => previous?.date === date ? previous : undefined,
    staleTime: 30 * 60 * 1000,
  })
}

// ---- Community photos ----

export const PHOTOS_KEY = ['photos', 'region'] as const

/** Map pins for every visible photo in the region. */
export function usePhotos(enabled: boolean) {
  return useQuery({
    queryKey: PHOTOS_KEY,
    queryFn: ({ signal }) => fetchPhotos(signal),
    enabled,
    staleTime: 60 * 1000,
  })
}

const PENDING_POLL_MS = 2000
/** Stop polling a stuck analysis after ~5 minutes; reopening the photo checks again. */
const MAX_PENDING_POLLS = 150

function photoKey(id: string | null, session: Session | null) {
  // The signed-in username is part of the key because `my_vote` depends on it.
  return ['photo', id, session?.username ?? 'anon'] as const
}

/** One photo. Polls while its AI analysis is still pending. */
export function usePhoto(id: string | null, session: Session | null) {
  return useQuery({
    queryKey: photoKey(id, session),
    queryFn: ({ signal }) => fetchPhoto(id as string, session?.token, signal),
    enabled: id !== null,
    staleTime: 30 * 1000,
    // Signing in changes the key; keep showing the same photo while it refetches with the token.
    placeholderData: (previous) => (previous?.id === id ? previous : undefined),
    refetchInterval: (query) =>
      query.state.data?.ai_status === 'pending' && query.state.dataUpdateCount < MAX_PENDING_POLLS
        ? PENDING_POLL_MS
        : false,
  })
}

interface VoteVariables {
  id: string
  value: VoteValue
  session: Session
}

/** Up/down/clear a vote, updating the open photo immediately and rolling back on failure. */
export function useVote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, value, session }: VoteVariables) => votePhoto(session.token, id, value),
    onMutate: async ({ id, value, session }) => {
      const key = photoKey(id, session)
      const previous = queryClient.getQueryData<PhotoDetail>(key)
      // Only cancel a refetch of data we're about to overwrite. Cancelling the first fetch
      // (e.g. right after signing in) would leave the query empty and never retried.
      if (previous) {
        await queryClient.cancelQueries({ queryKey: key })
        queryClient.setQueryData<PhotoDetail>(key, {
          ...previous,
          my_vote: value,
          vote_count: previous.vote_count - (previous.my_vote ?? 0) + value,
        })
      }
      return { key, previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous)
    },
    onSuccess: (result, { session }) => {
      const key = photoKey(result.photo_id, session)
      if (queryClient.getQueryData<PhotoDetail>(key)) {
        queryClient.setQueryData<PhotoDetail>(key, (photo) =>
          photo ? { ...photo, vote_count: result.vote_count, my_vote: result.my_vote } : photo,
        )
      } else {
        void queryClient.invalidateQueries({ queryKey: key })
      }
      void queryClient.invalidateQueries({ queryKey: PHOTOS_KEY })
    },
  })
}

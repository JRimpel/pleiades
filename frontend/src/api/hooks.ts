import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fetchScoreRange, fetchScores } from './client'

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

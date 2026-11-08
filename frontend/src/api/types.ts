// Mirrors backend/app/schemas/scores.py — keep in sync with the backend contract.
import type { FeatureCollection, Point, Polygon } from 'geojson'

export type ScoreLabel = 'Excellent' | 'Good' | 'Fair' | 'Poor'

export interface ScoreFeatureProperties {
  cell_id: number
  name: string | null
  /** 0–100, or null when the cell has no score for this hour. Never treat null as 0. */
  score: number | null
  label: ScoreLabel | null
  bortle: number | null
  top_factor: string | null
  is_curated: boolean
}

/** GeoJSON FeatureCollection plus the UTC hour the scores are valid for. */
export interface ScoresResponse extends FeatureCollection<Polygon | Point, ScoreFeatureProperties> {
  time: string
}

export interface ScoreRangeResponse {
  min_time: string | null
  max_time: string | null
  now: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: unknown
  }
}

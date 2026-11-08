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

// ---------- Spots (mirrors backend/app/schemas/spots.py) ----------

export interface Conditions {
  fetched_at: string
  cloud_low: number | null
  cloud_mid: number | null
  cloud_high: number | null
  cloud_total: number | null
  visibility_m: number | null
  rh: number | null
  dew_point_c: number | null
  temp_c: number | null
  wind_kmh: number | null
  precip_prob: number | null
}

export interface AstroSnapshot {
  time: string
  sun_alt: number | null
  moon_alt: number | null
  /** 0–1 */
  moon_illum: number | null
  moon_phase_deg: number | null
}

export interface Explanation {
  summary: string
  tips: string[]
}

export interface SpotDetail {
  cell_id: number
  name: string | null
  is_curated: boolean
  lat: number
  lon: number
  elevation_m: number | null
  sky_brightness_mpsas: number | null
  bortle: number | null
  valid_time: string
  score: number | null
  label: ScoreLabel | null
  nelm: number | null
  /** Points gained (+) or lost (−) per factor. */
  factors: Record<string, number> | null
  model_version: number | null
  computed_at: string | null
  conditions: Conditions | null
  astro: AstroSnapshot | null
  explanation: Explanation | null
}

export interface HistoryPoint {
  time: string
  score: number
  nelm: number | null
}

export interface NightlyBest {
  night: string
  best_score: number
  best_time: string | null
}

export interface SpotHistory {
  cell_id: number
  from_time: string
  to_time: string
  hourly: HistoryPoint[]
  nightly: NightlyBest[]
}

export interface DriftRevision {
  computed_at: string
  model_version: number
  peak_score: number
  points: { valid_time: string; score: number }[]
}

export interface SpotDrift {
  cell_id: number
  night: string
  window_start: string
  window_end: string
  revisions: DriftRevision[]
}

// ---------- Best spots (mirrors BestSpot / BestResponse in scores.py) ----------

export interface BestSpot {
  cell_id: number
  name: string | null
  is_curated: boolean
  lat: number
  lon: number
  score: number
  label: ScoreLabel | null
  bortle: number | null
  /** Hour of this score (the best hour of the night in nightly mode). */
  valid_time: string
  distance_km: number | null
}

export interface BestResponse {
  time: string | null
  night: string | null
  spots: BestSpot[]
}

// ---------- Sky events (mirrors backend/app/schemas/sky.py) ----------

export interface MoonInfo {
  /** 0 = new, 180 = full */
  phase_deg: number
  /** 0–1 */
  illumination: number
  phase_name: string
  rise: string | null
  set: string | null
}

export interface Twilight {
  sunset: string | null
  civil_dusk: string | null
  nautical_dusk: string | null
  astronomical_dusk: string | null
  astronomical_dawn: string | null
  sunrise: string | null
}

export interface PlanetVisibility {
  name: string
  rise: string | null
  set: string | null
  max_alt_deg: number | null
  magnitude: number | null
}

export interface SkyEvent {
  time: string
  type: string
  name: string
  details: Record<string, unknown> | null
}

export interface SkyEventsResponse {
  date: string
  lat: number
  lon: number
  moon: MoonInfo
  twilight: Twilight
  planets: PlanetVisibility[]
  events: SkyEvent[]
}

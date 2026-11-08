import type { ScoreLabel, ScoresResponse } from '../api/types'
import { haversineMiles } from './placeName'

/** Beyond this, the user isn't really "in" any cell (e.g. out on a lake or off the grid). */
const MAX_MILES = 6

export interface NearestCell {
  cellId: number
  name: string | null
  score: number | null
  label: ScoreLabel | null
  miles: number
}

/** Centre of a feature as [lon, lat]: the point itself, or the middle of a polygon's bounding box. */
export function featureCenter(geometry: ScoresResponse['features'][number]['geometry']): [number, number] | null {
  if (geometry.type === 'Point') return [geometry.coordinates[0], geometry.coordinates[1]]
  const ring = geometry.coordinates[0]
  if (!ring?.length) return null
  let west = Infinity
  let east = -Infinity
  let south = Infinity
  let north = -Infinity
  for (const [lon, lat] of ring) {
    west = Math.min(west, lon)
    east = Math.max(east, lon)
    south = Math.min(south, lat)
    north = Math.max(north, lat)
  }
  return [(west + east) / 2, (south + north) / 2]
}

/** The grid cell or curated spot closest to (lat, lon) in this hour's scores, or null if none is close. */
export function nearestCell(scores: ScoresResponse | undefined, lat: number, lon: number): NearestCell | null {
  if (!scores) return null
  let best: NearestCell | null = null
  for (const feature of scores.features) {
    const center = featureCenter(feature.geometry)
    if (!center) continue
    const miles = haversineMiles(lat, lon, center[1], center[0])
    if (miles <= MAX_MILES && (!best || miles < best.miles)) {
      const { cell_id, name, score, label } = feature.properties
      best = { cellId: cell_id, name, score, label, miles }
    }
  }
  return best
}

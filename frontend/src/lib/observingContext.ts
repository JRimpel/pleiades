import type { ScoresResponse, SpotDetail } from '../api/types'
import type { ObservationContext, ObservingConditions } from '../explore/astronomy'
import { isObservation } from '../explore/astronomy'
import { featureCenter } from './nearestCell'

/** Reuse map selection without treating map panning bounds as observing coverage. */
export function resolveObservingContext(time: string, cellId: number | null, spot: SpotDetail | undefined,
  scores: ScoresResponse | undefined, location: { lat: number; lon: number } | null) {
  const selectedSpot = spot?.cell_id === cellId ? spot : undefined
  const feature = scores?.features.find(item => item.properties.cell_id === cellId)
  const center = feature ? featureCenter(feature.geometry) : null
  const candidates = [
    { at: selectedSpot, label: 'Selected map spot' },
    { at: center ? { lat: center[1], lon: center[0] } : null, label: 'Selected map cell' },
    { at: location, label: 'Your location' },
    { at: { lat: 42.7, lon: -78.4 }, label: 'Western New York center' },
  ]
  const chosen = candidates.find(({ at }) => at && isObservation({ lat: at.lat, lon: at.lon, time }))!
  const observation: ObservationContext = { lat: chosen.at!.lat, lon: chosen.at!.lon, time }
  // Cached details may belong to a previous hour. Never attach that weather to the new time.
  const current = selectedSpot && Date.parse(selectedSpot.valid_time) === Date.parse(time)
    && selectedSpot.lat === observation.lat && selectedSpot.lon === observation.lon ? selectedSpot : undefined
  let conditions: ObservingConditions | undefined
  if (current && (current.conditions?.cloud_total != null || current.bortle != null)) {
    conditions = { cloudCoverPercent: current.conditions?.cloud_total ?? undefined, bortle: current.bortle ?? undefined,
      source: 'Selected spot forecast and static light-pollution estimate' }
  }
  return { observation, conditions, label: chosen.label }
}

// MapLibre uses [longitude, latitude].
export type Bounds = [[number, number], [number, number]]

/**
 * Extent of the drawn score data: grid centres (−79.8..−77.0, 42.0..43.3) plus the 1.5-step
 * fade margin that scoreSurface.ts draws around them. Used for the starting view.
 */
export const DATA_BOUNDS: Bounds = [
  [-79.95, 41.85],
  [-76.85, 43.45],
]

/** Panning limit: DATA_BOUNDS plus ~2° on every side. Also decides whether the user counts as "in the region". */
export const PAN_BOUNDS: Bounds = [
  [-81.95, 39.85],
  [-74.85, 45.45],
]

export function isWithinBounds(lat: number, lon: number, [[west, south], [east, north]]: Bounds = PAN_BOUNDS) {
  return lon >= west && lon <= east && lat >= south && lat <= north
}

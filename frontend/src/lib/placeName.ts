import { WNY_TOWNS } from './wnyTowns'
import type { Town } from './wnyTowns'

const EARTH_RADIUS_MI = 3958.8
const toRad = (deg: number) => (deg * Math.PI) / 180

export function haversineMiles(aLat: number, aLon: number, bLat: number, bLon: number) {
  const dLat = toRad(bLat - aLat)
  const dLon = toRad(bLon - aLon)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h))
}

/** "4.2 mi" under 10 miles, "42 mi" above. */
export function formatMiles(miles: number) {
  return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`
}

/** Initial compass bearing (0 = north, clockwise) from point a to point b. */
export function bearingDeg(aLat: number, aLon: number, bLat: number, bLon: number) {
  const dLon = toRad(bLon - aLon)
  const y = Math.sin(dLon) * Math.cos(toRad(bLat))
  const x = Math.cos(toRad(aLat)) * Math.sin(toRad(bLat)) - Math.sin(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.cos(dLon)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

function compass(deg: number) {
  return COMPASS[Math.round(deg / 45) % 8]
}

/** "42.50° N, 77.30° W" */
export function formatCoords(lat: number, lon: number) {
  return `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? 'E' : 'W'}`
}

function nearestTown(lat: number, lon: number): { town: Town; miles: number } {
  let best = WNY_TOWNS[0]
  let bestMiles = Infinity
  for (const town of WNY_TOWNS) {
    const miles = haversineMiles(town.lat, town.lon, lat, lon)
    if (miles < bestMiles) {
      best = town
      bestMiles = miles
    }
  }
  return { town: best, miles: bestMiles }
}

/** Human-readable place for an unnamed spot, e.g. "5 mi SW of Naples". */
export function describeLocation(lat: number, lon: number) {
  const { town, miles } = nearestTown(lat, lon)
  const title =
    miles < 1
      ? `In ${town.name}`
      : `${Math.round(miles)} mi ${compass(bearingDeg(town.lat, town.lon, lat, lon))} of ${town.name}`
  return { title, coords: formatCoords(lat, lon) }
}

/** The spot's own name when it has one (curated spots), otherwise a nearest-town description. */
export function spotTitle(spot: { name: string | null; lat: number; lon: number }) {
  return spot.name ?? describeLocation(spot.lat, spot.lon).title
}

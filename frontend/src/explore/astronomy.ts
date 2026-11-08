import type { CelestialObject } from './catalog'

export interface ObservationContext { lat: number; lon: number; time: string }
export interface ObservingConditions { cloudCoverPercent?: number; bortle?: number; source?: string }
export interface PhotoIdentification { name: string; confidence?: number }
export interface PlanetVisibility { name: string; rise: string | null; set: string | null; max_alt_deg: number | null }
export interface NightSummary {
  date: string; lat: number; lon: number
  twilight: { sunset: string | null; astronomical_dusk: string | null; astronomical_dawn: string | null; sunrise: string | null }
  moon: { illumination: number; phase_name: string; rise: string | null; set: string | null }
  planets: PlanetVisibility[]
}
export interface Availability { label: string; detail: string; tone: 'positive' | 'neutral' | 'muted'; rise?: string | null; set?: string | null; aboveHorizon?: boolean | null; altitudeDeg?: number }
export const REGION_TIMEZONE = 'America/New_York'

export function nightDate(iso: string): string {
  const values = new Intl.DateTimeFormat('en-CA', { timeZone: REGION_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(iso))
  const part = (type: Intl.DateTimeFormatPartTypes) => values.find(value => value.type === type)!.value
  const day = `${part('year')}-${part('month')}-${part('day')}`
  const noon = new Date(day + 'T12:00:00Z')
  if (Number(part('hour')) < 12) noon.setUTCDate(noon.getUTCDate() - 1)
  return noon.toISOString().slice(0, 10)
}

export function localTime(iso: string | null | undefined): string {
  if (!iso || !Number.isFinite(Date.parse(iso))) return 'Not supplied'
  return new Intl.DateTimeFormat('en-US', { timeZone: REGION_TIMEZONE, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(new Date(iso))
}

export function isObservation(value: ObservationContext): boolean {
  return Number.isFinite(value.lat) && Number.isFinite(value.lon) && value.lat >= 42 && value.lat <= 43.4 && value.lon >= -79.8 && value.lon <= -77 && Number.isFinite(Date.parse(value.time))
}

export function parseNightSummary(raw: unknown, context: ObservationContext): NightSummary {
  if (!raw || typeof raw !== 'object') throw new Error('Unexpected astronomy response')
  const body = raw as NightSummary
  if (body.date !== nightDate(context.time) || Math.abs(body.lat - context.lat) > .0001 || Math.abs(body.lon - context.lon) > .0001 || !Number.isFinite(body.lat) || !Number.isFinite(body.lon) || !Array.isArray(body.planets) || !body.twilight || !body.moon || !body.planets.every(p => typeof p.name === 'string')) {
    throw new Error('Astronomy response does not match the selected location/night')
  }
  return body
}

export function aboveFromEvents(time: string, rise: string | null, set: string | null): boolean | null {
  const t = Date.parse(time), r = Date.parse(rise ?? ''), s = Date.parse(set ?? '')
  if (![t, r, s].every(Number.isFinite) || r === s) return null
  return r < s ? t >= r && t < s : t >= r || t < s
}

// Approximate geometric altitude using J2000 catalog coordinates and mean sidereal
// time. UTC approximates UT1; precession, nutation, proper motion and refraction
// are omitted. This is a horizon estimate for browsing, not pointing precision.
// Formulae: https://aa.usno.navy.mil/faq/GAST and /faq/alt_az
export function catalogAltitude(position: CelestialObject['catalogPosition'], context: ObservationContext): number | null {
  if (!position || !isObservation(context) || !Number.isFinite(position.raHours) || !Number.isFinite(position.decDeg)
    || position.raHours < 0 || position.raHours >= 24 || Math.abs(position.decDeg) > 90) return null
  const jd = Date.parse(context.time) / 86400000 + 2440587.5
  const midnight = Math.floor(jd - .5) + .5
  const hours = (jd - midnight) * 24
  const centuries = (jd - 2451545) / 36525
  const gmst = 6.697375 + .065709824279 * (midnight - 2451545) + 1.0027379 * hours + .0000258 * centuries ** 2
  const radians = Math.PI / 180
  const hourAngle = ((gmst - position.raHours) * 15 + context.lon) * radians
  const dec = position.decDeg * radians
  const lat = context.lat * radians
  const sine = Math.cos(hourAngle) * Math.cos(dec) * Math.cos(lat) + Math.sin(dec) * Math.sin(lat)
  return Math.asin(Math.max(-1, Math.min(1, sine))) / radians
}

export function availabilityFor(object: CelestialObject, context: ObservationContext, summary: NightSummary | null): Availability {
  if (object.category !== 'Planet' && object.category !== 'Moon') {
    const altitude = catalogAltitude(object.catalogPosition, context)
    if (altitude !== null) {
      const above = altitude > 0
      const center = object.category === 'Constellation'
      return {
        label: center ? `Center ${above ? 'above' : 'below'} horizon · estimated` : `${above ? 'Above' : 'Below'} horizon · estimated`,
        detail: `${center ? 'Constellation center' : 'Catalog position'} is approximately ${Math.round(Math.abs(altitude))}° ${above ? 'above' : 'below'} a flat horizon at the selected time. ${center ? 'Parts of the constellation may be on either side of the horizon. ' : ''}This approximate catalog-based estimate excludes refraction and small coordinate changes since J2000. Daylight, weather, terrain, brightness and equipment still limit observing.`,
        tone: above ? 'positive' : 'neutral', aboveHorizon: above, altitudeDeg: altitude,
      }
    }
  }
  if (!summary || summary.date !== nightDate(context.time) || Math.abs(summary.lat - context.lat) > .0001 || Math.abs(summary.lon - context.lon) > .0001) {
    return { label: 'Visibility not calculated', detail: 'Explore the educational model while astronomy information is unavailable.', tone: 'muted' }
  }
  if (object.category !== 'Planet' && object.category !== 'Moon') {
    return { label: 'Visibility not calculated', detail: 'No usable catalog position is available for this object.', tone: 'muted' }
  }
  const planet = object.category === 'Moon' ? { name: 'Moon', ...summary.moon } : summary.planets.find(p => p.name.toLowerCase() === object.name.toLowerCase())
  if (!planet) return { label: 'Not listed for this night', detail: 'The nightly response does not list this planet. This is not an exact selected-time altitude calculation.', tone: 'muted' }
  const above = aboveFromEvents(context.time, planet.rise, planet.set)
  return {
    label: above === null ? 'Listed during this night' : above ? 'Above horizon · estimated' : 'Below horizon · estimated',
    detail: above === null ? 'Rise/set information is incomplete, so availability at the selected hour is not calculated.' : 'Estimated from the backend’s local-night rise/set crossings. Weather, daylight, terrain and equipment can still limit observing.',
    tone: above ? 'positive' : 'neutral', rise: planet.rise, set: planet.set, aboveHorizon: above,
  }
}

export function sortByVisibility(objects: readonly CelestialObject[], context: ObservationContext, summary: NightSummary | null): CelestialObject[] {
  const rank = (above: boolean | null | undefined) => above === true ? 0 : above === false ? 2 : 1
  return objects.map(object => ({ object, visibility: availabilityFor(object, context, summary) }))
    .sort((a, b) => rank(a.visibility.aboveHorizon) - rank(b.visibility.aboveHorizon)
      || (b.visibility.altitudeDeg ?? -90) - (a.visibility.altitudeDeg ?? -90)
      || a.object.name.localeCompare(b.object.name, 'en', { numeric: true })
      || a.object.id.localeCompare(b.object.id))
    .map(({ object }) => object)
}

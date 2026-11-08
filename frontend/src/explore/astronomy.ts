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
export interface Availability { label: string; detail: string; tone: 'positive' | 'neutral' | 'muted'; rise?: string | null; set?: string | null }
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

export function availabilityFor(object: CelestialObject, context: ObservationContext, summary: NightSummary | null): Availability {
  if (!summary || summary.date !== nightDate(context.time) || Math.abs(summary.lat - context.lat) > .0001 || Math.abs(summary.lon - context.lon) > .0001) {
    return { label: 'Visibility not calculated', detail: 'Explore the educational model while astronomy information is unavailable.', tone: 'muted' }
  }
  if (object.category !== 'Planet') {
    return { label: 'Visibility not calculated', detail: 'The current API provides planet and Moon summaries. It does not supply this object’s selected-time position.', tone: 'muted' }
  }
  const planet = summary.planets.find(p => p.name.toLowerCase() === object.name.toLowerCase())
  if (!planet) return { label: 'Not listed for this night', detail: 'The nightly response does not list this planet. This is not an exact selected-time altitude calculation.', tone: 'muted' }
  const above = aboveFromEvents(context.time, planet.rise, planet.set)
  return {
    label: above === null ? 'Listed during this night' : above ? 'Above horizon · estimated' : 'Below horizon · estimated',
    detail: above === null ? 'Rise/set information is incomplete, so availability at the selected hour is not calculated.' : 'Estimated from the backend’s local-night rise/set crossings. Weather, daylight, terrain and equipment can still limit observing.',
    tone: above ? 'positive' : 'neutral', rise: planet.rise, set: planet.set,
  }
}

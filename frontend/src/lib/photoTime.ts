/**
 * Capture-time helpers for uploaded photos. Pure (no DOM, no dependencies) so they can be
 * unit-tested in Node.
 *
 * EXIF stores "YYYY:MM:DD HH:MM:SS" wall-clock time, sometimes with an "OffsetTimeOriginal"
 * like "-05:00". Without an offset the time is read as Western New York local time (the app
 * covers only WNY), not the browser's zone, so a photo taken here reads the same wherever
 * it's uploaded from.
 */

export const REGION_TZ = 'America/New_York'

const EXIF_TIME = /^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/
const UTC_OFFSET = /^([+-])(\d{2}):?(\d{2})$/
const INPUT_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/

interface WallTime {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

function parseWallTime(match: RegExpMatchArray): WallTime | undefined {
  const [year, month, day, hour, minute] = match.slice(1, 6).map(Number)
  const second = match[6] ? Number(match[6]) : 0
  const wall = { year, month, day, hour, minute, second }
  // Reject impossible dates (e.g. 2026:02:31) and the all-zero "unset" EXIF value.
  const check = new Date(Date.UTC(year, month - 1, day, hour, minute, second))
  if (
    year < 1990 ||
    check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1 || check.getUTCDate() !== day ||
    check.getUTCHours() !== hour || check.getUTCMinutes() !== minute || check.getUTCSeconds() !== second
  ) {
    return undefined
  }
  return wall
}

const partsFormatters: Record<string, Intl.DateTimeFormat> = {}

/** How far `timeZone` is ahead of UTC at the instant `utcMs`, in ms. */
function zoneOffsetMs(utcMs: number, timeZone: string) {
  partsFormatters[timeZone] ??= new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  const parts = partsFormatters[timeZone].formatToParts(new Date(utcMs))
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value)
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'))
  return asUtc - Math.floor(utcMs / 1000) * 1000
}

/** The UTC instant for a wall-clock time in `timeZone`. Repeated DST hours resolve to the first one. */
function wallTimeToUtcMs(wall: WallTime, timeZone: string) {
  const naive = Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute, wall.second)
  // Try the offsets in effect a few hours either side, and keep the earliest that round-trips.
  const offsets = new Set([zoneOffsetMs(naive - 6 * 3_600_000, timeZone), zoneOffsetMs(naive + 6 * 3_600_000, timeZone)])
  const candidates = [...offsets]
    .map((offset) => naive - offset)
    .filter((utc) => zoneOffsetMs(utc, timeZone) === naive - utc)
    .sort((a, b) => a - b)
  // A skipped (spring-forward) hour has no exact match; fall back to the pre-transition offset.
  return candidates[0] ?? naive - zoneOffsetMs(naive - 6 * 3_600_000, timeZone)
}

/** ISO-8601 UTC without milliseconds, e.g. 2026-11-08T03:12:00Z. */
function toIso(ms: number) {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** EXIF capture time → UTC ISO string, or undefined when missing or invalid. */
export function exifTimeToIso(raw: unknown, offset?: unknown, timeZone = REGION_TZ): string | undefined {
  if (typeof raw !== 'string') return undefined
  const match = raw.trim().match(EXIF_TIME)
  const wall = match && parseWallTime(match)
  if (!wall) return undefined
  const offsetMatch = typeof offset === 'string' ? offset.trim().match(UTC_OFFSET) : null
  if (offsetMatch) {
    const sign = offsetMatch[1] === '-' ? -1 : 1
    const minutes = sign * (Number(offsetMatch[2]) * 60 + Number(offsetMatch[3]))
    const naive = Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute, wall.second)
    return toIso(naive - minutes * 60_000)
  }
  return toIso(wallTimeToUtcMs(wall, timeZone))
}

/** UTC ISO → "YYYY-MM-DDTHH:MM" in `timeZone`, for a `datetime-local` input. */
export function isoToInputValue(iso: string, timeZone = REGION_TZ): string {
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return ''
  const local = new Date(Math.floor(ms / 1000) * 1000 + zoneOffsetMs(ms, timeZone))
  return local.toISOString().slice(0, 16)
}

/** A `datetime-local` value read as `timeZone` wall time → UTC ISO, or undefined if invalid. */
export function inputValueToIso(value: string, timeZone = REGION_TZ): string | undefined {
  const match = value.trim().match(INPUT_TIME)
  const wall = match && parseWallTime(match)
  return wall ? toIso(wallTimeToUtcMs(wall, timeZone)) : undefined
}

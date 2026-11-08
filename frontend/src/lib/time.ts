export const HOUR_MS = 60 * 60 * 1000

const localHourFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
})

export function formatLocalHour(ms: number) {
  return localHourFormat.format(new Date(ms))
}

/** ISO-8601 UTC without milliseconds, e.g. 2026-11-08T03:00:00Z. */
export function toIsoHour(ms: number) {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
}

const localTimeFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: 'numeric',
  minute: '2-digit',
})

const localDayTimeFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
})

/** "11:42 PM" in Eastern time, or "—" when missing. */
export function formatLocalTime(iso: string | null | undefined) {
  return iso ? localTimeFormat.format(new Date(iso)) : '—'
}

/** "Sat 11:42 PM" in Eastern time, or "—" when missing. */
export function formatLocalDayTime(iso: string | null | undefined) {
  return iso ? localDayTimeFormat.format(new Date(iso)) : '—'
}

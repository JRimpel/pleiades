import assert from 'node:assert/strict'
import test from 'node:test'
import { aboveFromEvents, availabilityFor, isObservation, localTime, nightDate, parseNightSummary } from '../src/explore/astronomy.ts'

const context = { lat: 42.7, lon: -78.4, time: '2026-11-08T04:00:00Z' }
const summary = { date: '2026-11-07', lat: 42.7, lon: -78.4,
  moon: { phase_name: 'Test phase', illumination: .1, rise: null, set: null },
  twilight: { sunset: null, sunrise: null, astronomical_dusk: null, astronomical_dawn: null },
  planets: [{ name: 'Saturn', rise: '2026-11-07T20:00:00Z', set: '2026-11-08T07:00:00Z', max_alt_deg: 40 }] }
const planet = { name: 'Saturn', category: 'Planet' } as Parameters<typeof availabilityFor>[0]

test('NY night dates remain correct through repeated DST hours and local noon', () => {
  assert.equal(nightDate('2026-11-01T05:30:00Z'), '2026-10-31')
  assert.equal(nightDate('2026-11-01T06:30:00Z'), '2026-10-31')
  assert.equal(nightDate('2026-11-01T16:00:00Z'), '2026-10-31')
  assert.equal(nightDate('2026-11-01T17:00:00Z'), '2026-11-01')
  assert.match(localTime('2026-11-01T05:30:00Z'), /EDT/)
  assert.match(localTime('2026-11-01T06:30:00Z'), /EST/)
})
test('rise/set estimates cover normal and wrapped night intervals; missing data is unknown', () => {
  assert.equal(aboveFromEvents(context.time, summary.planets[0].rise, summary.planets[0].set), true)
  assert.equal(aboveFromEvents(context.time, '2026-11-08T06:00:00Z', '2026-11-07T21:00:00Z'), false)
  assert.equal(aboveFromEvents('2026-11-07T18:00:00Z', '2026-11-08T06:00:00Z', '2026-11-07T21:00:00Z'), true)
  assert.equal(aboveFromEvents(context.time, null, summary.planets[0].set), null)
})
test('stale or incomplete summaries never imply selected-time visibility', () => {
  assert.match(availabilityFor(planet, context, summary).label, /estimated/)
  assert.equal(availabilityFor(planet, { ...context, lat: 43 }, summary).label, 'Visibility not calculated')
  assert.equal(availabilityFor({ ...planet, category: 'Star' }, context, summary).label, 'Visibility not calculated')
  assert.equal(availabilityFor(planet, context, { ...summary, planets: [] }).label, 'Not listed for this night')
  assert.throws(() => parseNightSummary({ ...summary, date: '2026-11-08' }, context))
  assert.throws(() => parseNightSummary({ ...summary, lat: undefined }, context))
  assert.equal(parseNightSummary(summary, context).date, summary.date)
})
test('out of region/invalid observing context is rejected', () => {
  assert.equal(isObservation(context), true)
  assert.equal(isObservation({ ...context, lat: 100 }), false)
  assert.equal(isObservation({ ...context, time: 'not a date' }), false)
})

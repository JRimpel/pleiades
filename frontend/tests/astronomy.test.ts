import assert from 'node:assert/strict'
import test from 'node:test'
import { aboveFromEvents, availabilityFor, catalogAltitude, isObservation, localTime, nightDate, parseNightSummary, sortByVisibility } from '../src/explore/astronomy.ts'

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

test('catalog altitude handles pole geometry, a known transit, time, and invalid coordinates', () => {
  assert.ok(Math.abs(catalogAltitude({ raHours: 0, decDeg: 90 }, context)! - context.lat) < 1e-9)
  assert.ok(Math.abs(catalogAltitude({ raHours: 0, decDeg: -90 }, context)! + context.lat) < 1e-9)
  // J2000 noon: GMST ~18.6973746h; matching local RA/declination passes overhead.
  const epoch = { ...context, time: '2000-01-01T12:00:00Z' }
  const overhead = { raHours: 18.6973746 + context.lon / 15, decDeg: context.lat }
  assert.ok(catalogAltitude(overhead, epoch)! > 89.99)
  assert.ok(catalogAltitude(overhead, { ...epoch, time: '2000-01-02T00:00:00Z' })! < 0)
  assert.notEqual(catalogAltitude({ raHours: 5, decDeg: 0 }, context), catalogAltitude({ raHours: 5, decDeg: 0 }, { ...context, lon: -77 }))
  assert.equal(catalogAltitude(undefined, context), null)
  assert.equal(catalogAltitude({ raHours: NaN, decDeg: 0 }, context), null)
  assert.equal(catalogAltitude({ raHours: 0, decDeg: 91 }, context), null)
  assert.equal(catalogAltitude(overhead, { ...context, time: 'bad' }), null)
})

test('visibility sorts above, unknown, below without mutating the catalog or requiring the API', () => {
  const star = (id: string, decDeg?: number) => ({ ...planet, id, name: id, category: 'Star',
    catalogPosition: decDeg === undefined ? undefined : { raHours: 0, decDeg } }) as Parameters<typeof sortByVisibility>[0][number]
  const objects = [star('below', -90), star('unknown'), star('above', 90)]
  assert.deepEqual(sortByVisibility(objects, context, null).map(object => object.id), ['above', 'unknown', 'below'])
  assert.deepEqual(objects.map(object => object.id), ['below', 'unknown', 'above'])
  assert.equal(availabilityFor(objects[2], context, null).aboveHorizon, true)
  assert.equal(availabilityFor(objects[0], context, null).aboveHorizon, false)
  assert.match(availabilityFor({ ...objects[2], category: 'Constellation' }, context, null).detail, /Parts of the constellation/)
  const epoch = { ...context, time: '2000-01-01T12:00:00Z' }
  const zenith = { ...objects[2], id: 'zenith', name: 'Zenith', catalogPosition: { raHours: 18.6973746 + context.lon / 15, decDeg: context.lat } }
  assert.deepEqual(sortByVisibility([objects[2], zenith], epoch, null).map(object => object.id), ['zenith', 'above'])
})

test('planet and Moon sorting uses rise/set crossings; stale and missing events stay unknown', () => {
  assert.equal(availabilityFor(planet, context, summary).aboveHorizon, true)
  assert.equal(availabilityFor(planet, { ...context, time: '2026-11-08T08:00:00Z' }, summary).aboveHorizon, false)
  assert.equal(availabilityFor(planet, context, { ...summary, planets: [{ ...summary.planets[0], rise: null }] }).aboveHorizon, null)
  const moon = { ...planet, name: 'Moon', category: 'Moon' } as typeof planet
  assert.equal(availabilityFor(moon, context, { ...summary, moon: { ...summary.moon, rise: '2026-11-07T20:00:00Z', set: '2026-11-08T07:00:00Z' } }).aboveHorizon, true)
  assert.equal(availabilityFor(planet, { ...context, lat: 43 }, summary).aboveHorizon, undefined)
})

import assert from 'node:assert/strict'
import test from 'node:test'
import { exifTimeToIso, inputValueToIso, isoToInputValue } from '../src/lib/photoTime.ts'

test('EXIF time with an explicit offset uses that offset', () => {
  assert.equal(exifTimeToIso('2026:11:07 22:14:05', '-05:00'), '2026-11-08T03:14:05Z')
  assert.equal(exifTimeToIso('2026:07:04 23:30:00', '+0200'), '2026-07-04T21:30:00Z')
})

test('EXIF time without an offset is read as Western New York time, across DST', () => {
  // EST (UTC-5) in November, EDT (UTC-4) in July.
  assert.equal(exifTimeToIso('2026:11:07 22:14:05'), '2026-11-08T03:14:05Z')
  assert.equal(exifTimeToIso('2026:07:04 23:30:00'), '2026-07-05T03:30:00Z')
})

test('the repeated fall-back hour resolves to its first occurrence', () => {
  // 2026-11-01 01:30 happens twice in New York; the first is EDT (UTC-4).
  assert.equal(exifTimeToIso('2026:11:01 01:30:00'), '2026-11-01T05:30:00Z')
})

test('missing, unset and impossible EXIF times are ignored', () => {
  assert.equal(exifTimeToIso(undefined), undefined)
  assert.equal(exifTimeToIso('0000:00:00 00:00:00'), undefined)
  assert.equal(exifTimeToIso('2026:02:31 10:00:00'), undefined)
  assert.equal(exifTimeToIso('not a date'), undefined)
  assert.equal(exifTimeToIso(new Date()), undefined)
})

test('datetime-local values round-trip in Eastern time', () => {
  assert.equal(isoToInputValue('2026-11-08T03:14:05Z'), '2026-11-07T22:14')
  assert.equal(inputValueToIso('2026-11-07T22:14'), '2026-11-08T03:14:00Z')
  assert.equal(inputValueToIso('2026-07-04T23:30'), '2026-07-05T03:30:00Z')
  assert.equal(inputValueToIso(''), undefined)
  assert.equal(isoToInputValue('garbage'), '')
})

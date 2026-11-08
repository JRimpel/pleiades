import { exifTimeToIso } from './photoTime'

/** What a photo's EXIF says about where and when it was taken. Every field is optional. */
export interface PhotoMetadata {
  lat?: number
  lon?: number
  /** UTC ISO string. */
  takenAt?: string
}

/**
 * Read GPS position and capture time from a photo. Never throws: missing, stripped
 * (common on phones) or unreadable metadata just leaves fields undefined.
 * `exifr` loads on first use so the map doesn't pay for it up front.
 */
export async function readPhotoMetadata(file: Blob): Promise<PhotoMetadata> {
  const result: PhotoMetadata = {}
  let exifr: typeof import('exifr').default
  try {
    exifr = (await import('exifr')).default
  } catch {
    return result
  }

  try {
    const gps = await exifr.gps(file)
    const { latitude, longitude } = gps ?? {}
    // 0,0 is what some apps write when location is off.
    if (Number.isFinite(latitude) && Number.isFinite(longitude) && !(latitude === 0 && longitude === 0)) {
      result.lat = latitude
      result.lon = longitude
    }
  } catch {
    // No GPS block.
  }

  try {
    // Raw strings (reviveValues: false) so the UTC offset is applied explicitly.
    const tags = await exifr.parse(file, {
      pick: ['DateTimeOriginal', 'OffsetTimeOriginal', 'CreateDate', 'OffsetTimeDigitized'],
      reviveValues: false,
    })
    const takenAt =
      exifTimeToIso(tags?.DateTimeOriginal, tags?.OffsetTimeOriginal) ??
      exifTimeToIso(tags?.CreateDate, tags?.OffsetTimeDigitized)
    // Ignore clocks set in the future.
    if (takenAt && Date.parse(takenAt) <= Date.now() + 60 * 60 * 1000) result.takenAt = takenAt
  } catch {
    // No EXIF block.
  }
  return result
}

import { useEffect, useState } from 'react'

/** The user's last known position from the browser. */
export interface UserLocation {
  lat: number
  lon: number
  /** Radius of the 95% confidence circle, in metres. */
  accuracyM: number
  /** Epoch ms when the browser took the fix. */
  timestamp: number
}

export type LocationError = 'unsupported' | 'insecure' | 'denied' | 'unavailable' | 'timeout'

const WATCH_OPTIONS: PositionOptions = { enableHighAccuracy: true, maximumAge: 30_000, timeout: 20_000 }

/** Reasons geolocation can't work at all in this browser or page. */
function blockedReason(): LocationError | null {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return 'unsupported'
  // Browsers only allow geolocation on HTTPS or localhost.
  if (!window.isSecureContext) return 'insecure'
  return null
}

/**
 * Live user position. Call it once (in App) and pass the result down, so every feature shares
 * one browser watch. Asks for permission as soon as it mounts.
 */
export function useUserLocation(): { location: UserLocation | null; error: LocationError | null } {
  const [location, setLocation] = useState<UserLocation | null>(null)
  const [watchError, setWatchError] = useState<LocationError | null>(null)
  const blocked = blockedReason()

  useEffect(() => {
    if (blockedReason()) return
    const watchId = navigator.geolocation.watchPosition(
      (position) => {
        setLocation({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          accuracyM: position.coords.accuracy,
          timestamp: position.timestamp,
        })
        setWatchError(null)
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          setLocation(null)
          setWatchError('denied')
        } else {
          // Timeouts and lost signal are often temporary: keep the last good position.
          setWatchError(error.code === error.TIMEOUT ? 'timeout' : 'unavailable')
        }
      },
      WATCH_OPTIONS,
    )
    return () => navigator.geolocation.clearWatch(watchId)
  }, [])

  return { location: blocked ? null : location, error: blocked ?? watchError }
}

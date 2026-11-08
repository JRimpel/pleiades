import { useEffect, useId, useRef, useState } from 'react'
import { useBest } from '../api/hooks'
import type { BestSpot } from '../api/types'
import { formatMiles, haversineMiles, spotTitle } from '../lib/placeName'
import { scoreToRgb } from '../lib/scoreColors'
import { formatLocalTime } from '../lib/time'
import type { UserLocation } from '../lib/useUserLocation'

interface BestSpotsProps {
  onPick: (spot: BestSpot) => void
  /** First hour the slider can show; best hours before it are labeled "earlier tonight". */
  firstHourMs?: number
  /** The user's position, only when inside the region. Enables "Near me" and distances. */
  userLocation?: UserLocation | null
}

const NEAR_RADIUS_KM = 80
const NEAR_RADIUS_LABEL = '50 mi'
const KM_TO_MI = 0.621371

/** Distance from the user: the backend's value in "near me" mode, otherwise straight-line from the user. */
function spotMiles(spot: BestSpot, location: UserLocation | null | undefined) {
  if (spot.distance_km !== null) return spot.distance_km * KM_TO_MI
  if (!location) return null
  return haversineMiles(location.lat, location.lon, spot.lat, spot.lon)
}

function swatch(score: number) {
  const [r, g, b] = scoreToRgb(score)
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}

/** "Tonight's best" button with a ranked list of the top spots and their best hour. */
function BestSpots({ onPick, firstHourMs, userLocation }: BestSpotsProps) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [requested, setRequested] = useState(false)
  const [scope, setScope] = useState<'near' | 'all'>('near')
  const nearMe = scope === 'near' && !!userLocation
  // Pick the #1 spot automatically when the list first arrives after a click.
  const autoPick = useRef(false)
  const best = useBest(requested, 5, nearMe ? userLocation : undefined, NEAR_RADIUS_KM)
  const spots = best.data?.spots ?? []
  const topSpot = best.data?.spots[0]

  useEffect(() => {
    if (autoPick.current && topSpot) {
      autoPick.current = false
      onPick(topSpot)
    }
  }, [topSpot, onPick])

  const toggle = () => {
    // Only the first open jumps to #1; re-opening just shows the list.
    if (!open && !requested) autoPick.current = true
    setRequested(true)
    setOpen((value) => !value)
  }

  return (
    <div className="best-spots">
      <button
        type="button"
        className="pill-button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={toggle}
      >
        ★ Tonight's best
      </button>
      {open && (
        <div id={listId} className="best-spots-list" role="region" aria-label="Tonight's best spots">
          {userLocation && (
            <div className="best-scope" role="group" aria-label="Which spots to show">
              <button type="button" aria-pressed={scope === 'near'} onClick={() => setScope('near')}>
                Near me ({NEAR_RADIUS_LABEL})
              </button>
              <button type="button" aria-pressed={scope === 'all'} onClick={() => setScope('all')}>
                All of WNY
              </button>
            </div>
          )}
          {best.isLoading && <p className="spot-muted">Finding the darkest skies…</p>}
          {best.isError && <p className="spot-muted">Could not load tonight's best spots.</p>}
          {best.isSuccess && spots.length === 0 && (
            <p className="spot-muted">
              {nearMe ? `No scored spots within ${NEAR_RADIUS_LABEL} tonight.` : 'No scores for tonight yet.'}
            </p>
          )}
          {spots.length > 0 && (
            <ol>
              {spots.map((spot) => {
                const miles = spotMiles(spot, userLocation)
                return (
                  <li key={spot.cell_id}>
                    <button
                      type="button"
                      onClick={() => {
                        onPick(spot)
                        setOpen(false)
                      }}
                    >
                      <span className="best-swatch" style={{ background: swatch(spot.score) }} aria-hidden="true" />
                      <span className="best-name">{spotTitle(spot)}</span>
                      <span className="best-meta">
                        {Math.round(spot.score)} · {spot.label ?? '—'} · {formatLocalTime(spot.valid_time)}
                        {firstHourMs !== undefined &&
                          Date.parse(spot.valid_time) < firstHourMs &&
                          ' (earlier tonight)'}
                        {miles !== null && ` · ${formatMiles(miles)} away`}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

export default BestSpots

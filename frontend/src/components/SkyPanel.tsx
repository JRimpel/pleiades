import { useSkyEvents } from '../api/hooks'
import type { MoonInfo, SkyEvent } from '../api/types'
import { formatLocalDayTime, formatLocalTime } from '../lib/time'

/**
 * Moon disc with the lit part drawn as a semicircle plus an elliptical terminator.
 * Waxing moons are lit on the right, as seen from the northern hemisphere.
 */
function MoonGraphic({ moon, size = 56 }: { moon: MoonInfo; size?: number }) {
  const r = 24
  const lit = Math.max(0, Math.min(1, moon.illumination))
  const waxing = ((moon.phase_deg % 360) + 360) % 360 < 180
  const terminatorRx = r * Math.abs(1 - 2 * lit)
  const crescent = lit < 0.5
  const outerSweep = waxing ? 1 : 0
  const innerSweep = waxing === crescent ? 0 : 1
  const path = `M 0 ${-r} A ${r} ${r} 0 0 ${outerSweep} 0 ${r} A ${terminatorRx} ${r} 0 0 ${innerSweep} 0 ${-r} Z`
  return (
    <svg viewBox="-28 -28 56 56" width={size} height={size} aria-hidden="true">
      <circle r={r} fill="#2a3346" stroke="#56627c" strokeWidth="1" />
      {lit > 0.01 && (lit > 0.99 ? <circle r={r} fill="#f1ead2" /> : <path d={path} fill="#f1ead2" />)}
    </svg>
  )
}

/** "Sets 4:41 PM · Rises 6:11 AM": rise and set in the order they happen tonight. */
function riseSet(rise: string | null, set: string | null) {
  const parts: [number, string][] = []
  if (rise) parts.push([Date.parse(rise), `Rises ${formatLocalTime(rise)}`])
  if (set) parts.push([Date.parse(set), `Sets ${formatLocalTime(set)}`])
  if (parts.length === 0) return 'Rise/set times unavailable'
  return parts
    .sort((a, b) => a[0] - b[0])
    .map(([, text]) => text)
    .join(' · ')
}

/** Planets that never climb this high tonight are lost in horizon haze and trees. */
const MIN_PLANET_ALT = 5

const HIDDEN_EVENT_TYPES = new Set(['moonrise', 'moonset'])

function eventIcon(event: SkyEvent) {
  switch (event.type) {
    case 'meteor_shower':
      return '☄'
    case 'iss_pass':
      return '🛰'
    case 'planet':
      return '●'
    default:
      return '✦'
  }
}

/** Expanding "Sky tonight" section inside the title card. */
function SkyPanel({ id, at, date }: { id: string; at?: { lat: number; lon: number }; date?: string }) {
  const sky = useSkyEvents(true, at, date)

  if (sky.isLoading) {
    return (
      <div id={id} className="sky-panel" role="status">
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line short" />
      </div>
    )
  }
  if (sky.isError || !sky.data) {
    return (
      <div id={id} className="sky-panel">
        <p className="spot-muted">Sky details are unavailable right now.</p>
      </div>
    )
  }

  const { moon, twilight, planets, events } = sky.data
  const visiblePlanets = planets.filter((p) => p.max_alt_deg === null || p.max_alt_deg >= MIN_PLANET_ALT)
  const otherEvents = events.filter((e) => !HIDDEN_EVENT_TYPES.has(e.type))

  return (
    <div id={id} className="sky-panel">
      <p className="spot-muted sky-caption">
        {date ? `Local night starting ${date}` : 'Tonight'} · {at && !sky.isPlaceholderData ? 'For the selected location' : 'For Western New York'}
      </p>
      <section className="sky-moon" aria-label="Moon">
        <MoonGraphic moon={moon} />
        <div>
          <p className="sky-moon-name">
            {moon.phase_name} · {Math.round(moon.illumination * 100)}% lit
          </p>
          <p className="spot-muted">{riseSet(moon.rise, moon.set)}</p>
        </div>
      </section>

      <section aria-labelledby={`${id}-dark`}>
        <h3 id={`${id}-dark`}>Darkness</h3>
        <dl className="sky-times">
          <div>
            <dt>Sunset</dt>
            <dd>{formatLocalTime(twilight.sunset)}</dd>
          </div>
          <div>
            <dt>Truly dark</dt>
            <dd>{formatLocalTime(twilight.astronomical_dusk)}</dd>
          </div>
          <div>
            <dt>Dark ends</dt>
            <dd>{formatLocalTime(twilight.astronomical_dawn)}</dd>
          </div>
          <div>
            <dt>Sunrise</dt>
            <dd>{formatLocalTime(twilight.sunrise)}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby={`${id}-planets`}>
        <h3 id={`${id}-planets`}>Planets</h3>
        {visiblePlanets.length === 0 ? (
          <p className="spot-muted">No bright planets listed for this night.</p>
        ) : (
          <ul className="sky-list">
            {visiblePlanets.map((planet) => (
              <li key={planet.name}>
                <span className="sky-list-name">{planet.name}</span>
                <span className="spot-muted">
                  {riseSet(planet.rise, planet.set)}
                  {planet.max_alt_deg !== null && ` · up to ${Math.round(planet.max_alt_deg)}°`}
                  {planet.magnitude !== null && ` · mag ${planet.magnitude.toFixed(1)}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {otherEvents.length > 0 && (
        <section aria-labelledby={`${id}-events`}>
          <h3 id={`${id}-events`}>Events</h3>
          <ul className="sky-list">
            {otherEvents.map((event) => (
              <li key={`${event.type}-${event.name}-${event.time}`}>
                <span className="sky-list-name">
                  <span aria-hidden="true">{eventIcon(event)} </span>
                  {event.name}
                </span>
                <span className="spot-muted">{formatLocalDayTime(event.time)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

export default SkyPanel

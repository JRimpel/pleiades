import { useEffect, useId, useMemo, useRef } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSpot, useSpotDrift, useSpotHistory } from '../api/hooks'
import type { Conditions, AstroSnapshot, SpotDetail, SpotDrift, SpotHistory } from '../api/types'
import { factorLabel, scoreToRgb } from '../lib/scoreColors'
import { formatCoords, formatMiles, haversineMiles, spotTitle } from '../lib/placeName'
import { formatLocalDayTime, formatLocalHour } from '../lib/time'
import type { UserLocation } from '../lib/useUserLocation'

interface SpotPanelProps {
  cellId: number
  /** ISO UTC hour shown on the map, or undefined for the backend's current hour. */
  time: string | undefined
  onClose: () => void
  /** When known, the panel shows the distance and uses it as the directions origin. */
  userLocation?: UserLocation | null
}

const AXIS_COLOR = '#8d98ae'
const GRID_COLOR = 'rgba(141, 152, 174, 0.18)'

function rgbCss(score: number) {
  const [r, g, b] = scoreToRgb(score)
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}

function ScoreGauge({ score, label }: { score: number | null; label: string | null }) {
  const radius = 44
  const circumference = 2 * Math.PI * radius
  const fraction = score === null ? 0 : Math.max(0, Math.min(1, score / 100))
  return (
    <div className="spot-gauge">
      <svg viewBox="0 0 110 110" width="110" height="110" aria-hidden="true">
        <circle cx="55" cy="55" r={radius} fill="none" stroke="rgba(141,152,174,0.25)" strokeWidth="10" />
        {score !== null && (
          <circle
            cx="55"
            cy="55"
            r={radius}
            fill="none"
            stroke={rgbCss(score)}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${fraction * circumference} ${circumference}`}
            transform="rotate(-90 55 55)"
          />
        )}
      </svg>
      <div className="spot-gauge-text">
        <span className="spot-gauge-number">{score === null ? '—' : Math.round(score)}</span>
        <span className="spot-gauge-label">{score === null ? 'No score' : (label ?? 'Unlabeled')}</span>
      </div>
    </div>
  )
}

function FactorBars({ factors }: { factors: Record<string, number> }) {
  const entries = Object.entries(factors)
    .filter(([, value]) => Math.abs(value) >= 0.5)
    .sort((a, b) => a[1] - b[1])
  if (entries.length === 0) return <p className="spot-muted">Nothing is holding this score back.</p>
  const scale = Math.max(10, ...entries.map(([, v]) => Math.abs(v)))
  return (
    <ul className="factor-bars">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span className="factor-name">{factorLabel(key)}</span>
          <span className="factor-track" aria-hidden="true">
            <span
              className={value < 0 ? 'factor-fill factor-loss' : 'factor-fill factor-gain'}
              style={{ width: `${(Math.abs(value) / scale) * 100}%` }}
            />
          </span>
          <span className="factor-value">
            {value > 0 ? '+' : '−'}
            {Math.abs(Math.round(value))}
            <span className="visually-hidden"> points</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function pct(value: number | null) {
  return value === null ? '—' : `${Math.round(value)}%`
}

function ConditionsGrid({ conditions, astro }: { conditions: Conditions | null; astro: AstroSnapshot | null }) {
  const rows: [string, string][] = []
  if (conditions) {
    rows.push(
      ['Low clouds', pct(conditions.cloud_low)],
      ['Mid clouds', pct(conditions.cloud_mid)],
      ['High clouds', pct(conditions.cloud_high)],
      ['Humidity', pct(conditions.rh)],
      [
        'Visibility',
        conditions.visibility_m === null ? '—' : `${(conditions.visibility_m / 1000).toFixed(0)} km`,
      ],
      ['Wind', conditions.wind_kmh === null ? '—' : `${Math.round(conditions.wind_kmh)} km/h`],
      [
        'Temperature',
        conditions.temp_c === null
          ? '—'
          : `${Math.round((conditions.temp_c * 9) / 5 + 32)}°F (${Math.round(conditions.temp_c)}°C)`,
      ],
      ['Rain chance', pct(conditions.precip_prob)],
    )
  }
  if (astro) {
    rows.push(
      ['Moon altitude', astro.moon_alt === null ? '—' : `${Math.round(astro.moon_alt)}°`],
      ['Moon lit', astro.moon_illum === null ? '—' : `${Math.round(astro.moon_illum * 100)}%`],
    )
  }
  if (rows.length === 0) return <p className="spot-muted">No forecast for this hour.</p>
  return (
    <dl className="spot-conditions">
      {rows.map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

const tooltipStyle = {
  contentStyle: { background: '#162136', border: '1px solid #56627c', borderRadius: 6, fontSize: 12 },
  labelStyle: { color: '#bac4d7' },
}

function HistoryChart({ history, selectedMs }: { history: SpotHistory; selectedMs?: number }) {
  const data = useMemo(
    () => history.hourly.map((p) => ({ t: Date.parse(p.time), score: Math.round(p.score) })),
    [history],
  )
  if (data.length < 2) return <p className="spot-muted">Not enough history yet.</p>
  return (
    <ResponsiveContainer width="100%" height={110}>
      <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -24 }}>
        <defs>
          <linearGradient id="history-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f5d000" stopOpacity={0.45} />
            <stop offset="100%" stopColor="#f5d000" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_COLOR} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          scale="time"
          tickFormatter={(ms: number) =>
            new Date(ms).toLocaleDateString('en-US', { timeZone: 'America/New_York', weekday: 'short' })
          }
          stroke={AXIS_COLOR}
          fontSize={11}
          minTickGap={24}
        />
        <YAxis domain={[0, 100]} ticks={[0, 50, 100]} stroke={AXIS_COLOR} fontSize={11} />
        <Tooltip
          {...tooltipStyle}
          labelFormatter={(ms: number) => formatLocalHour(ms)}
          formatter={(value: number) => [value, 'Score']}
        />
        {selectedMs !== undefined && <ReferenceLine x={selectedMs} stroke="#b3cbff" strokeDasharray="3 3" />}
        <Area dataKey="score" stroke="#f5d000" fill="url(#history-fill)" strokeWidth={1.5} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

const MAX_REVISIONS = 6

function DriftChart({ drift }: { drift: SpotDrift }) {
  const revisions = drift.revisions.slice(-MAX_REVISIONS)
  const data = useMemo(() => {
    const rows = new Map<number, Record<string, number>>()
    revisions.forEach((rev, i) => {
      for (const p of rev.points) {
        const t = Date.parse(p.valid_time)
        const row = rows.get(t) ?? { t }
        row[`r${i}`] = Math.round(p.score)
        rows.set(t, row)
      }
    })
    return [...rows.values()].sort((a, b) => a.t - b.t)
  }, [revisions])

  if (revisions.length === 0) return <p className="spot-muted">No forecasts for tonight yet.</p>
  return (
    <>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -24 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            scale="time"
            tickFormatter={(ms: number) =>
              new Date(ms).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: 'numeric' })
            }
            stroke={AXIS_COLOR}
            fontSize={11}
            minTickGap={20}
          />
          <YAxis domain={[0, 100]} ticks={[0, 50, 100]} stroke={AXIS_COLOR} fontSize={11} />
          <Tooltip {...tooltipStyle} labelFormatter={(ms: number) => formatLocalHour(ms)} />
          {revisions.map((rev, i) => {
            const latest = i === revisions.length - 1
            return (
              <Line
                key={rev.computed_at}
                dataKey={`r${i}`}
                name={`Forecast from ${formatLocalDayTime(rev.computed_at)}`}
                stroke={latest ? '#f5d000' : '#8d98ae'}
                strokeOpacity={latest ? 1 : 0.35 + (0.5 * i) / Math.max(1, revisions.length - 1)}
                strokeWidth={latest ? 2 : 1}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            )
          })}
        </LineChart>
      </ResponsiveContainer>
      <p className="spot-muted">
        {revisions.length === 1
          ? 'Only one forecast revision so far.'
          : `${revisions.length} forecast revisions. The yellow line is the latest; grey lines are earlier forecasts.`}
      </p>
    </>
  )
}

function SpotBody({
  spot,
  selectedMs,
  userLocation,
}: {
  spot: SpotDetail
  selectedMs?: number
  userLocation?: UserLocation | null
}) {
  const history = useSpotHistory(spot.cell_id)
  const drift = useSpotDrift(spot.cell_id)
  const directionsParams = new URLSearchParams({ api: '1', destination: `${spot.lat},${spot.lon}` })
  if (userLocation) directionsParams.set('origin', `${userLocation.lat},${userLocation.lon}`)
  const directions = `https://www.google.com/maps/dir/?${directionsParams}`
  const milesAway = userLocation ? haversineMiles(userLocation.lat, userLocation.lon, spot.lat, spot.lon) : null

  return (
    <>
      <div className="spot-summary">
        <ScoreGauge score={spot.score} label={spot.label} />
        <div className="spot-summary-text">
          {spot.nelm !== null && spot.score !== null && (
            <p>
              You'll see stars down to magnitude <strong>{spot.nelm.toFixed(1)}</strong>.
            </p>
          )}
          <p className="spot-muted">
            Bortle {spot.bortle ?? '?'}
            {spot.sky_brightness_mpsas !== null && ` · ${spot.sky_brightness_mpsas.toFixed(1)} mag/arcsec²`}
            {spot.elevation_m !== null && ` · ${Math.round(spot.elevation_m * 3.281).toLocaleString()} ft`}
          </p>
          {milesAway !== null && (
            <p className="spot-muted">
              {milesAway < 0.5 ? "You're here" : `About ${formatMiles(milesAway)} from you (straight line)`}
            </p>
          )}
        </div>
      </div>

      {spot.explanation && (
        <section className="spot-section" aria-label="Why this score">
          <p className="spot-explanation">{spot.explanation.summary}</p>
          {spot.explanation.tips.length > 0 && (
            <ul className="spot-tips">
              {spot.explanation.tips.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {spot.factors && (
        <section className="spot-section">
          <h3>What's affecting the score</h3>
          <FactorBars factors={spot.factors} />
        </section>
      )}

      <section className="spot-section">
        <h3>Conditions</h3>
        <ConditionsGrid conditions={spot.conditions} astro={spot.astro} />
      </section>

      <section className="spot-section">
        <h3>Score history</h3>
        {history.data ? (
          <HistoryChart history={history.data} selectedMs={selectedMs} />
        ) : history.isError ? (
          <p className="spot-muted">History unavailable.</p>
        ) : (
          <div className="skeleton skeleton-chart" />
        )}
      </section>

      <section className="spot-section">
        <h3>How tonight's forecast changed</h3>
        {drift.data ? (
          <DriftChart drift={drift.data} />
        ) : drift.isError ? (
          <p className="spot-muted">Forecast revisions unavailable.</p>
        ) : (
          <div className="skeleton skeleton-chart" />
        )}
      </section>

      <a className="spot-directions" href={directions} target="_blank" rel="noopener noreferrer">
        Get directions ↗
      </a>
    </>
  )
}

function SpotPanel({ cellId, time, onClose, userLocation }: SpotPanelProps) {
  const headingId = useId()
  const headingRef = useRef<HTMLHeadingElement>(null)
  const spot = useSpot(cellId, time)
  const data = spot.data?.cell_id === cellId ? spot.data : undefined
  const selectedMs = time ? Date.parse(time) : data ? Date.parse(data.valid_time) : undefined

  // Move focus to the panel when it opens or switches spot, for keyboard and screen-reader users.
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true })
  }, [cellId])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const title = data ? spotTitle(data) : 'Loading spot…'

  return (
    <aside className="spot-panel" aria-labelledby={headingId}>
      <header className="spot-panel-header">
        <div>
          <h2 id={headingId} ref={headingRef} tabIndex={-1}>
            {title}
          </h2>
          {data && (
            <p className="spot-muted">
              {data.name === null && `${formatCoords(data.lat, data.lon)} · `}
              {formatLocalHour(Date.parse(data.valid_time))} (Eastern)
            </p>
          )}
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close spot details">
          ×
        </button>
      </header>
      <div className="spot-panel-body">
        {data ? (
          <>
            {spot.isFetching && (
              <p className="spot-muted" role="status">
                Updating…
              </p>
            )}
            <SpotBody spot={data} selectedMs={selectedMs} userLocation={userLocation} />
          </>
        ) : spot.isError ? (
          <p className="spot-muted" role="alert">
            Could not load this spot. Try again in a moment.
          </p>
        ) : (
          <div role="status" aria-label="Loading spot details">
            <div className="skeleton skeleton-gauge" />
            <div className="skeleton skeleton-line" />
            <div className="skeleton skeleton-line short" />
            <div className="skeleton skeleton-chart" />
          </div>
        )}
      </div>
    </aside>
  )
}

export default SpotPanel

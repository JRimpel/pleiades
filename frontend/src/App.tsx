import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { useScoreRange, useScores, useSkyEvents } from './api/hooks'
import type { BestSpot } from './api/types'
import BestSpots from './components/BestSpots'
import ScoreLegend from './components/ScoreLegend'
import SkyPanel from './components/SkyPanel'
import SpotPanel from './components/SpotPanel'
import StargazingMap from './components/StargazingMap'
<<<<<<< HEAD
import { ExploreIn3D } from './explore'
=======
import type { MapFocus } from './components/StargazingMap'
import TimeSlider from './components/TimeSlider'
import { nearestCell } from './lib/nearestCell'
import { isWithinBounds } from './lib/region'
import { scoreToRgb } from './lib/scoreColors'
import { HOUR_MS, toIsoHour } from './lib/time'
import { useUserLocation } from './lib/useUserLocation'
>>>>>>> 316d78010979697cd916b8318a9824a734ab9056
import './App.css'

/** How long the "outside Western New York" notice stays up. */
const OUTSIDE_NOTICE_MS = 8000

function rgbCss(score: number) {
  const [r, g, b] = scoreToRgb(score)
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}

function App() {
  const skyPanelId = useId()
  const { location } = useUserLocation()
  // Location-aware features only use the position when it's inside the map's region.
  const inRegion = !!location && isWithinBounds(location.lat, location.lon)
  const regionLocation = inRegion ? location : null
  const [outsideNoticeDone, setOutsideNoticeDone] = useState(false)
  const showOutsideNotice = !!location && !inRegion && !outsideNoticeDone
  useEffect(() => {
    if (!showOutsideNotice) return
    const timer = window.setTimeout(() => setOutsideNoticeDone(true), OUTSIDE_NOTICE_MS)
    return () => window.clearTimeout(timer)
  }, [showOutsideNotice])

  const range = useScoreRange()
  const sky = useSkyEvents(true, regionLocation ?? undefined)
  // Hour chosen on the slider (epoch ms). Undefined until the range loads → backend default (current hour).
  const [selectedMs, setSelectedMs] = useState<number>()
  // Wait for the slider to settle briefly before requesting a new hour.
  const [requestedMs, setRequestedMs] = useState<number>()
  const [selectedCellId, setSelectedCellId] = useState<number | null>(null)
  const [focus, setFocus] = useState<MapFocus>()
  const [skyOpen, setSkyOpen] = useState(false)
  // A picked spot's best hour, shown in the panel until the slider moves (it may be before the slider's range).
  const [panelTime, setPanelTime] = useState<string>()

  const minMs = range.data?.min_time ? Date.parse(range.data.min_time) : undefined
  const maxMs = range.data?.max_time ? Date.parse(range.data.max_time) : undefined
  const nowHourMs = range.data ? Math.floor(Date.parse(range.data.now) / HOUR_MS) * HOUR_MS : undefined
  const defaultMs =
    minMs !== undefined && maxMs !== undefined && nowHourMs !== undefined
      ? Math.min(Math.max(nowHourMs, minMs), maxMs)
      : undefined
  const sliderMs = selectedMs ?? defaultMs

  useEffect(() => {
    if (selectedMs === undefined) return
    const timer = window.setTimeout(() => setRequestedMs(selectedMs), 150)
    return () => window.clearTimeout(timer)
  }, [selectedMs])

  const requestedTime = requestedMs === undefined ? undefined : toIsoHour(requestedMs)
  const scores = useScores(requestedTime)
  // The score at the user's spot for the hour on the slider.
  const yourCell = useMemo(
    () => (regionLocation ? nearestCell(scores.data, regionLocation.lat, regionLocation.lon) : null),
    [scores.data, regionLocation],
  )

  const closeSpot = useCallback(() => setSelectedCellId(null), [])
  const selectCell = useCallback((cellId: number) => {
    setPanelTime(undefined)
    setSelectedCellId(cellId)
  }, [])
  const changeHour = useCallback((ms: number) => {
    setPanelTime(undefined)
    setSelectedMs(ms)
  }, [])

  const pickBest = useCallback(
    (spot: BestSpot) => {
      let ms = Math.floor(Date.parse(spot.valid_time) / HOUR_MS) * HOUR_MS
      setPanelTime(toIsoHour(ms))
      if (minMs !== undefined && maxMs !== undefined) ms = Math.min(Math.max(ms, minMs), maxMs)
      setSelectedMs(ms)
      setRequestedMs(ms)
      setSelectedCellId(spot.cell_id)
      setFocus({ lat: spot.lat, lon: spot.lon, key: Date.now() })
    },
    [minMs, maxMs],
  )

  // Mark when real darkness starts and ends on the slider.
  const ticks: { ms: number; label: string }[] = []
  if (sky.data?.twilight.astronomical_dusk) {
    ticks.push({ ms: Date.parse(sky.data.twilight.astronomical_dusk), label: 'Dark' })
  }
  if (sky.data?.twilight.astronomical_dawn) {
    ticks.push({ ms: Date.parse(sky.data.twilight.astronomical_dawn), label: 'Dawn' })
  }

  let status = ''
  if (scores.isError || range.isError) {
    status = 'Scores unavailable. Is the backend running? (Vite proxies /api to localhost:5001.)'
  } else if (scores.isLoading) {
    status = 'Loading scores…'
  } else if (scores.isFetching) {
    status = 'Updating scores…'
  } else if (range.isSuccess && minMs === undefined) {
    status = 'No forecast scores are available yet.'
  }

  return (
    <main className={selectedCellId === null ? 'app' : 'app has-spot-panel'}>
      <header className="app-header">
        <div className="app-header-row">
          <div>
            <h1>Pleiades</h1>
            <p>Find your next constellation lookout in Western New York</p>
          </div>
          <div className="app-header-buttons">
            <button
              type="button"
              className="pill-button"
              aria-expanded={skyOpen}
              aria-controls={skyPanelId}
              onClick={() => setSkyOpen((open) => !open)}
            >
              {skyOpen ? 'Hide sky' : 'Sky tonight'}
            </button>
            {yourCell && (
              <button
                type="button"
                className="pill-button your-sky-button"
                aria-label={
                  yourCell.score === null
                    ? 'Your sky: no score for this hour. Open details.'
                    : `Your sky at the selected hour: ${Math.round(yourCell.score)}, ${yourCell.label}. Open details.`
                }
                title="Score where you are, for the hour on the slider"
                onClick={() => selectCell(yourCell.cellId)}
              >
                <span
                  className="your-sky-swatch"
                  aria-hidden="true"
                  style={{ background: yourCell.score === null ? '#6b7280' : rgbCss(yourCell.score) }}
                />
                Your sky · {yourCell.score === null ? '—' : `${Math.round(yourCell.score)} ${yourCell.label ?? ''}`}
              </button>
            )}
          </div>
        </div>
        {skyOpen && <SkyPanel id={skyPanelId} at={regionLocation ?? undefined} />}
      </header>
<<<<<<< HEAD
      <StargazingMap />
      <ExploreIn3D />
=======
      <StargazingMap
        scores={scores.data}
        onSelectCell={selectCell}
        selectedCellId={selectedCellId}
        focus={focus}
        userLocation={location}
      >
        {showOutsideNotice && (
          <p className="map-notice location-notice" role="status">
            You're outside Western New York, so your location isn't shown on the map.
          </p>
        )}
        {minMs !== undefined && maxMs !== undefined && sliderMs !== undefined ? (
          <TimeSlider
            minMs={minMs}
            maxMs={maxMs}
            valueMs={sliderMs}
            onChange={changeHour}
            status={status}
            actions={<BestSpots onPick={pickBest} firstHourMs={minMs} userLocation={regionLocation} />}
            ticks={ticks}
          />
        ) : (
          status && (
            <p className="map-overlay-card time-slider-status" role="status">
              {status}
            </p>
          )
        )}
        <ScoreLegend />
      </StargazingMap>
      {selectedCellId !== null && (
        <SpotPanel
          cellId={selectedCellId}
          time={panelTime ?? requestedTime ?? scores.data?.time}
          onClose={closeSpot}
          userLocation={location}
        />
      )}
>>>>>>> 316d78010979697cd916b8318a9824a734ab9056
    </main>
  )
}

export default App

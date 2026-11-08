import { useEffect, useState } from 'react'
import { useScoreRange, useScores } from './api/hooks'
import ScoreLegend from './components/ScoreLegend'
import StargazingMap from './components/StargazingMap'
import TimeSlider from './components/TimeSlider'
import { HOUR_MS, toIsoHour } from './lib/time'
import './App.css'

function App() {
  const range = useScoreRange()
  // Hour chosen on the slider (epoch ms). Undefined until the range loads → backend default (current hour).
  const [selectedMs, setSelectedMs] = useState<number>()
  // Wait for the slider to settle briefly before requesting a new hour.
  const [requestedMs, setRequestedMs] = useState<number>()

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

  const scores = useScores(requestedMs === undefined ? undefined : toIsoHour(requestedMs))

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
    <main className="app">
      <header className="app-header">
        <h1>Pleiades</h1>
        <p>Find your next constellation lookout in Western New York</p>
      </header>
      <StargazingMap scores={scores.data}>
        {minMs !== undefined && maxMs !== undefined && sliderMs !== undefined ? (
          <TimeSlider minMs={minMs} maxMs={maxMs} valueMs={sliderMs} onChange={setSelectedMs} status={status} />
        ) : (
          status && (
            <p className="map-overlay-card time-slider-status" role="status">
              {status}
            </p>
          )
        )}
        <ScoreLegend />
      </StargazingMap>
    </main>
  )
}

export default App

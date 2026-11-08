import { useState } from 'react'
import { isObservation, localTime } from './astronomy'
import type { ObservationContext } from './astronomy'

export default function ObservationControls({ value, onChange }: { value: ObservationContext; onChange: (value: ObservationContext) => void }) {
  const [lat, setLat] = useState(String(value.lat))
  const [lon, setLon] = useState(String(value.lon))
  const [time, setTime] = useState(new Date(value.time).toISOString().slice(0, 16))
  const [error, setError] = useState('')
  return <form className="explore-context" onSubmit={event => {
    event.preventDefault()
    const next = { lat: Number(lat), lon: Number(lon), time: time + ':00Z' }
    if (!lat.trim() || !lon.trim() || !isObservation(next)) { setError('Choose valid WNY coordinates and a date/time.'); return }
    setError(''); onChange({ ...next, time: new Date(next.time).toISOString() })
  }}>
    <div className="explore-context-heading"><span className="eyebrow">Your observing context</span><p>Independent of the map for now.</p></div>
    <div className="explore-context-fields">
      <label>Latitude<input type="number" step="0.0001" min="42" max="43.4" required value={lat} onChange={e => setLat(e.target.value)} /></label>
      <label>Longitude<input type="number" step="0.0001" min="-79.8" max="-77" required value={lon} onChange={e => setLon(e.target.value)} /></label>
      <label className="explore-time-input">Date &amp; time (UTC)<input type="datetime-local" step="3600" required value={time} onChange={e => setTime(e.target.value)} /></label>
      <button type="submit" className="explore-button">Update sky context <span aria-hidden="true">↗</span></button>
    </div>
    <p className="explore-context-caption">Selected: {localTime(value.time)} · {value.lat.toFixed(4)}, {value.lon.toFixed(4)}</p>
    {error && <p className="explore-error-text" role="alert">{error}</p>}
  </form>
}

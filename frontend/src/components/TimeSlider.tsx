import { useId } from 'react'
import { HOUR_MS, formatLocalHour } from '../lib/time'

interface TimeSliderProps {
  /** First and last available forecast hours, as epoch milliseconds. */
  minMs: number
  maxMs: number
  valueMs: number
  onChange: (ms: number) => void
  status?: string
}

function TimeSlider({ minMs, maxMs, valueMs, onChange, status }: TimeSliderProps) {
  const id = useId()
  const hours = Math.max(0, Math.round((maxMs - minMs) / HOUR_MS))
  const index = Math.round((valueMs - minMs) / HOUR_MS)
  const label = formatLocalHour(valueMs)

  return (
    <div className="map-overlay-card time-slider">
      <div className="time-slider-header">
        <label htmlFor={id}>
          Scores for <strong>{label}</strong>
          <span className="time-zone"> (Eastern)</span>
        </label>
        <span className="time-slider-status" role="status">
          {status}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={hours}
        step={1}
        value={index}
        aria-valuetext={label}
        disabled={hours === 0}
        onChange={(event) => onChange(minMs + Number(event.target.value) * HOUR_MS)}
      />
      <div className="time-slider-ends" aria-hidden="true">
        <span>{formatLocalHour(minMs)}</span>
        <span>{formatLocalHour(maxMs)}</span>
      </div>
    </div>
  )
}

export default TimeSlider

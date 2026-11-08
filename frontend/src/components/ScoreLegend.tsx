import { NO_DATA_COLOR, scoreGradientCss } from '../lib/scoreColors'

const TICKS = [0, 25, 50, 75, 100]
const LABELS = ['Poor', 'Fair', 'Good', 'Excellent']

function ScoreLegend() {
  return (
    <figure className="score-legend" aria-label="Stargazing score color key">
      <figcaption>Stargazing score</figcaption>
      <div className="score-legend-bar" style={{ background: scoreGradientCss }} />
      <div className="score-legend-ticks" aria-hidden="true">
        {TICKS.map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </div>
      <div className="score-legend-labels">
        {LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      <div className="score-legend-nodata">
        <span className="score-legend-swatch" style={{ background: NO_DATA_COLOR }} />
        No data for this hour
      </div>
    </figure>
  )
}

export default ScoreLegend

import type { ExpressionSpecification } from 'maplibre-gl'

/** Gradient stops: red near 0, yellow near 50, green near 100. */
export const SCORE_STOPS = [
  { score: 0, color: '#d7301f' },
  { score: 50, color: '#f5d000' },
  { score: 100, color: '#1a9850' },
] as const

/** Cells with no score for the selected hour (never shown as a zero score). */
export const NO_DATA_COLOR = '#6b7280'

export const scoreColorExpression: ExpressionSpecification = [
  'case',
  ['==', ['get', 'score'], null],
  NO_DATA_COLOR,
  [
    'interpolate',
    ['linear'],
    ['get', 'score'],
    ...SCORE_STOPS.flatMap((stop) => [stop.score, stop.color]),
  ],
] as ExpressionSpecification

/** The same gradient as CSS, for the legend. */
export const scoreGradientCss = `linear-gradient(to right, ${SCORE_STOPS.map(
  (stop) => `${stop.color} ${stop.score}%`,
).join(', ')})`

/** Readable names for the backend's factor keys (see backend-documentation.md §3.1). */
export const FACTOR_LABELS: Record<string, string> = {
  clouds: 'Clouds',
  moon: 'Moonlight',
  light_pollution: 'Light pollution',
  haze: 'Haze',
  twilight: 'Twilight',
  elevation: 'Elevation',
  calibration: 'Calibration',
}

export function factorLabel(key: string | null): string {
  if (!key) return 'None'
  return FACTOR_LABELS[key] ?? key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export type Rgb = [number, number, number]

function hexToRgb(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

const STOP_RGB = SCORE_STOPS.map((stop) => ({ score: stop.score, rgb: hexToRgb(stop.color) }))

export const NO_DATA_RGB: Rgb = hexToRgb(NO_DATA_COLOR)

/** The same linear red → yellow → green blend as `scoreColorExpression`, for canvas drawing. */
export function scoreToRgb(score: number): Rgb {
  const first = STOP_RGB[0]
  const last = STOP_RGB[STOP_RGB.length - 1]
  if (score <= first.score) return [...first.rgb]
  if (score >= last.score) return [...last.rgb]
  for (let i = 1; i < STOP_RGB.length; i++) {
    const hi = STOP_RGB[i]
    if (score <= hi.score) {
      const lo = STOP_RGB[i - 1]
      const t = (score - lo.score) / (hi.score - lo.score)
      return [0, 1, 2].map((c) => lo.rgb[c] + (hi.rgb[c] - lo.rgb[c]) * t) as Rgb
    }
  }
  return [...last.rgb]
}

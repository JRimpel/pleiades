import type { ScoresResponse } from '../api/types'
import { NO_DATA_RGB, scoreToRgb } from './scoreColors'

/** Image corners in MapLibre order: top-left, top-right, bottom-right, bottom-left ([lng, lat]). */
export type ImageCorners = [[number, number], [number, number], [number, number], [number, number]]

export interface SurfacePixels {
  width: number
  height: number
  /** RGBA, row-major, top row first. */
  data: Uint8ClampedArray
  coordinates: ImageCorners
}

/** Pixels drawn per grid step. MapLibre smooths further when zoomed in. */
const PIXELS_PER_CELL = 20
/** Gaussian blur radius in grid steps: smooth, round blends while a cell still dominates its own centre. */
const SIGMA_CELLS = 0.55
/** Cells farther than this (in grid steps) contribute effectively nothing. */
const KERNEL_RADIUS = 2
/** Image margin beyond the outer centres, in grid steps; enough for the fade to reach zero. */
const MARGIN_CELLS = 1.5

/** A fully transparent 1×1 PNG, used before scores arrive. */
export const TRANSPARENT_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='

const mercatorY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))
const latFromMercatorY = (y: number) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90
const smoothstep = (t: number) => t * t * (3 - 2 * t)
const gaussian = (d: number) => Math.exp((-d * d) / (2 * SIGMA_CELLS * SIGMA_CELLS))

interface AxisWeights {
  /** Grid indices (within bounds) and their weights, per pixel. */
  index: Int32Array[]
  weight: Float64Array[]
  /** Weight total a pixel would get if every lattice position existed (used to measure coverage). */
  full: Float64Array
}

/** Gaussian weights from each pixel position `g` (in grid steps) to the nearby lattice indices. */
function axisWeights(positions: number[], count: number): AxisWeights {
  const index: Int32Array[] = []
  const weight: Float64Array[] = []
  const full = new Float64Array(positions.length)
  positions.forEach((g, p) => {
    const ids: number[] = []
    const ws: number[] = []
    for (let k = Math.ceil(g - KERNEL_RADIUS); k <= Math.floor(g + KERNEL_RADIUS); k++) {
      const w = gaussian(g - k)
      full[p] += w
      if (k >= 0 && k < count) {
        ids.push(k)
        ws.push(w)
      }
    }
    index.push(Int32Array.from(ids))
    weight.push(Float64Array.from(ws))
  })
  return { index, weight, full }
}

/**
 * Turn the grid-cell polygons into a smooth RGBA surface.
 *
 * Each pixel is a Gaussian-weighted average of nearby cell scores (normalized convolution).
 * Cells that are absent — off the grid or over the lakes — get no weight, so the color fades to
 * transparent within about a cell instead of ending in hard squares. Null scores blend toward
 * gray and are never treated as zero. The Gaussian is separable, so it runs as two 1-D passes.
 */
export function sampleScoreSurface(scores: ScoresResponse, stepDeg = 0.1): SurfacePixels | null {
  const centres: { lon: number; lat: number; score: number | null }[] = []
  for (const feature of scores.features) {
    if (feature.geometry.type !== 'Polygon') continue
    const ring = feature.geometry.coordinates[0]
    if (!ring || ring.length < 3) continue
    centres.push({
      lon: (ring[0][0] + ring[2][0]) / 2,
      lat: (ring[0][1] + ring[2][1]) / 2,
      score: feature.properties.score,
    })
  }
  if (centres.length === 0) return null

  const minLon = Math.min(...centres.map((c) => c.lon))
  const minLat = Math.min(...centres.map((c) => c.lat))
  const cols = Math.round((Math.max(...centres.map((c) => c.lon)) - minLon) / stepDeg) + 1
  const rows = Math.round((Math.max(...centres.map((c) => c.lat)) - minLat) / stepDeg) + 1

  // present[k] = 1 where a cell exists; scored[k] = 1 where it also has a score.
  const present = new Float64Array(cols * rows)
  const scored = new Float64Array(cols * rows)
  const value = new Float64Array(cols * rows)
  for (const c of centres) {
    const k = Math.round((c.lat - minLat) / stepDeg) * cols + Math.round((c.lon - minLon) / stepDeg)
    present[k] = 1
    if (c.score !== null && Number.isFinite(c.score)) {
      scored[k] = 1
      value[k] = c.score
    }
  }

  const west = minLon - MARGIN_CELLS * stepDeg
  const east = minLon + (cols - 1 + MARGIN_CELLS) * stepDeg
  const south = minLat - MARGIN_CELLS * stepDeg
  const north = minLat + (rows - 1 + MARGIN_CELLS) * stepDeg
  const width = Math.round((cols - 1 + 2 * MARGIN_CELLS) * PIXELS_PER_CELL)
  const height = Math.round((rows - 1 + 2 * MARGIN_CELLS) * PIXELS_PER_CELL)

  // Pixel centres in grid coordinates. Rows are evenly spaced in Web Mercator, matching how
  // MapLibre stretches an image source.
  const gxs = Array.from({ length: width }, (_, px) => (west + ((px + 0.5) / width) * (east - west) - minLon) / stepDeg)
  const yNorth = mercatorY(north)
  const ySouth = mercatorY(south)
  const gys = Array.from({ length: height }, (_, py) => {
    const lat = latFromMercatorY(yNorth - ((py + 0.5) / height) * (yNorth - ySouth))
    return (lat - minLat) / stepDeg
  })
  const xw = axisWeights(gxs, cols)
  const yw = axisWeights(gys, rows)

  // Pass 1: blur each grid row horizontally to pixel columns.
  const rowPresent = new Float64Array(rows * width)
  const rowScored = new Float64Array(rows * width)
  const rowValue = new Float64Array(rows * width)
  for (let j = 0; j < rows; j++) {
    for (let px = 0; px < width; px++) {
      const ids = xw.index[px]
      const ws = xw.weight[px]
      let p = 0
      let s = 0
      let v = 0
      for (let n = 0; n < ids.length; n++) {
        const k = j * cols + ids[n]
        p += ws[n] * present[k]
        s += ws[n] * scored[k]
        v += ws[n] * scored[k] * value[k]
      }
      rowPresent[j * width + px] = p
      rowScored[j * width + px] = s
      rowValue[j * width + px] = v
    }
  }

  // Pass 2: blur vertically to pixel rows, then color each pixel.
  const data = new Uint8ClampedArray(width * height * 4)
  for (let py = 0; py < height; py++) {
    const ids = yw.index[py]
    const ws = yw.weight[py]
    for (let px = 0; px < width; px++) {
      let p = 0
      let s = 0
      let v = 0
      for (let n = 0; n < ids.length; n++) {
        const k = ids[n] * width + px
        p += ws[n] * rowPresent[k]
        s += ws[n] * rowScored[k]
        v += ws[n] * rowValue[k]
      }
      // Share of the kernel that landed on real cells: ~1 inside the grid, falling to 0 outside.
      const coverage = p / (xw.full[px] * yw.full[py])
      const alpha = smoothstep(Math.min(1, Math.max(0, (coverage - 0.1) / 0.5)))
      if (alpha <= 0) continue

      const rgb = s > 1e-9 ? scoreToRgb(v / s) : NO_DATA_RGB
      const grayShare = p > 0 ? 1 - s / p : 1
      const o = (py * width + px) * 4
      for (let c = 0; c < 3; c++) data[o + c] = rgb[c] + (NO_DATA_RGB[c] - rgb[c]) * grayShare
      data[o + 3] = Math.round(alpha * 255)
    }
  }

  return {
    width,
    height,
    data,
    coordinates: [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ],
  }
}

/** Render the surface to a PNG data URL for a MapLibre `image` source. */
export function buildScoreSurface(scores: ScoresResponse, stepDeg = 0.1) {
  const pixels = sampleScoreSurface(scores, stepDeg)
  if (!pixels) return null
  const canvas = document.createElement('canvas')
  canvas.width = pixels.width
  canvas.height = pixels.height
  const context = canvas.getContext('2d')
  if (!context) return null
  const image = context.createImageData(pixels.width, pixels.height)
  image.data.set(pixels.data)
  context.putImageData(image, 0, 0)
  return { url: canvas.toDataURL('image/png'), coordinates: pixels.coordinates }
}

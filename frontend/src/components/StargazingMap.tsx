import { useEffect, useRef, useState } from 'react'
import { Map, NavigationControl, ScaleControl, setWorkerUrl } from 'maplibre-gl'
import type { LngLatBoundsLike } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

// Let Vite bundle the background worker that decodes the map tiles.
setWorkerUrl(workerUrl)

// MapLibre uses [longitude, latitude]. These bounds match Architecture.md.
const WNY_BOUNDS: LngLatBoundsLike = [
  [-79.8, 42.0],
  [-77.0, 43.4],
]
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/dark'

function StargazingMap() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const [status, setStatus] = useState('Loading the map…')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let map: Map
    try {
      map = new Map({
        container: containerRef.current,
        style: MAP_STYLE,
        bounds: WNY_BOUNDS,
        // Keep navigation inside our project's Western New York region.
        maxBounds: WNY_BOUNDS,
        fitBoundsOptions: { padding: 32 },
        minZoom: 3,
        maxZoom: 18,
      })
    } catch {
      setStatus('')
      setError('The map could not start. Try a browser with WebGL enabled.')
      return
    }

    mapRef.current = map
    map.addControl(new NavigationControl(), 'top-right')
    map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left')
    map.getCanvas().setAttribute('aria-label', 'Interactive map of Western New York')
    map.getCanvas().setAttribute('aria-describedby', 'map-instructions')

    map.on('load', () => setStatus(''))
    map.on('error', () => {
      setStatus('')
      setError('Some map details could not load. Check your internet connection and reload the page.')
    })
    // Clear a temporary network warning once the map finishes loading again.
    map.on('idle', () => {
      if (map.isStyleLoaded() && map.areTilesLoaded()) {
        setStatus('')
        setError(null)
      }
    })

    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(containerRef.current)

    // React development mode mounts twice; remove the old map each time.
    return () => {
      resizeObserver.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [])

  function resetView() {
    mapRef.current?.fitBounds(WNY_BOUNDS, {
      padding: 32,
      bearing: 0,
      pitch: 0,
      duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 800,
    })
  }

  return (
    <section className="map-section" aria-label="Explore Western New York">
      <div className="map-toolbar">
        <p id="map-instructions">
          Drag to explore. Scroll or use + / − to zoom.
          <span className="keyboard-hint"> You can also focus the map and use the arrow keys.</span>
        </p>
        <button type="button" onClick={resetView}>
          Back to Western New York
        </button>
      </div>
      <div className="map-frame">
        <div ref={containerRef} className="map-container" />
        {status && <p className="map-notice" role="status">{status}</p>}
        {error && <p className="map-notice map-error" role="alert">{error}</p>}
      </div>
    </section>
  )
}

export default StargazingMap

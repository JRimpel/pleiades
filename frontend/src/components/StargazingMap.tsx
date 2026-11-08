import { useEffect, useRef, useState } from 'react'
import { Map, Marker, NavigationControl, ScaleControl, setWorkerUrl } from 'maplibre-gl'
import type {
  ExpressionSpecification,
  GeoJSONSource,
  IControl,
  ImageSource,
  MapLayerMouseEvent,
  MapMouseEvent,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { PhotoMarker, ScoresResponse } from '../api/types'
import { DATA_BOUNDS, PAN_BOUNDS, isWithinBounds } from '../lib/region'
import type { Bounds } from '../lib/region'
import { scoreColorExpression } from '../lib/scoreColors'
import { TRANSPARENT_PNG, buildScoreSurface } from '../lib/scoreSurface'
import type { ImageCorners } from '../lib/scoreSurface'
import type { UserLocation } from '../lib/useUserLocation'

// Let Vite bundle the background worker that decodes the map tiles.
setWorkerUrl(workerUrl)

/** How many zoom levels closer than "fit" the map starts, and than "PAN_BOUNDS fills the screen" it stops zooming out. */
const ZOOM_CLOSER = 0.5

/** Zoom at which `bounds` exactly fill a `width` × `height` viewport in both directions (MapLibre uses 512 px tiles). */
function zoomToFill([[west, south], [east, north]]: Bounds, width: number, height: number) {
  const mercatorY = (lat: number) => (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2
  const zoomForWidth = Math.log2((width * 360) / (512 * (east - west)))
  const zoomForHeight = Math.log2(height / (512 * (mercatorY(south) - mercatorY(north))))
  return Math.max(zoomForWidth, zoomForHeight)
}

/** Starting-view padding that keeps the data clear of the title card, slider card, and map controls. */
function fitPadding() {
  return window.innerWidth <= 640
    ? { top: 100, bottom: 150, left: 8, right: 8 }
    : { top: 96, bottom: 140, left: 24, right: 56 }
}
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/dark'

const SCORE_SOURCE = 'scores'
const SURFACE_SOURCE = 'score-surface'
const SURFACE_LAYER = 'score-surface'
/** Invisible grid squares: never drawn, but still clickable so the popup can find the cell. */
const FILL_LAYER = 'score-fill'
const SPOT_LAYER = 'spot-circle'
const SPOT_LABEL_LAYER = 'spot-label'
const EMPTY_COLLECTION: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
const EMPTY_IMAGE_CORNERS: ImageCorners = [
  [-79.8, 43.4],
  [-77.0, 43.4],
  [-77.0, 42.0],
  [-79.8, 42.0],
]

const USER_SOURCE = 'user-location'
const USER_ACCURACY_LAYER = 'user-accuracy'
const USER_ACCURACY_OUTLINE_LAYER = 'user-accuracy-outline'
const USER_DOT_LAYER = 'user-dot'
const USER_BLUE = '#3b82f6'
const EARTH_RADIUS_M = 6_371_008.8

/** Approximate circle of `radiusM` metres around (lat, lon), as a closed polygon ring. */
function circlePolygon(lat: number, lon: number, radiusM: number, steps = 64): GeoJSON.Polygon {
  const angular = (radiusM / EARTH_RADIUS_M) * (180 / Math.PI)
  const lonScale = Math.max(Math.cos((lat * Math.PI) / 180), 1e-6)
  const ring: [number, number][] = []
  for (let i = 0; i <= steps; i++) {
    const theta = (2 * Math.PI * i) / steps
    ring.push([lon + (angular * Math.sin(theta)) / lonScale, lat + angular * Math.cos(theta)])
  }
  return { type: 'Polygon', coordinates: [ring] }
}

/** The blue dot and its accuracy ring, or nothing when the location is unknown or outside the region. */
function userLocationData(location: UserLocation | null | undefined): GeoJSON.FeatureCollection {
  if (!location || !isWithinBounds(location.lat, location.lon)) return EMPTY_COLLECTION
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: circlePolygon(location.lat, location.lon, location.accuracyM),
      },
      { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [location.lon, location.lat] } },
    ],
  }
}

/** Map button that flies to the user's position. Disabled until a position inside the region is known. */
class LocateControl implements IControl {
  private container: HTMLDivElement | null = null
  private readonly button: HTMLButtonElement

  constructor(onClick: () => void) {
    this.button = document.createElement('button')
    this.button.type = 'button'
    this.button.className = 'locate-button'
    this.button.addEventListener('click', onClick)
    const icon = document.createElement('span')
    icon.className = 'locate-icon'
    icon.setAttribute('aria-hidden', 'true')
    this.button.append(icon)
    this.setEnabled(false)
  }

  onAdd() {
    this.container = document.createElement('div')
    this.container.className = 'maplibregl-ctrl maplibregl-ctrl-group'
    this.container.append(this.button)
    return this.container
  }

  onRemove() {
    this.container?.remove()
    this.container = null
  }

  setEnabled(enabled: boolean) {
    this.button.disabled = !enabled
    const label = enabled ? 'Center on my location' : 'Your location is not available'
    this.button.setAttribute('aria-label', label)
    this.button.title = label
  }
}

/** Accuracy ring under the curated spots; the dot above everything. Neither is clickable. */
function addUserLocationLayers(map: Map) {
  map.addSource(USER_SOURCE, { type: 'geojson', data: EMPTY_COLLECTION })
  map.addLayer(
    {
      id: USER_ACCURACY_LAYER,
      type: 'fill',
      source: USER_SOURCE,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': USER_BLUE, 'fill-opacity': 0.12 },
    },
    SPOT_LAYER,
  )
  map.addLayer(
    {
      id: USER_ACCURACY_OUTLINE_LAYER,
      type: 'line',
      source: USER_SOURCE,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'line-color': USER_BLUE, 'line-opacity': 0.4, 'line-width': 1 },
    },
    SPOT_LAYER,
  )
  map.addLayer({
    id: USER_DOT_LAYER,
    type: 'circle',
    source: USER_SOURCE,
    filter: ['==', ['geometry-type'], 'Point'],
    paint: {
      'circle-color': USER_BLUE,
      'circle-radius': 7,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  })
}

// ---- Community photos: clustered bubbles on the canvas, single photos as HTML thumbnails ----

const PHOTO_SOURCE = 'photos'
const PHOTO_CLUSTER_GLOW_LAYER = 'photo-cluster-glow'
const PHOTO_CLUSTER_LAYER = 'photo-clusters'
const PHOTO_CLUSTER_COUNT_LAYER = 'photo-cluster-count'
const PHOTO_LAYERS = [PHOTO_CLUSTER_GLOW_LAYER, PHOTO_CLUSTER_LAYER, PHOTO_CLUSTER_COUNT_LAYER]
const PHOTO_RING = '#b8caff'
const IS_CLUSTER: ExpressionSpecification = ['has', 'point_count']

const photoDateFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

function photoCollection(photos: PhotoMarker[] | undefined): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: (photos ?? []).map((photo) => ({
      type: 'Feature',
      // Empty strings rather than null: null properties don't survive the GeoJSON worker.
      properties: { id: photo.id, thumb_url: photo.thumb_url ?? '', taken_at: photo.taken_at ?? '' },
      geometry: { type: 'Point', coordinates: [photo.lon, photo.lat] },
    })),
  }
}

function addPhotoLayers(map: Map) {
  map.addSource(PHOTO_SOURCE, {
    type: 'geojson',
    data: EMPTY_COLLECTION,
    cluster: true,
    clusterRadius: 48,
    clusterMaxZoom: 14,
  })
  const radius: ExpressionSpecification = ['step', ['get', 'point_count'], 18, 10, 22, 50, 27]
  map.addLayer({
    id: PHOTO_CLUSTER_GLOW_LAYER,
    type: 'circle',
    source: PHOTO_SOURCE,
    filter: IS_CLUSTER,
    paint: { 'circle-color': PHOTO_RING, 'circle-opacity': 0.35, 'circle-blur': 0.9, 'circle-radius': ['+', radius, 8] },
  })
  map.addLayer({
    id: PHOTO_CLUSTER_LAYER,
    type: 'circle',
    source: PHOTO_SOURCE,
    filter: IS_CLUSTER,
    paint: {
      'circle-color': '#1d2a44',
      'circle-radius': radius,
      'circle-stroke-color': PHOTO_RING,
      'circle-stroke-width': 3,
    },
  })
  map.addLayer({
    id: PHOTO_CLUSTER_COUNT_LAYER,
    type: 'symbol',
    source: PHOTO_SOURCE,
    filter: IS_CLUSTER,
    layout: {
      'text-field': ['get', 'point_count_abbreviated'],
      'text-font': ['Noto Sans Bold'],
      'text-size': 13,
      'text-allow-overlap': true,
    },
    paint: { 'text-color': '#f1f5ff' },
  })
}

/** A round thumbnail button for one photo (an `<img>`, so presigned URLs need no CORS). */
function photoMarkerElement(id: string, thumbUrl: string, takenAt: string, onOpen: (id: string) => void) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'photo-marker'
  const when = takenAt ? `taken ${photoDateFormat.format(new Date(takenAt))}` : 'capture time unknown'
  button.setAttribute('aria-label', `Open sky photo, ${when}`)
  button.title = 'Sky photo'
  if (thumbUrl) {
    const img = document.createElement('img')
    img.src = thumbUrl
    img.alt = ''
    img.loading = 'lazy'
    img.decoding = 'async'
    // A broken or expired thumbnail falls back to the placeholder star.
    img.addEventListener('error', () => {
      img.remove()
      button.classList.add('placeholder')
    })
    button.append(img)
  } else {
    button.classList.add('placeholder')
  }
  button.addEventListener('click', (event) => {
    event.stopPropagation()
    // MapLibre markers swallow mousedown, so a click never focuses the button. Focus it so
    // the viewer can hand focus back here when it closes.
    button.focus({ preventScroll: true })
    onOpen(id)
  })
  return button
}

/** Where to fly the camera. Change `key` to fly again to the same place. */
export interface MapFocus {
  lat: number
  lon: number
  key: number
}

interface StargazingMapProps {
  scores?: ScoresResponse
  /** Called with the cell id when the user clicks a grid square or curated spot. */
  onSelectCell?: (cellId: number) => void
  selectedCellId?: number | null
  focus?: MapFocus
  /** Drawn as a blue dot with an accuracy ring when inside the region. */
  userLocation?: UserLocation | null
  /** Community photo pins. */
  photos?: PhotoMarker[]
  showPhotos?: boolean
  /** A single photo pin was clicked. */
  onOpenPhoto?: (id: string) => void
  /** A cluster of photos at (nearly) the same spot was clicked at full zoom. */
  onOpenPhotoGroup?: (ids: string[]) => void
  /** While set, a map click reports its position here instead of selecting a cell. */
  onPickLocation?: ((lat: number, lon: number) => void) | null
  /** Location chosen for a photo being uploaded. */
  draftPin?: { lat: number; lon: number } | null
  children?: React.ReactNode
}

/**
 * Add the score sources and layers. The smooth surface sits under basemap labels so town
 * names stay readable; curated spots sit on top of everything.
 */
function addScoreLayers(map: Map) {
  map.addSource(SCORE_SOURCE, {
    type: 'geojson',
    data: EMPTY_COLLECTION,
    promoteId: 'cell_id',
  })
  map.addSource(SURFACE_SOURCE, {
    type: 'image',
    url: TRANSPARENT_PNG,
    coordinates: EMPTY_IMAGE_CORNERS,
  })

  const firstSymbolLayer = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id
  const hovered: ExpressionSpecification = ['boolean', ['feature-state', 'hover'], false]
  const selected: ExpressionSpecification = ['boolean', ['feature-state', 'selected'], false]
  const emphasized: ExpressionSpecification = ['any', hovered, selected]

  map.addLayer(
    {
      id: SURFACE_LAYER,
      type: 'raster',
      source: SURFACE_SOURCE,
      paint: {
        'raster-opacity': 0.55,
        'raster-resampling': 'linear',
        'raster-fade-duration': 0,
      },
    },
    firstSymbolLayer,
  )
  map.addLayer(
    {
      id: FILL_LAYER,
      type: 'fill',
      source: SCORE_SOURCE,
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-opacity': 0 },
    },
    firstSymbolLayer,
  )
  // Curated spots go on top of everything so they stay visible and clickable.
  map.addLayer({
    id: SPOT_LAYER,
    type: 'circle',
    source: SCORE_SOURCE,
    filter: ['==', ['geometry-type'], 'Point'],
    paint: {
      'circle-color': scoreColorExpression,
      'circle-radius': ['case', emphasized, 10, 8],
      'circle-stroke-color': ['case', selected, '#b3cbff', '#ffffff'],
      'circle-stroke-width': ['case', selected, 4, hovered, 3, 2],
    },
  })
  map.addLayer({
    id: SPOT_LABEL_LAYER,
    type: 'symbol',
    source: SCORE_SOURCE,
    filter: ['==', ['geometry-type'], 'Point'],
    layout: {
      'text-field': ['coalesce', ['get', 'name'], ''],
      'text-font': ['Noto Sans Bold'],
      'text-size': 12,
      // Prefer below the dot; fall back to other sides so nearby spots (e.g. Hunters Creek
      // next to Chestnut Ridge) don't hide each other's labels at the default zoom.
      'text-variable-anchor': ['top', 'bottom', 'right', 'left'],
      'text-radial-offset': 1.2,
      'text-justify': 'auto',
      'text-optional': true,
    },
    paint: {
      'text-color': '#f1f5ff',
      'text-halo-color': '#0b0f17',
      'text-halo-width': 1.5,
    },
  })
}

function StargazingMap({
  scores,
  onSelectCell,
  selectedCellId,
  focus,
  userLocation,
  photos,
  showPhotos = true,
  onOpenPhoto,
  onOpenPhotoGroup,
  onPickLocation,
  draftPin,
  children,
}: StargazingMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const locateRef = useRef<LocateControl | null>(null)
  // Handlers registered once on the map read the latest props through refs.
  const showPhotosRef = useRef(showPhotos)
  const onOpenPhotoRef = useRef(onOpenPhoto)
  const onOpenPhotoGroupRef = useRef(onOpenPhotoGroup)
  const onPickRef = useRef(onPickLocation)
  useEffect(() => {
    showPhotosRef.current = showPhotos
    onOpenPhotoRef.current = onOpenPhoto
    onOpenPhotoGroupRef.current = onOpenPhotoGroup
    onPickRef.current = onPickLocation
  }, [showPhotos, onOpenPhoto, onOpenPhotoGroup, onPickLocation])
  /** Re-syncs the HTML photo thumbnails with the clustered source; set once the map loads. */
  const syncPhotoMarkersRef = useRef<() => void>(() => {})
  // The locate button is created once, so it reads the latest position through a ref.
  const userLocationRef = useRef(userLocation)
  useEffect(() => {
    userLocationRef.current = userLocation
  }, [userLocation])
  const [mapReady, setMapReady] = useState(false)
  const [status, setStatus] = useState('Loading the map…')
  const [error, setError] = useState<string | null>(null)
  // The click handler is registered once, so read the latest callback through a ref.
  const onSelectRef = useRef(onSelectCell)
  useEffect(() => {
    onSelectRef.current = onSelectCell
  }, [onSelectCell])

  useEffect(() => {
    if (!containerRef.current) return

    let map: Map
    try {
      map = new Map({
        container: containerRef.current,
        style: MAP_STYLE,
        // Keep navigation within ~2° of the data.
        maxBounds: PAN_BOUNDS,
        maxZoom: 18,
      })
    } catch {
      // Report the external renderer failure asynchronously; cancel on unmount.
      let disposed = false
      queueMicrotask(() => {
        if (!disposed) {
          setStatus('')
          setError('The map could not start. Try a browser with WebGL enabled.')
        }
      })
      return () => { disposed = true }
    }

    mapRef.current = map

    // Zoom-out limit: a little closer than the point where PAN_BOUNDS fills the screen.
    // It depends on the viewport size, so it is recomputed on resize.
    const updateMinZoom = () => {
      const { clientWidth, clientHeight } = map.getContainer()
      if (clientWidth > 0 && clientHeight > 0) {
        map.setMinZoom(zoomToFill(PAN_BOUNDS, clientWidth, clientHeight) + ZOOM_CLOSER)
      }
    }
    updateMinZoom()

    // Starting view: fit the data clear of the overlay cards, then move a little closer.
    const camera = map.cameraForBounds(DATA_BOUNDS, { padding: fitPadding() })
    if (camera?.center && camera.zoom !== undefined) {
      map.jumpTo({ center: camera.center, zoom: Math.max(camera.zoom + ZOOM_CLOSER, map.getMinZoom()) })
    }

    map.addControl(new NavigationControl(), 'top-right')
    const locate = new LocateControl(() => {
      const location = userLocationRef.current
      if (!location || !isWithinBounds(location.lat, location.lon)) return
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      map.flyTo({
        center: [location.lon, location.lat],
        zoom: Math.max(map.getZoom(), 10),
        essential: true,
        duration: reduceMotion ? 0 : 1200,
      })
    })
    locateRef.current = locate
    map.addControl(locate, 'top-right')
    map.addControl(new ScaleControl({ unit: 'imperial' }), 'bottom-left')
    map.getCanvas().setAttribute('aria-label', 'Interactive map of Western New York stargazing scores')
    map.getCanvas().setAttribute('aria-describedby', 'map-instructions')

    // Hover: highlight one feature at a time using feature-state.
    let hoveredId: string | number | undefined
    const clearHover = () => {
      if (hoveredId !== undefined) {
        map.setFeatureState({ source: SCORE_SOURCE, id: hoveredId }, { hover: false })
        hoveredId = undefined
      }
      map.getCanvas().style.cursor = ''
    }
    const onHover = (event: MapLayerMouseEvent) => {
      if (onPickRef.current) {
        map.getCanvas().style.cursor = 'crosshair'
        return
      }
      // Only spots get a highlight; the smooth surface just shows a pointer so it stays seamless.
      const [spot] = map.queryRenderedFeatures(event.point, { layers: [SPOT_LAYER] })
      if (spot?.id !== hoveredId) {
        clearHover()
        if (spot?.id !== undefined) {
          hoveredId = spot.id
          map.setFeatureState({ source: SCORE_SOURCE, id: hoveredId }, { hover: true })
        }
      }
      const overScores = spot ?? map.queryRenderedFeatures(event.point, { layers: [FILL_LAYER] })[0]
      map.getCanvas().style.cursor = overScores ? 'pointer' : ''
    }
    const onPhotoClusterHover = () => {
      if (!onPickRef.current) map.getCanvas().style.cursor = 'pointer'
    }

    /** Zoom into a photo cluster, or open all its photos when they can't be separated further. */
    const openCluster = async (clusterId: number, center: [number, number]) => {
      const source = map.getSource<GeoJSONSource>(PHOTO_SOURCE)
      if (!source) return
      const zoom = await source.getClusterExpansionZoom(clusterId)
      if (zoom > map.getZoom() + 0.01 && zoom <= map.getMaxZoom()) {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        map.easeTo({ center, zoom, duration: reduceMotion ? 0 : 500 })
        return
      }
      const leaves = await source.getClusterLeaves(clusterId, 200, 0)
      const ids = leaves.map((leaf) => String(leaf.properties?.id)).filter(Boolean)
      if (ids.length) onOpenPhotoGroupRef.current?.(ids)
    }

    const onClick = (event: MapMouseEvent) => {
      if (onPickRef.current) {
        onPickRef.current(event.lngLat.lat, event.lngLat.lng)
        return
      }
      if (showPhotosRef.current) {
        const [cluster] = map.queryRenderedFeatures(event.point, { layers: [PHOTO_CLUSTER_LAYER] })
        if (cluster && cluster.geometry.type === 'Point') {
          void openCluster(Number(cluster.properties.cluster_id), cluster.geometry.coordinates as [number, number])
          return
        }
      }
      const [feature] = map.queryRenderedFeatures(event.point, { layers: [SPOT_LAYER, FILL_LAYER] })
      const cellId = Number(feature?.properties.cell_id)
      if (feature && Number.isFinite(cellId)) onSelectRef.current?.(cellId)
    }

    // Unclustered photos are HTML markers, kept in step with what the clustered source renders.
    let photoMarkers: Record<string, Marker> = {}
    const syncPhotoMarkers = () => {
      const next: Record<string, Marker> = {}
      if (showPhotosRef.current && map.getSource(PHOTO_SOURCE)) {
        const features = map.querySourceFeatures(PHOTO_SOURCE, { filter: ['!', IS_CLUSTER] })
        for (const feature of features) {
          if (feature.geometry.type !== 'Point') continue
          const id = String(feature.properties.id)
          const thumb = String(feature.properties.thumb_url ?? '')
          // Recreate a marker when its thumbnail appears (pending → analyzed).
          const key = `${id}|${thumb}`
          if (next[key]) continue
          const [lon, lat] = feature.geometry.coordinates
          next[key] =
            photoMarkers[key] ??
            new Marker({
              element: photoMarkerElement(id, thumb, String(feature.properties.taken_at ?? ''), (photoId) => {
                // While picking an upload location, a thumbnail counts as a click on its spot.
                if (onPickRef.current) onPickRef.current(lat, lon)
                else onOpenPhotoRef.current?.(photoId)
              }),
            })
              .setLngLat([lon, lat])
              .addTo(map)
        }
      }
      for (const [key, marker] of Object.entries(photoMarkers)) {
        if (!next[key]) marker.remove()
      }
      photoMarkers = next
    }
    syncPhotoMarkersRef.current = syncPhotoMarkers

    map.on('load', () => {
      setStatus('')
      addScoreLayers(map)
      addPhotoLayers(map)
      addUserLocationLayers(map)
      for (const layer of [FILL_LAYER, SPOT_LAYER]) {
        map.on('mousemove', layer, onHover)
        map.on('mouseleave', layer, clearHover)
      }
      map.on('mousemove', PHOTO_CLUSTER_LAYER, onPhotoClusterHover)
      map.on('mouseleave', PHOTO_CLUSTER_LAYER, clearHover)
      // One click handler for every layer, so overlapping features only act once.
      map.on('click', onClick)
      map.on('moveend', syncPhotoMarkers)
      map.on('sourcedata', (event) => {
        if (event.sourceId === PHOTO_SOURCE && event.isSourceLoaded) syncPhotoMarkers()
      })
      setMapReady(true)
    })
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

    const resizeObserver = new ResizeObserver(() => {
      map.resize()
      updateMinZoom()
    })
    resizeObserver.observe(containerRef.current)

    // React development mode mounts twice; remove the old map each time.
    return () => {
      resizeObserver.disconnect()
      for (const marker of Object.values(photoMarkers)) marker.remove()
      photoMarkers = {}
      syncPhotoMarkersRef.current = () => {}
      map.remove()
      mapRef.current = null
      locateRef.current = null
      setMapReady(false)
    }
  }, [])

  // Push new score data into the existing source whenever the selected hour changes.
  useEffect(() => {
    if (!mapReady) return
    const map = mapRef.current
    map?.getSource<GeoJSONSource>(SCORE_SOURCE)?.setData(scores ?? EMPTY_COLLECTION)
    const surface = scores ? buildScoreSurface(scores) : null
    map
      ?.getSource<ImageSource>(SURFACE_SOURCE)
      ?.updateImage(surface ?? { url: TRANSPARENT_PNG, coordinates: EMPTY_IMAGE_CORNERS })
  }, [mapReady, scores])

  // Move the blue dot and enable the locate button whenever the position changes.
  useEffect(() => {
    if (!mapReady) return
    mapRef.current?.getSource<GeoJSONSource>(USER_SOURCE)?.setData(userLocationData(userLocation))
    locateRef.current?.setEnabled(!!userLocation && isWithinBounds(userLocation.lat, userLocation.lon))
  }, [mapReady, userLocation])

  // Ring the selected curated spot (grid squares have no visible layer, so they show nothing).
  // Feature state survives setData because ids are promoted.
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || selectedCellId == null) return
    map.setFeatureState({ source: SCORE_SOURCE, id: selectedCellId }, { selected: true })
    return () => {
      if (map.getSource(SCORE_SOURCE)) {
        map.setFeatureState({ source: SCORE_SOURCE, id: selectedCellId }, { selected: false })
      }
    }
  }, [mapReady, selectedCellId])

  // Push new photo pins into the clustered source; markers re-sync once it's processed.
  useEffect(() => {
    if (!mapReady) return
    mapRef.current?.getSource<GeoJSONSource>(PHOTO_SOURCE)?.setData(photoCollection(photos))
  }, [mapReady, photos])

  // Show or hide the whole photo layer.
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    for (const layer of PHOTO_LAYERS) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', showPhotos ? 'visible' : 'none')
    }
    syncPhotoMarkersRef.current()
  }, [mapReady, showPhotos])

  // Pin the location chosen for an upload.
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !draftPin) return
    const element = document.createElement('div')
    element.className = 'draft-pin'
    element.setAttribute('aria-hidden', 'true')
    const marker = new Marker({ element, anchor: 'bottom' }).setLngLat([draftPin.lon, draftPin.lat]).addTo(map)
    return () => {
      marker.remove()
    }
  }, [mapReady, draftPin])

  // Crosshair while picking an upload location.
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map) return
    map.getCanvas().style.cursor = onPickLocation ? 'crosshair' : ''
  }, [mapReady, onPickLocation])

  // Fly to a requested place (e.g. a "Tonight's best" pick).
  useEffect(() => {
    const map = mapRef.current
    if (!mapReady || !map || !focus) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    map.flyTo({
      center: [focus.lon, focus.lat],
      zoom: Math.max(map.getZoom(), 9),
      essential: true,
      duration: reduceMotion ? 0 : 1200,
    })
  }, [mapReady, focus])

  return (
    <section className="map-section" aria-label="Explore Western New York">
      {/* Read by screen readers via the canvas's aria-describedby; not shown visually. */}
      <p id="map-instructions" className="visually-hidden">
        Drag to explore. Scroll or use plus and minus to zoom. Click a square or spot to open its details panel. Round
        photo thumbnails are community sky photos; numbered circles group several photos. You can also focus the map
        and use the arrow keys.
      </p>
      <div className="map-frame">
        <div ref={containerRef} className="map-container" />
        {status && <p className="map-notice" role="status">{status}</p>}
        {error && <p className="map-notice map-error" role="alert">{error}</p>}
        {children}
      </div>
    </section>
  )
}

export default StargazingMap

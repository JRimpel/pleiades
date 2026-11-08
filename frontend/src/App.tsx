import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { PHOTOS_KEY, usePhotos, useScoreRange, useScores, useSkyEvents, useSpot } from './api/hooks'
import type { BestSpot, ChatContext, ChatSpot } from './api/types'
import { ApiError, wipePhotos } from './api/client'
import BestSpots from './components/BestSpots'
import ChatPanel from './components/ChatPanel'
import PhotoUploadDialog from './components/PhotoUploadDialog'
import type { UploadLocation } from './components/PhotoUploadDialog'
import PhotoViewer from './components/PhotoViewer'
import ScoreLegend from './components/ScoreLegend'
import UsernamePrompt from './components/UsernamePrompt'
import { getSession, useSession } from './lib/session'
import type { Session } from './lib/session'
import SkyPanel from './components/SkyPanel'
import SpotPanel from './components/SpotPanel'
import StargazingMap from './components/StargazingMap'
import { ExploreIn3D } from './explore'
import type { MapFocus, MapHighlights, MapViewport } from './components/StargazingMap'
import TimeSlider from './components/TimeSlider'
import { nearestCell } from './lib/nearestCell'
import { isWithinBounds } from './lib/region'
import { scoreToRgb } from './lib/scoreColors'
import { HOUR_MS, toIsoHour } from './lib/time'
import { useUserLocation } from './lib/useUserLocation'
import { resolveObservingContext } from './lib/observingContext'
import { nightDate } from './explore/astronomy'
import './App.css'
import './photos.css'
import './chat.css'

/** How long the "outside Western New York" notice stays up. */
const OUTSIDE_NOTICE_MS = 8000

const SHOW_PHOTOS_KEY = 'pleiades.showPhotos'

function readShowPhotos() {
  try {
    return window.localStorage.getItem(SHOW_PHOTOS_KEY) !== 'false'
  } catch {
    return true
  }
}

interface ViewerState {
  ids: string[]
  index: number
  /** Remounts the viewer for each new opening. */
  key: number
}

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
  // Hour chosen on the slider (epoch ms). Undefined until the range loads → backend default (current hour).
  const [selectedMs, setSelectedMs] = useState<number>()
  // Wait for the slider to settle briefly before requesting a new hour.
  const [requestedMs, setRequestedMs] = useState<number>()
  const [selectedCellId, setSelectedCellId] = useState<number | null>(null)
  const [focus, setFocus] = useState<MapFocus>()
  const [skyOpen, setSkyOpen] = useState(false)
  // A picked spot's best hour, shown in the panel until the slider moves (it may be before the slider's range).
  const [panelTime, setPanelTime] = useState<string>()
  const [initialHour] = useState(() => toIsoHour(Math.floor(Date.now() / HOUR_MS) * HOUR_MS))

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

  const requestHour = requestedMs ?? defaultMs
  const requestedTime = requestHour === undefined ? undefined : toIsoHour(requestHour)
  const scores = useScores(requestedTime)
  const spotTime = panelTime ?? requestedTime ?? scores.data?.time
  const selectedSpot = useSpot(selectedCellId, spotTime)
  const observing = resolveObservingContext(
    panelTime ?? (sliderMs === undefined ? scores.data?.time ?? initialHour : toIsoHour(sliderMs)),
    selectedCellId, selectedSpot.data, scores.data, regionLocation,
  )
  const observingNight = nightDate(observing.observation.time)
  const sky = useSkyEvents(true, observing.observation, observingNight)
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

  /** Open a spot's details and fly to it; with `validTime`, also move the slider to that hour. */
  const showSpot = useCallback(
    (spot: { cell_id: number; lat: number; lon: number; valid_time?: string | null }) => {
      if (spot.valid_time) {
        let ms = Math.floor(Date.parse(spot.valid_time) / HOUR_MS) * HOUR_MS
        setPanelTime(toIsoHour(ms))
        if (minMs !== undefined && maxMs !== undefined) ms = Math.min(Math.max(ms, minMs), maxMs)
        setSelectedMs(ms)
        setRequestedMs(ms)
      } else {
        setPanelTime(undefined)
      }
      setSelectedCellId(spot.cell_id)
      setFocus({ lat: spot.lat, lon: spot.lon, key: Date.now() })
    },
    [minMs, maxMs],
  )
  const pickBest = useCallback((spot: BestSpot) => showSpot(spot), [showSpot])

  // ---- "Ask the sky" assistant ----
  const [chatOpen, setChatOpen] = useState(false)
  const [highlights, setHighlights] = useState<MapHighlights>()
  const viewportRef = useRef<MapViewport | undefined>(undefined)
  const onViewportChange = useCallback((viewport: MapViewport) => {
    viewportRef.current = viewport
  }, [])
  const contextTime = panelTime ?? (sliderMs === undefined ? undefined : toIsoHour(sliderMs))
  const getChatContext = useCallback(
    (): ChatContext => ({
      location: regionLocation ? { lat: regionLocation.lat, lon: regionLocation.lon } : undefined,
      time: contextTime,
      selected_cell_id: selectedCellId ?? undefined,
      viewport: viewportRef.current,
    }),
    [regionLocation, contextTime, selectedCellId],
  )
  // A reply that names spots flies to the first one and pulses them all. When the reply is about a
  // particular hour, the slider moves there too, so the map's colors match the scores in the reply.
  const onChatSpots = useCallback(
    (spots: ChatSpot[]) => {
      const [first] = spots
      setFocus({ lat: first.lat, lon: first.lon, key: Date.now() })
      setHighlights({ points: spots.map(({ lat, lon }) => ({ lat, lon })), key: Date.now() })
      if (first.valid_time && minMs !== undefined && maxMs !== undefined) {
        const ms = Math.floor(Date.parse(first.valid_time) / HOUR_MS) * HOUR_MS
        if (ms >= minMs && ms <= maxMs) {
          setPanelTime(undefined)
          setSelectedMs(ms)
          setRequestedMs(ms)
        }
      }
    },
    [minMs, maxMs],
  )
  const onChatPickSpot = useCallback(
    (spot: ChatSpot) => {
      // On phones both panels are bottom sheets; make room for the spot's details.
      if (window.matchMedia('(max-width: 640px)').matches) setChatOpen(false)
      showSpot(spot)
    },
    [showSpot],
  )

  // ---- Community photos ----
  const queryClient = useQueryClient()
  const session = useSession()
  const [showPhotos, setShowPhotos] = useState(readShowPhotos)
  const photos = usePhotos(showPhotos)
  const photoList = photos.data?.photos
  const [viewer, setViewer] = useState<ViewerState | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadLocation, setUploadLocation] = useState<UploadLocation | null>(null)
  const [picking, setPicking] = useState(false)
  const [justUploadedId, setJustUploadedId] = useState<string | null>(null)
  const [accountRequest, setAccountRequest] = useState<{
    reason: string
    resolve: (session: Session | null) => void
  } | null>(null)

  const toggleShowPhotos = useCallback(() => {
    setShowPhotos((shown) => {
      try {
        window.localStorage.setItem(SHOW_PHOTOS_KEY, String(!shown))
      } catch {
        // Not remembered when storage is blocked.
      }
      return !shown
    })
  }, [])

  /** The current session, or ask for a username first. Resolves null if the user cancels. */
  const ensureSession = useCallback((reason: string) => {
    const existing = getSession()
    if (existing) return Promise.resolve(existing)
    return new Promise<Session | null>((resolve) => setAccountRequest({ reason, resolve }))
  }, [])
  const finishAccountRequest = useCallback(
    (result: Session | null) => {
      accountRequest?.resolve(result)
      setAccountRequest(null)
    },
    [accountRequest],
  )

  // A single pin opens the viewer at that photo within all loaded photos (newest first).
  const openPhoto = useCallback(
    (id: string) => {
      const ids = photoList?.map((photo) => photo.id) ?? []
      const index = ids.indexOf(id)
      setViewer(index >= 0 ? { ids, index, key: Date.now() } : { ids: [id], index: 0, key: Date.now() })
    },
    [photoList],
  )
  // A cluster that can't be split further opens just its photos, newest capture first.
  const openPhotoGroup = useCallback(
    (ids: string[]) => {
      const takenMs = (id: string) => {
        const photo = photoList?.find((candidate) => candidate.id === id)
        return photo?.taken_at ? Date.parse(photo.taken_at) : 0
      }
      setViewer({ ids: [...ids].sort((a, b) => takenMs(b) - takenMs(a)), index: 0, key: Date.now() })
    },
    [photoList],
  )

  const pickLocation = useCallback((lat: number, lon: number) => {
    setUploadLocation({ lat, lon, source: 'map' })
    setPicking(false)
  }, [])
  const closeUpload = useCallback(() => {
    setUploadOpen(false)
    setUploadLocation(null)
    setPicking(false)
  }, [])
  const onUploaded = useCallback(
    (id: string) => {
      closeUpload()
      setJustUploadedId(id)
      void queryClient.invalidateQueries({ queryKey: PHOTOS_KEY })
      setViewer({ ids: [id], index: 0, key: Date.now() })
    },
    [closeUpload, queryClient],
  )

  // Demo-only: wipe every photo.
  const [wiping, setWiping] = useState(false)
  const [wipeError, setWipeError] = useState(false)
  const wipeAllPhotos = useCallback(async () => {
    if (!window.confirm('Delete ALL photos? This cannot be undone.')) return
    setWiping(true)
    setWipeError(false)
    try {
      await wipePhotos()
      setViewer(null)
      setJustUploadedId(null)
    } catch {
      setWipeError(true)
    } finally {
      setWiping(false)
      void queryClient.invalidateQueries({ queryKey: PHOTOS_KEY })
    }
  }, [queryClient])

  // Escape cancels picking a location on the map.
  useEffect(() => {
    if (!picking) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPicking(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [picking])

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
      const error = scores.error ?? range.error
      status = error instanceof ApiError && error.code === 'database_unavailable'
        ? 'Scores unavailable: the backend cannot connect to its database.'
        : error instanceof ApiError
          ? 'Scores unavailable: the backend returned an error. Try again shortly.'
          : 'Scores unavailable: the API could not be reached. Check that the backend is running.'
  } else if (scores.isLoading) {
    status = 'Loading scores…'
  } else if (scores.isFetching) {
    status = 'Updating scores…'
  } else if (range.isSuccess && minMs === undefined) {
    status = 'No forecast scores are available yet.'
  }

  return (
    <main
      className={['app', selectedCellId !== null && 'has-spot-panel', chatOpen && 'has-chat-panel']
        .filter(Boolean)
        .join(' ')}
    >
      <div className="app-map-shell">
      <header className="app-header">
        <div className="app-header-row">
          <div>
            <h1>Pleiades</h1>
            <p>Find your next constellation lookout in Western New York</p>
          </div>
          <div className="app-header-buttons">
            <button
              type="button"
              className="pill-button chat-launch-button"
              aria-expanded={chatOpen}
              onClick={() => setChatOpen((open) => !open)}
            >
              <span aria-hidden="true">✦ </span>Ask the sky
            </button>
            <button type="button" className="pill-button" onClick={() => document.getElementById('explore-title')?.scrollIntoView()}>
              Explore in 3D
            </button>
            <button
              type="button"
              className="pill-button"
              aria-expanded={skyOpen}
              aria-controls={skyPanelId}
              onClick={() => setSkyOpen((open) => !open)}
            >
              {skyOpen ? 'Hide sky' : 'Sky details'}
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
        <div className="app-header-photo-row">
          <button type="button" className="pill-button photo-upload-button" onClick={() => setUploadOpen(true)}>
            Upload photo
          </button>
          <button
            type="button"
            className="pill-button photo-toggle"
            aria-pressed={showPhotos}
            onClick={toggleShowPhotos}
            title="Show community sky photos on the map"
          >
            <span className="photo-toggle-dot" aria-hidden="true" />
            Photos{showPhotos && photoList ? ` · ${photoList.length}` : ''}
          </button>
          <button
            type="button"
            className="pill-button photo-wipe-button"
            onClick={() => void wipeAllPhotos()}
            disabled={wiping}
            title="Demo only: delete every photo"
          >
            {wiping ? 'Wiping…' : 'Wipe photos (demo)'}
          </button>
          {session && <span className="photo-signed-in" title="Your username on this browser">@{session.username}</span>}
        </div>
        {showPhotos && photos.isError && (
          <p className="photo-header-note" role="status">Community photos couldn’t be loaded.</p>
        )}
        {wipeError && (
          <p className="photo-header-note" role="status">Couldn’t wipe photos. Check that the backend is running.</p>
        )}
        {skyOpen && <SkyPanel id={skyPanelId} at={observing.observation} date={observingNight} />}
      </header>
      <StargazingMap
        scores={scores.data}
        onSelectCell={selectCell}
        selectedCellId={selectedCellId}
        focus={focus}
        userLocation={location}
        photos={photoList}
        showPhotos={showPhotos}
        onOpenPhoto={openPhoto}
        onOpenPhotoGroup={openPhotoGroup}
        onPickLocation={picking ? pickLocation : null}
        draftPin={uploadOpen ? uploadLocation : null}
        highlights={highlights}
        onViewportChange={onViewportChange}
      >
        {picking && (
          <div className="map-notice pick-notice" role="status">
            <span>Click the map where you took this photo.</span>
            <button type="button" className="photo-button secondary small" onClick={() => setPicking(false)}>
              Cancel
            </button>
          </div>
        )}
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
          time={spotTime}
          onClose={closeSpot}
          userLocation={location}
        />
      )}
      {/* Stays mounted while closed so the conversation survives. */}
      <ChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        getContext={getChatContext}
        onSpots={onChatSpots}
        onPickSpot={onChatPickSpot}
        onOpenPhotos={(ids, index) => setViewer({ ids, index, key: Date.now() })}
        hasSelectedSpot={selectedCellId !== null}
      />
      </div>
      <ExploreIn3D observation={observing.observation} conditions={observing.conditions} contextLabel={observing.label} hideControls />
      {uploadOpen && (
        <PhotoUploadDialog
          location={uploadLocation}
          onLocationChange={setUploadLocation}
          picking={picking}
          onStartPick={() => setPicking(true)}
          userLocation={regionLocation}
          ensureSession={ensureSession}
          onUploaded={onUploaded}
          onClose={closeUpload}
        />
      )}
      {viewer && (
        <PhotoViewer
          key={viewer.key}
          ids={viewer.ids}
          startIndex={viewer.index}
          justUploadedId={justUploadedId}
          ensureSession={ensureSession}
          onClose={() => setViewer(null)}
        />
      )}
      {/* Last, so it stacks above whichever dialog asked for it. */}
      {accountRequest && <UsernamePrompt reason={accountRequest.reason} onDone={finishAccountRequest} />}
    </main>
  )
}

export default App

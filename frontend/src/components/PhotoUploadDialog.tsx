import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { ApiError, createPhoto, presignPhoto, uploadToStorage } from '../api/client'
import { readPhotoMetadata } from '../lib/photoMetadata'
import { inputValueToIso, isoToInputValue } from '../lib/photoTime'
import { isWithinBounds } from '../lib/region'
import type { Session } from '../lib/session'
import { useModalDialog } from '../lib/useModalDialog'
import type { UserLocation } from '../lib/useUserLocation'

/** Same limits as backend/app/config.py. */
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_BYTES = 15 * 1024 * 1024
const MAX_CAPTION = 500

export interface UploadLocation {
  lat: number
  lon: number
  source: 'exif' | 'device' | 'map'
}

const SOURCE_LABEL: Record<UploadLocation['source'], string> = {
  exif: 'from the photo’s GPS',
  device: 'your current location',
  map: 'picked on the map',
}

interface PhotoUploadDialogProps {
  /** Owned by App so the map can show it as a draft pin and set it in pick mode. */
  location: UploadLocation | null
  onLocationChange: (location: UploadLocation | null) => void
  /** While true the dialog steps aside so the user can click the map. */
  picking: boolean
  onStartPick: () => void
  /** The user's position, only when it's inside the region. */
  userLocation: UserLocation | null
  ensureSession: (reason: string) => Promise<Session | null>
  onUploaded: (photoId: string) => void
  onClose: () => void
}

type Phase = { step: 'idle' } | { step: 'uploading'; progress: number } | { step: 'saving' }

function uploadErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'The upload failed. Check your connection and try again.'
  switch (error.code) {
    case 'storage_unavailable':
      return 'Photo uploads aren’t available right now: the server has no photo storage configured.'
    case 'storage_unreachable':
      return 'Couldn’t reach photo storage. Check your connection and try again.'
    case 'storage_upload_failed':
    case 'upload_not_found':
      return 'The upload didn’t finish. Please try again.'
    case 'file_too_large':
      return 'That photo is larger than 15 MB. Export a smaller copy and try again.'
    case 'unsupported_media_type':
      return 'Only JPEG, PNG and WebP photos are supported.'
    case 'rate_limited':
      return error.message || 'You’ve reached the hourly upload limit. Try again later.'
    case 'unauthorized':
      return 'Your account on this browser is no longer valid. Choose Share again to pick a new username.'
    case 'database_unavailable':
      return 'Uploads are unavailable right now: the backend cannot reach its database.'
    default:
      return error.message || 'The upload failed. Please try again.'
  }
}

function fileProblem(file: File): string | null {
  if (/\.hei[cf]$/i.test(file.name) || /hei[cf]/i.test(file.type)) {
    return 'HEIC photos aren’t supported yet. Export or share the photo as JPEG and try again.'
  }
  if (!ALLOWED_TYPES.includes(file.type)) return 'Choose a JPEG, PNG or WebP photo.'
  if (file.size > MAX_BYTES) return 'That photo is larger than 15 MB. Export a smaller copy and try again.'
  if (file.size === 0) return 'That file is empty.'
  return null
}

export default function PhotoUploadDialog({
  location,
  onLocationChange,
  picking,
  onStartPick,
  userLocation,
  ensureSession,
  onUploaded,
  onClose,
}: PhotoUploadDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const titleId = useId()
  const fileHintId = useId()
  const timeHintId = useId()
  const captionCountId = useId()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [reading, setReading] = useState(false)
  const [gpsNote, setGpsNote] = useState<string | null>(null)
  const [takenAt, setTakenAt] = useState('')
  const [timeSource, setTimeSource] = useState<'exif' | 'user' | null>(null)
  const [caption, setCaption] = useState('')
  const [phase, setPhase] = useState<Phase>({ step: 'idle' })
  const [error, setError] = useState<string | null>(null)
  const busy = phase.step !== 'idle'
  useModalDialog(dialogRef, !picking)

  // Release the preview's object URL when it changes or the dialog unmounts.
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])
  // Cancel an in-flight upload if the dialog goes away.
  useEffect(() => () => abortRef.current?.abort(), [])

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0]
    event.target.value = ''
    if (!chosen) return
    const problem = fileProblem(chosen)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setFile(chosen)
    setPreview(URL.createObjectURL(chosen))
    setGpsNote(null)
    // A location read from the previous photo no longer applies.
    if (location?.source === 'exif') onLocationChange(null)
    if (timeSource === 'exif') {
      setTakenAt('')
      setTimeSource(null)
    }

    setReading(true)
    const metadata = await readPhotoMetadata(chosen)
    setReading(false)
    if (metadata.lat !== undefined && metadata.lon !== undefined) {
      if (isWithinBounds(metadata.lat, metadata.lon)) {
        onLocationChange({ lat: metadata.lat, lon: metadata.lon, source: 'exif' })
      } else {
        setGpsNote('This photo’s GPS location is outside the map’s region. Pick where it was taken.')
      }
    } else {
      setGpsNote('This photo has no location data (phones often remove it). Pick where it was taken.')
    }
    if (metadata.takenAt) {
      setTakenAt(isoToInputValue(metadata.takenAt))
      setTimeSource('exif')
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file || !location || busy) return
    const takenAtIso = takenAt ? inputValueToIso(takenAt) : undefined
    if (takenAt && !takenAtIso) {
      setError('Enter a valid capture time, or clear it to use the upload time.')
      return
    }
    if (takenAtIso && Date.parse(takenAtIso) > Date.now() + 60 * 60 * 1000) {
      setError('The capture time is in the future.')
      return
    }
    setError(null)
    const session = await ensureSession('to share photos')
    if (!session) return

    const controller = new AbortController()
    abortRef.current = controller
    try {
      setPhase({ step: 'uploading', progress: 0 })
      const presigned = await presignPhoto(session.token, file.type, file.size)
      await uploadToStorage(
        presigned.upload_url,
        presigned.headers,
        file,
        (progress) => setPhase({ step: 'uploading', progress }),
        controller.signal,
      )
      setPhase({ step: 'saving' })
      const trimmed = caption.trim()
      const created = await createPhoto(session.token, {
        s3_key: presigned.s3_key,
        lat: location.lat,
        lon: location.lon,
        ...(takenAtIso ? { taken_at: takenAtIso, taken_at_source: timeSource ?? 'user' } : {}),
        ...(trimmed ? { caption: trimmed } : {}),
      })
      onUploaded(created.id)
    } catch (err) {
      if (controller.signal.aborted) return
      setError(uploadErrorMessage(err))
      setPhase({ step: 'idle' })
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  function close() {
    abortRef.current?.abort()
    onClose()
  }

  const progress = phase.step === 'uploading' ? phase.progress : phase.step === 'saving' ? 1 : 0
  const canSubmit = !!file && !!location && !busy && !reading

  return (
    <dialog
      ref={dialogRef}
      className="photo-dialog upload-dialog"
      aria-labelledby={titleId}
      aria-busy={busy || undefined}
      onCancel={(event) => {
        event.preventDefault()
        close()
      }}
    >
      <form className="photo-dialog-body" onSubmit={submit} noValidate>
        <header className="photo-dialog-header">
          <h2 id={titleId}>Share a sky photo</h2>
          <button type="button" className="icon-button" aria-label="Close upload" onClick={close}>
            ×
          </button>
        </header>
        <p className="photo-muted">
          Your photo appears on the map for everyone, pinned at the exact spot you choose. An AI looks for
          constellations, planets and sky quality after it uploads.
        </p>

        <input
          ref={fileInputRef}
          id={`${titleId}-file`}
          className="visually-hidden"
          type="file"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          aria-describedby={fileHintId}
          onChange={chooseFile}
          disabled={busy}
        />
        {file && preview ? (
          <div className="upload-preview">
            <img src={preview} alt="Selected photo preview" />
            <div>
              <p className="upload-file-name">{file.name}</p>
              <p className="photo-small">{(file.size / (1024 * 1024)).toFixed(1)} MB</p>
              <button
                type="button"
                className="photo-button secondary small"
                onClick={() => fileInputRef.current?.click()}
                disabled={busy}
              >
                Choose a different photo
              </button>
            </div>
          </div>
        ) : (
          <label htmlFor={`${titleId}-file`} className="upload-drop">
            <span className="upload-drop-title">Choose a photo</span>
            <span id={fileHintId} className="photo-small">
              JPEG, PNG or WebP, up to 15 MB
            </span>
          </label>
        )}

        <fieldset className="photo-fieldset" disabled={busy}>
          <legend>Where was it taken?</legend>
          {reading ? (
            <p className="photo-muted" role="status">
              Reading photo details…
            </p>
          ) : location ? (
            <p className="upload-location" role="status">
              <span aria-hidden="true">📍</span> {location.lat.toFixed(5)}, {location.lon.toFixed(5)}
              <span className="photo-small"> · {SOURCE_LABEL[location.source]}</span>
            </p>
          ) : (
            <p className="photo-muted" role="status">
              {gpsNote ?? (file ? 'Pick where it was taken.' : 'Choose a photo first; its GPS location is used when available.')}
            </p>
          )}
          <div className="upload-location-actions">
            <button type="button" className="photo-button secondary small" onClick={onStartPick}>
              {location ? 'Change on map' : 'Pick on map'}
            </button>
            {userLocation && (
              <button
                type="button"
                className="photo-button secondary small"
                onClick={() => onLocationChange({ lat: userLocation.lat, lon: userLocation.lon, source: 'device' })}
              >
                Use my location
              </button>
            )}
          </div>
        </fieldset>

        <label className="photo-field">
          <span>When was it taken? (Eastern time)</span>
          <input
            type="datetime-local"
            value={takenAt}
            max={isoToInputValue(new Date().toISOString())}
            onChange={(event) => {
              setTakenAt(event.target.value)
              setTimeSource(event.target.value ? 'user' : null)
            }}
            aria-describedby={timeHintId}
            disabled={busy}
          />
        </label>
        <p id={timeHintId} className="photo-small">
          {timeSource === 'exif'
            ? 'From the photo’s metadata. Correct it if your camera clock was off.'
            : 'Optional. Leave empty to use the upload time.'}
        </p>

        <label className="photo-field">
          <span>Caption (optional)</span>
          <textarea
            value={caption}
            onChange={(event) => setCaption(event.target.value.slice(0, MAX_CAPTION))}
            maxLength={MAX_CAPTION}
            rows={2}
            placeholder="Orion over the lake, 30 s exposure…"
            aria-describedby={captionCountId}
            disabled={busy}
          />
        </label>
        <p id={captionCountId} className="photo-small photo-count">
          {caption.length}/{MAX_CAPTION}
        </p>

        {error && (
          <p className="photo-error" role="alert">
            {error}
          </p>
        )}
        {busy && (
          <div className="upload-progress" role="status">
            <progress max={1} value={progress} aria-label="Upload progress" />
            <span>{phase.step === 'saving' ? 'Saving…' : `Uploading ${Math.round(progress * 100)}%`}</span>
          </div>
        )}

        <div className="photo-dialog-actions">
          <button type="button" className="photo-button secondary" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="photo-button" disabled={!canSubmit}>
            Share photo
          </button>
        </div>
      </form>
    </dialog>
  )
}

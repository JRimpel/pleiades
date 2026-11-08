import { useEffect, useId, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError, fetchPhoto } from '../api/client'
import { PHOTOS_KEY, usePhoto, useVote } from '../api/hooks'
import type { PhotoDetail, TakenAtSource, VoteValue } from '../api/types'
import { scoreToRgb } from '../lib/scoreColors'
import { getSession, useSession } from '../lib/session'
import type { Session } from '../lib/session'
import { useModalDialog } from '../lib/useModalDialog'

const takenFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

const TIME_SOURCE: Record<TakenAtSource, string> = {
  exif: 'from photo metadata',
  user: 'entered by the photographer',
  upload_time: 'upload time',
}

const SWIPE_PX = 50

interface PhotoViewerProps {
  /** Photos to step through, in order. */
  ids: string[]
  startIndex: number
  /** The photo this browser just uploaded, so a rejected result can be explained to its owner. */
  justUploadedId?: string | null
  ensureSession: (reason: string) => Promise<Session | null>
  onClose: () => void
}

function scoreChipStyle(score: number) {
  const [r, g, b] = scoreToRgb(score)
  return { background: `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})` }
}

function AiPanel({ photo, isOwnUpload }: { photo: PhotoDetail; isOwnUpload: boolean }) {
  if (photo.ai_status === 'pending') {
    return (
      <section className="photo-ai" aria-live="polite">
        <h3>AI sky analysis</h3>
        <p className="photo-ai-pending">
          <span className="photo-spinner" aria-hidden="true" /> Analyzing the sky…
        </p>
      </section>
    )
  }
  if (photo.ai_status === 'rejected') {
    return (
      <section className="photo-ai" aria-live="polite">
        <h3>AI sky analysis</h3>
        <p className="photo-error">
          {isOwnUpload
            ? 'This didn’t look like a night-sky photo, so it won’t appear on the map.'
            : 'This photo was not recognized as a night-sky photo.'}
        </p>
      </section>
    )
  }
  if (photo.ai_status === 'failed') {
    return (
      <section className="photo-ai" aria-live="polite">
        <h3>AI sky analysis</h3>
        <p className="photo-muted">AI analysis is unavailable for this photo.</p>
      </section>
    )
  }
  const objects = photo.ai_objects ?? []
  return (
    <section className="photo-ai" aria-live="polite">
      <h3>AI sky analysis</h3>
      {photo.ai_description && <p>{photo.ai_description}</p>}
      {objects.length > 0 ? (
        <ul className="photo-objects" aria-label="Objects identified">
          {objects.map((object) => (
            <li key={object.name}>
              {object.name} <span>· {object.type}</span>
              <span className="photo-object-confidence"> {Math.round(object.confidence * 100)}%</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="photo-small">No specific objects were confidently identified.</p>
      )}
      <dl className="photo-facts">
        {photo.ai_sky_quality !== null && (
          <div>
            <dt>Sky quality</dt>
            <dd>{photo.ai_sky_quality}/10</dd>
          </div>
        )}
        {photo.ai_milky_way_visible !== null && (
          <div>
            <dt>Milky Way</dt>
            <dd>{photo.ai_milky_way_visible ? 'Visible' : 'Not visible'}</dd>
          </div>
        )}
      </dl>
      {photo.ai_light_pollution_notes && <p className="photo-small">{photo.ai_light_pollution_notes}</p>}
      <p className="photo-small">
        AI estimates from the image only; percentages are the model’s own confidence, not a guarantee.
      </p>
    </section>
  )
}

/** Full-screen "story" viewer for community photos, with AI analysis and voting. */
export default function PhotoViewer({ ids, startIndex, justUploadedId, ensureSession, onClose }: PhotoViewerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [index, setIndex] = useState(() => Math.min(Math.max(startIndex, 0), Math.max(ids.length - 1, 0)))
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null)
  const [voteError, setVoteError] = useState<string | null>(null)
  const swipeStart = useRef<{ x: number; y: number } | null>(null)
  const session = useSession()
  const queryClient = useQueryClient()
  const id = ids[index] ?? null
  const photo = usePhoto(id, session)
  const vote = useVote()
  useModalDialog(dialogRef)

  // Lock page scroll behind the viewer.
  useEffect(() => {
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = overflow
    }
  }, [])

  // Warm the neighbours so stepping through feels instant.
  useEffect(() => {
    for (const neighbour of [ids[index - 1], ids[index + 1]]) {
      if (!neighbour) continue
      void queryClient.prefetchQuery({
        queryKey: ['photo', neighbour, session?.username ?? 'anon'],
        queryFn: ({ signal }) => fetchPhoto(neighbour, session?.token, signal),
        staleTime: 30 * 1000,
      })
    }
  }, [ids, index, queryClient, session])

  const canPrev = index > 0
  const canNext = index < ids.length - 1
  const go = (step: number) => {
    setVoteError(null)
    setIndex((current) => Math.min(Math.max(current + step, 0), ids.length - 1))
  }

  async function castVote(value: VoteValue) {
    if (!id) return
    setVoteError(null)
    let current = getSession() ?? (await ensureSession('to vote'))
    if (!current) return
    const next: VoteValue = photo.data?.my_vote === value ? 0 : value
    try {
      await vote.mutateAsync({ id, value: next, session: current })
    } catch (error) {
      // A stale token was cleared by the client; ask once for a new account and retry.
      if (error instanceof ApiError && error.status === 401) {
        current = await ensureSession('to vote')
        if (!current) return
        try {
          await vote.mutateAsync({ id, value: next, session: current })
          return
        } catch {
          // fall through to the message
        }
      }
      setVoteError('Your vote couldn’t be saved. Try again.')
    }
  }

  function onPointerDown(event: ReactPointerEvent) {
    if (event.pointerType !== 'mouse') swipeStart.current = { x: event.clientX, y: event.clientY }
  }
  function onPointerUp(event: ReactPointerEvent) {
    const start = swipeStart.current
    swipeStart.current = null
    if (!start) return
    const dx = event.clientX - start.x
    const dy = event.clientY - start.y
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy) * 1.5) go(dx < 0 ? 1 : -1)
  }

  const data = photo.data?.id === id ? photo.data : undefined
  const imageUrl = data?.url ?? data?.thumb_url ?? null

  // When an analysis finishes, refresh the map pins so the new thumbnail (or removal) shows.
  const lastStatus = useRef<{ id: string | null; status?: string }>({ id: null })
  useEffect(() => {
    const status = data?.ai_status
    const previous = lastStatus.current
    if (previous.id === id && previous.status === 'pending' && status && status !== 'pending') {
      void queryClient.invalidateQueries({ queryKey: PHOTOS_KEY })
    }
    lastStatus.current = { id, status }
  }, [id, data?.ai_status, queryClient])
  const showFull = !!data?.url && loadedUrl === data.url

  return (
    <dialog
      ref={dialogRef}
      className="photo-viewer"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onKeyDown={(event) => {
        if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
        if (event.key === 'ArrowRight' && canNext) go(1)
        if (event.key === 'ArrowLeft' && canPrev) go(-1)
      }}
    >
      {ids.length > 1 && (
        <div className="photo-progress" aria-hidden="true">
          {ids.map((photoId, i) => (
            <span key={photoId} className={i < index ? 'seen' : i === index ? 'current' : ''} />
          ))}
        </div>
      )}
      <div className="photo-viewer-layout">
        <div className="photo-stage" onPointerDown={onPointerDown} onPointerUp={onPointerUp}>
          {imageUrl ? (
            <>
              {/* The thumbnail shows while the full image loads. */}
              {data?.thumb_url && !showFull && <img className="photo-stage-thumb" src={data.thumb_url} alt="" />}
              {data?.url && (
                <img
                  key={data.url}
                  className={showFull ? 'photo-stage-full ready' : 'photo-stage-full'}
                  src={data.url}
                  alt={data.caption ? `Night sky photo: ${data.caption}` : `Night sky photo by ${data.username}`}
                  onLoad={() => setLoadedUrl(data.url)}
                />
              )}
            </>
          ) : (
            <p className="photo-stage-empty" role="status">
              {photo.isError ? 'This photo couldn’t be loaded.' : data ? 'This photo isn’t available right now.' : 'Loading photo…'}
            </p>
          )}
          {canPrev && (
            <button type="button" className="photo-nav prev" aria-label="Previous photo" onClick={() => go(-1)}>
              ‹
            </button>
          )}
          {canNext && (
            <button type="button" className="photo-nav next" aria-label="Next photo" onClick={() => go(1)}>
              ›
            </button>
          )}
        </div>

        <aside className="photo-details" aria-label="Photo details">
          <header className="photo-details-header">
            <div>
              <h2 id={titleId}>{data ? `@${data.username}` : 'Sky photo'}</h2>
              {ids.length > 1 && (
                <p className="photo-small">
                  Photo {index + 1} of {ids.length}
                </p>
              )}
            </div>
            <button type="button" className="icon-button" aria-label="Close photo viewer" onClick={onClose} data-autofocus>
              ×
            </button>
          </header>

          {data ? (
            <>
              <p className="photo-taken">
                {data.taken_at ? takenFormat.format(new Date(data.taken_at)) : takenFormat.format(new Date(data.uploaded_at))}
                <span className="photo-small">
                  {' · '}
                  {data.taken_at ? TIME_SOURCE[data.taken_at_source ?? 'exif'] : TIME_SOURCE.upload_time}
                </span>
              </p>
              {data.caption && <p className="photo-caption">{data.caption}</p>}
              <p className="photo-location photo-small">
                {data.lat.toFixed(4)}, {data.lon.toFixed(4)}
              </p>

              <div className="photo-meta-row">
                {data.score_at_capture !== null ? (
                  <span className="photo-score" title="Stargazing score predicted for this spot and hour">
                    <span className="photo-score-swatch" style={scoreChipStyle(data.score_at_capture)} aria-hidden="true" />
                    Score at capture: {Math.round(data.score_at_capture)}
                  </span>
                ) : (
                  <span className="photo-small">No forecast score for when this was taken</span>
                )}
                <div className="photo-votes" role="group" aria-label="Vote on this photo">
                  <button
                    type="button"
                    className="vote-button"
                    aria-pressed={data.my_vote === 1}
                    aria-label="Upvote"
                    onClick={() => castVote(1)}
                    disabled={vote.isPending}
                  >
                    ▲
                  </button>
                  <span className="vote-count" aria-label={`${data.vote_count} net votes`}>
                    {data.vote_count}
                  </span>
                  <button
                    type="button"
                    className="vote-button"
                    aria-pressed={data.my_vote === -1}
                    aria-label="Downvote"
                    onClick={() => castVote(-1)}
                    disabled={vote.isPending}
                  >
                    ▼
                  </button>
                </div>
              </div>
              {voteError && (
                <p className="photo-error" role="alert">
                  {voteError}
                </p>
              )}

              <AiPanel photo={data} isOwnUpload={!!justUploadedId && justUploadedId === data.id} />
            </>
          ) : (
            <p className="photo-muted" role="status">
              {photo.isError ? 'This photo couldn’t be loaded. It may have been removed.' : 'Loading details…'}
            </p>
          )}
        </aside>
      </div>
    </dialog>
  )
}

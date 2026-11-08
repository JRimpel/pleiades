import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ApiError, postChat } from '../api/client'
import type { ChatContext, ChatMessage, ChatPhoto, ChatResponse, ChatSpot } from '../api/types'
import { spotTitle } from '../lib/placeName'
import { scoreToRgb } from '../lib/scoreColors'
import { formatLocalDayTime } from '../lib/time'

/** The API accepts at most this many messages (schemas/chat.py MAX_TURNS) of at most MAX_CHARS each. */
const MAX_TURNS = 12
const MAX_CHARS = 1000

interface Turn {
  role: 'user' | 'assistant'
  content: string
  /** Only on assistant turns. */
  response?: ChatResponse
  /** An assistant turn that is an error notice, not part of the conversation sent back to the API. */
  error?: boolean
}

interface ChatPanelProps {
  open: boolean
  onClose: () => void
  /** Read when a question is sent, so it reflects the map as it is right then. */
  getContext: () => ChatContext
  /** A reply named spots: fly to the first and pulse them all. */
  onSpots: (spots: ChatSpot[]) => void
  /** A spot chip was clicked: open its details. */
  onPickSpot: (spot: ChatSpot) => void
  /** A photo card was clicked: open the viewer on these photos at `index`. */
  onOpenPhotos: (ids: string[], index: number) => void
  /** Show "this spot" suggestions when a spot is open. */
  hasSelectedSpot: boolean
}

function swatch(score: number) {
  const [r, g, b] = scoreToRgb(score)
  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'chat_unavailable') return 'The assistant isn’t set up on this server (it needs a Gemini API key).'
    if (error.code === 'rate_limited' || error.code === 'chat_failed') return error.message
    if (error.status === 0 || error.code === 'invalid_json') return 'The assistant could not be reached. Check that the backend is running.'
    return 'The assistant couldn’t answer that. Try rephrasing.'
  }
  return 'The assistant could not be reached. Check your connection.'
}

const TOOL_LABELS: Record<string, string> = {
  find_place: 'Looked up a place',
  best_spots: 'Ranked spots by forecast score',
  spot_conditions: 'Read a spot’s score and weather',
  when_visible: 'Computed when an object is up',
  sky_tonight: 'Checked moon, twilight and planets',
  search_photos: 'Searched community photos',
}

function describeArgs(args: Record<string, unknown>) {
  return Object.entries(args)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`)
    .join(', ')
}

function SpotChip({ spot, onPick }: { spot: ChatSpot; onPick: (spot: ChatSpot) => void }) {
  const title = spotTitle(spot)
  return (
    <li>
      <button type="button" className="chat-spot" onClick={() => onPick(spot)}>
        <span
          className="chat-spot-swatch"
          aria-hidden="true"
          style={{ background: spot.score === null ? '#6b7280' : swatch(spot.score) }}
        />
        <span className="chat-spot-name">{title}</span>
        {spot.score !== null && (
          <span className="chat-spot-score">
            {Math.round(spot.score)} {spot.label}
          </span>
        )}
      </button>
    </li>
  )
}

function PhotoCard({ photo, onOpen }: { photo: ChatPhoto; onOpen: () => void }) {
  const label = photo.objects.length ? photo.objects.slice(0, 3).join(', ') : 'Night sky'
  return (
    <li>
      <button type="button" className="chat-photo" onClick={onOpen} title={photo.description ?? undefined}>
        {photo.thumb_url ? (
          <img src={photo.thumb_url} alt="" loading="lazy" />
        ) : (
          <span className="chat-photo-placeholder" aria-hidden="true" />
        )}
        <span className="chat-photo-text">
          <span className="chat-photo-objects">{label}</span>
          {photo.taken_at && <span className="chat-photo-time">{formatLocalDayTime(photo.taken_at)}</span>}
        </span>
      </button>
    </li>
  )
}

function AssistantTurn({
  turn,
  onPickSpot,
  onOpenPhotos,
}: {
  turn: Turn
  onPickSpot: (spot: ChatSpot) => void
  onOpenPhotos: (ids: string[], index: number) => void
}) {
  const response = turn.response
  const photoIds = response?.photos.map((photo) => photo.id) ?? []
  return (
    <div className={turn.error ? 'chat-turn assistant error' : 'chat-turn assistant'}>
      <p className="chat-text">{turn.content}</p>
      {response && response.spots.length > 0 && (
        <ul className="chat-spots" aria-label="Spots mentioned">
          {response.spots.map((spot) => (
            <SpotChip key={spot.cell_id} spot={spot} onPick={onPickSpot} />
          ))}
        </ul>
      )}
      {response && response.photos.length > 0 && (
        <ul className="chat-photos" aria-label="Community photos">
          {response.photos.map((photo, index) => (
            <PhotoCard key={photo.id} photo={photo} onOpen={() => onOpenPhotos(photoIds, index)} />
          ))}
        </ul>
      )}
      {response && response.tool_calls.length > 0 && (
        <details className="chat-sources">
          <summary>
            Based on {response.tool_calls.length} data look-up{response.tool_calls.length === 1 ? '' : 's'}
          </summary>
          <ul>
            {response.tool_calls.map((call, index) => (
              <li key={index}>
                <strong>{TOOL_LABELS[call.name] ?? call.name}</strong>
                {Object.keys(call.args).length > 0 && <span> ({describeArgs(call.args)})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** "Ask the sky": a side sheet that chats with the backend's grounded Gemini assistant. */
function ChatPanel({ open, onClose, getContext, onSpots, onPickSpot, onOpenPhotos, hasSelectedSpot }: ChatPanelProps) {
  const headingId = useId()
  const inputId = useId()
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Focus the box when the panel opens.
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // Keep the newest message in view.
  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [turns, pending])

  // Cancel an in-flight question if the app unmounts.
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = async (text: string) => {
    const question = text.trim().slice(0, MAX_CHARS)
    if (!question || pending) return
    const history = [...turns.filter((turn) => !turn.error), { role: 'user' as const, content: question }]
    const messages: ChatMessage[] = history
      .slice(-MAX_TURNS)
      .map(({ role, content }) => ({ role, content: content.slice(0, MAX_CHARS) }))
    // The API wants the conversation to start with the user.
    while (messages.length > 1 && messages[0].role !== 'user') messages.shift()

    setTurns((current) => [...current, { role: 'user', content: question }])
    setDraft('')
    setPending(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await postChat(messages, getContext(), controller.signal)
      setTurns((current) => [...current, { role: 'assistant', content: response.reply, response }])
      if (response.spots.length > 0) onSpots(response.spots)
    } catch (error) {
      if (controller.signal.aborted) return
      setTurns((current) => [...current, { role: 'assistant', content: errorMessage(error), error: true }])
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setPending(false)
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    void send(draft)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send(draft)
    }
  }

  const suggestions = [
    'Where’s the best spot near me tonight?',
    'When is Orion up tonight, and where should I go?',
    'Will the Leonids be visible this year?',
    hasSelectedSpot ? 'Why is this spot’s score what it is?' : 'What planets can I see tonight?',
    'Show me community photos of the Moon',
  ]

  return (
    <aside
      className="chat-panel"
      aria-labelledby={headingId}
      hidden={!open}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <header className="chat-panel-header">
        <div>
          <h2 id={headingId}>Ask the sky</h2>
          <p>Answers come from the live forecast, ephemeris and community photos.</p>
        </div>
        <div className="chat-panel-actions">
          {turns.length > 0 && (
            <button
              type="button"
              className="photo-button secondary small"
              onClick={() => {
                abortRef.current?.abort()
                setTurns([])
              }}
            >
              New chat
            </button>
          )}
          <button type="button" className="icon-button" aria-label="Close chat" onClick={onClose}>
            ×
          </button>
        </div>
      </header>

      <div className="chat-log" ref={logRef} aria-live="polite" aria-busy={pending}>
        {turns.length === 0 && (
          <div className="chat-empty">
            <p>Ask about where and when to stargaze in Western New York. Try:</p>
            <ul className="chat-suggestions">
              {suggestions.map((suggestion) => (
                <li key={suggestion}>
                  <button type="button" onClick={() => void send(suggestion)}>
                    {suggestion}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <div key={index} className="chat-turn user">
              <p className="chat-text">{turn.content}</p>
            </div>
          ) : (
            <AssistantTurn key={index} turn={turn} onPickSpot={onPickSpot} onOpenPhotos={onOpenPhotos} />
          ),
        )}
        {pending && (
          <div className="chat-turn assistant pending" role="status">
            <span className="chat-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span className="visually-hidden">Checking the forecast…</span>
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={onSubmit}>
        <label htmlFor={inputId} className="visually-hidden">
          Your question
        </label>
        <textarea
          id={inputId}
          ref={inputRef}
          rows={2}
          maxLength={MAX_CHARS}
          value={draft}
          placeholder="e.g. Is tonight good near Letchworth?"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="photo-button" disabled={pending || !draft.trim()}>
          Send
        </button>
      </form>
    </aside>
  )
}

export default ChatPanel

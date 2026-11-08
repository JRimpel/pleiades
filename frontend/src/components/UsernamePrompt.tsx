import { useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, createUser } from '../api/client'
import { setSession } from '../lib/session'
import type { Session } from '../lib/session'
import { useModalDialog } from '../lib/useModalDialog'

/** Same rule as backend/app/schemas/users.py. */
const USERNAME_PATTERN = /^[A-Za-z0-9_.-]{3,32}$/

interface UsernamePromptProps {
  /** Why an account is needed right now, e.g. "to vote". */
  reason: string
  /** Called with the new session, or null if the user cancelled. */
  onDone: (session: Session | null) => void
}

/** Pick a username to upload and vote. The backend returns a token once; this browser keeps it. */
export default function UsernamePrompt({ reason, onDone }: UsernamePromptProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const hintId = useId()
  const errorId = useId()
  const [username, setUsername] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useModalDialog(dialogRef)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const name = username.trim()
    if (!USERNAME_PATTERN.test(name)) {
      setError('Use 3–32 letters, numbers, dots, dashes or underscores.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const created = await createUser(name)
      const session = { username: created.username, token: created.token }
      setSession(session)
      onDone(session)
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'username_taken'
          ? `“${name}” is already taken. Try another.`
          : err instanceof ApiError && err.code === 'database_unavailable'
            ? 'Accounts are unavailable right now: the backend cannot reach its database.'
            : 'Could not create the account. Check your connection and try again.',
      )
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="photo-dialog username-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onDone(null)
      }}
    >
      <form className="photo-dialog-body" onSubmit={submit} noValidate>
        <h2 id={titleId}>Choose a username</h2>
        <p className="photo-muted">You need a username {reason}. It appears next to photos you share.</p>
        <label className="photo-field">
          <span>Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={32}
            required
            data-autofocus
            aria-describedby={error ? `${hintId} ${errorId}` : hintId}
            aria-invalid={error ? true : undefined}
          />
        </label>
        <p id={hintId} className="photo-small">
          No password: this browser is your account. Clearing this site's data signs you out for good.
        </p>
        {error && (
          <p id={errorId} className="photo-error" role="alert">
            {error}
          </p>
        )}
        <div className="photo-dialog-actions">
          <button type="button" className="photo-button secondary" onClick={() => onDone(null)} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="photo-button" disabled={busy}>
            {busy ? 'Creating…' : 'Continue'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

import { useSyncExternalStore } from 'react'

/**
 * The browser's photo-sharing account: a username and the bearer token the backend issued
 * once for it. There is no password, so this browser *is* the account; clearing site data
 * loses it.
 */
export interface Session {
  username: string
  token: string
}

const STORAGE_KEY = 'pleiades.session'
const listeners = new Set<() => void>()
let cached: Session | null | undefined

function readStored(): Session | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const value: unknown = JSON.parse(raw)
    if (
      typeof value === 'object' && value !== null &&
      typeof (value as Session).username === 'string' && typeof (value as Session).token === 'string'
    ) {
      return { username: (value as Session).username, token: (value as Session).token }
    }
  } catch {
    // Storage blocked (private mode, sandboxed preview) or corrupt: act signed out.
  }
  return null
}

function notify() {
  for (const listener of listeners) listener()
}

export function getSession(): Session | null {
  if (cached === undefined) cached = readStored()
  return cached
}

export function setSession(session: Session | null) {
  cached = session
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Keep the in-memory session for this tab even when storage is unavailable.
  }
  notify()
}

/** Called when the backend rejects the stored token (401). */
export function clearSession() {
  setSession(null)
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  // Keep tabs in sync when another tab signs in.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return
    cached = readStored()
    listener()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribe, getSession, () => null)
}

import { loadLauncherClientIdentity } from './launcherBridge'

export const CLIENT_ID_HEADER = 'X-ChemSSH-Client-Id'

const CLIENT_ID_STORAGE_KEY = 'chemssh.clientId.v1'
const CLIENT_ID_PATTERN = /^client_[A-Za-z0-9_.-]+$/

let currentClientId: string | null = null
let clientIdSource: 'launcher' | 'browser' = 'browser'
let initializationPromise: Promise<string> | null = null

export async function initializeClientSession(): Promise<string> {
  if (initializationPromise) {
    return initializationPromise
  }

  initializationPromise = (async () => {
    // Try Launcher bridge identity first
    try {
      const launcherIdentity = await loadLauncherClientIdentity()
      if (launcherIdentity?.enabled && launcherIdentity.client_id && CLIENT_ID_PATTERN.test(launcherIdentity.client_id)) {
        currentClientId = launcherIdentity.client_id
        clientIdSource = 'launcher'
        // Write to localStorage as fallback for this origin
        storeClientId(currentClientId)
        return currentClientId
      }
    } catch {
      // Launcher identity not available, fall back to localStorage
    }

    // Fall back to browser localStorage
    const stored = readStoredClientId()
    if (stored) {
      currentClientId = stored
      clientIdSource = 'browser'
      return currentClientId
    }

    // Generate new browser client_id
    const clientId = `client_${newClientIdToken()}`
    currentClientId = clientId
    clientIdSource = 'browser'
    storeClientId(clientId)
    return currentClientId
  })()

  return initializationPromise
}

export function getClientId(): string {
  if (currentClientId) {
    return currentClientId
  }

  // Synchronous fallback for compatibility
  const stored = readStoredClientId()
  if (stored) {
    currentClientId = stored
    return stored
  }

  const clientId = `client_${newClientIdToken()}`
  currentClientId = clientId
  storeClientId(clientId)
  return clientId
}

export function getClientIdSource(): 'launcher' | 'browser' {
  return clientIdSource
}

export function clientIdHeaders() {
  return { [CLIENT_ID_HEADER]: getClientId() }
}

function readStoredClientId() {
  try {
    const value = window.localStorage.getItem(CLIENT_ID_STORAGE_KEY)
    return value && CLIENT_ID_PATTERN.test(value) ? value : null
  } catch {
    return null
  }
}

function storeClientId(clientId: string) {
  try {
    window.localStorage.setItem(CLIENT_ID_STORAGE_KEY, clientId)
  } catch {
    // Non-persistent browser contexts still get a stable id for this page.
  }
}

function newClientIdToken() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  }

  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

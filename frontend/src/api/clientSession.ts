export const CLIENT_ID_HEADER = 'X-ChemSSH-Client-Id'

const CLIENT_ID_STORAGE_KEY = 'chemssh.clientId.v1'
const CLIENT_ID_PATTERN = /^client_[A-Za-z0-9_.-]+$/

export function getClientId() {
  const stored = readStoredClientId()
  if (stored) return stored

  const clientId = `client_${newClientIdToken()}`
  storeClientId(clientId)
  return clientId
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

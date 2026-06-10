import { API_BASE, ApiError } from './http'
import { isPathInsideWorkspace } from './workspaceScope'
import type { FileItem } from './files'

export type LauncherBridgeCapabilities = {
  enabled: boolean
  version: number
  launcher?: string
  session_id?: string
  workspace_root?: string
  features: {
    system_icons?: boolean
    open_default?: boolean
    open_text?: boolean
    open_sync_events?: boolean
  }
  endpoints: {
    icon?: string
    open?: string
    open_text?: string
    sync_events?: string
  }
}

export type LauncherBridgeOpenResponse = {
  ok: boolean
  remote_path: string
  local_path?: string
}

export type LauncherBridgeSyncEvent = {
  seq: number
  time?: string
  remote_path: string
  local_path?: string
  status: 'done' | 'error' | string
  error?: string
}

export type LauncherClientIdentity = {
  enabled: boolean
  version: number
  client_id: string
  source?: string
}

let currentCapabilities: LauncherBridgeCapabilities | null = null

export async function loadLauncherBridgeCapabilities(): Promise<LauncherBridgeCapabilities | null> {
  try {
    const capabilities = await bridgeRequest<LauncherBridgeCapabilities>('/api/chemssh-bridge/capabilities')
    if (!capabilities?.enabled) {
      currentCapabilities = null
      return null
    }
    currentCapabilities = {
      ...capabilities,
      features: capabilities.features ?? {},
      endpoints: capabilities.endpoints ?? {}
    }
    return currentCapabilities
  } catch {
    currentCapabilities = null
    return null
  }
}

export function launcherFileIconUrl(item: Pick<FileItem, 'name' | 'type'>, size = 16): string | null {
  const endpoint = currentCapabilities?.endpoints.icon
  if (!currentCapabilities?.enabled || !currentCapabilities.features.system_icons || !endpoint) return null
  const query = new URLSearchParams({
    name: item.type === 'directory' ? 'folder' : item.name,
    is_dir: item.type === 'directory' ? '1' : '0',
    size: String(size)
  })
  return `${bridgeUrl(endpoint)}?${query.toString()}`
}

export function openWithLocalApp(path: string): Promise<LauncherBridgeOpenResponse> {
  const endpoint = currentCapabilities?.endpoints.open
  if (!endpoint || !currentCapabilities?.features.open_default) {
    throw new ApiError('LAUNCHER_BRIDGE_UNAVAILABLE', 'Launcher local open is unavailable')
  }
  return bridgeRequest<LauncherBridgeOpenResponse>(endpoint, {
    method: 'POST',
    body: JSON.stringify({ path })
  })
}

export function openWithNotepad(path: string): Promise<LauncherBridgeOpenResponse> {
  const endpoint = currentCapabilities?.endpoints.open_text
  if (!endpoint || !currentCapabilities?.features.open_text) {
    throw new ApiError('LAUNCHER_BRIDGE_UNAVAILABLE', 'Launcher text open is unavailable')
  }
  return bridgeRequest<LauncherBridgeOpenResponse>(endpoint, {
    method: 'POST',
    body: JSON.stringify({ path })
  })
}

export async function pollLauncherOpenSyncEvents(afterSeq: number): Promise<LauncherBridgeSyncEvent[]> {
  const endpoint = currentCapabilities?.endpoints.sync_events
  if (!endpoint || !currentCapabilities?.features.open_sync_events) return []
  const query = new URLSearchParams({ after: String(afterSeq) })
  const response = await bridgeRequest<{ events?: LauncherBridgeSyncEvent[] }>(`${endpoint}?${query.toString()}`)
  return Array.isArray(response.events) ? response.events : []
}

export async function loadLauncherClientIdentity(): Promise<LauncherClientIdentity | null> {
  try {
    const identity = await bridgeRequest<LauncherClientIdentity>('/api/chemssh-bridge/client-identity')
    if (!identity?.enabled || !identity.client_id) {
      return null
    }
    return identity
  } catch {
    return null
  }
}

export function launcherBridgeIconFailureKey(item: Pick<FileItem, 'name' | 'type' | 'extension'>, size = 16) {
  if (item.type === 'directory') return `directory:${size}`
  const extension = item.extension || item.name.split('.').pop() || item.name
  return `file:${extension.toLowerCase()}:${size}`
}

export function parentDirectoryPath(path: string) {
  const normalized = normalizeRemotePath(path)
  const index = normalized.lastIndexOf('/')
  if (index < 0) return ''
  if (index === 0) return '/'
  return normalized.slice(0, index)
}

export { isPathInsideWorkspace }

function normalizeRemotePath(path: string) {
  return path.replace(/\\/g, '/').replace(/\/+$/, '')
}

async function bridgeRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(bridgeUrl(endpoint), {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    const error = data?.error
    throw new ApiError(error?.code ?? 'HTTP_ERROR', error?.message ?? response.statusText)
  }
  return data as T
}

function bridgeUrl(endpoint: string) {
  if (/^https?:\/\//i.test(endpoint)) return endpoint
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
  return `${API_BASE}${path}`
}

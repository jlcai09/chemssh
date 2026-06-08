import { request } from './http'
import { CLIENT_ID_HEADER, getClientId } from './clientSession'
import { getCurrentWorkspaceScopeKey } from './workspaceScope'
import type { CanvasBoardState, ClientPreferences } from '../types/canvasBoard'

export interface ClientCacheResponse {
  enabled: boolean
  client_id: string
  preferences: ClientPreferences
  boards: CanvasBoardState
  updated_at: string
}

function jsonHeaders() {
  return {
    'Content-Type': 'application/json',
    [CLIENT_ID_HEADER]: getClientId(),
    'X-ChemSSH-Cache-Scope': getCurrentWorkspaceScopeKey()
  }
}

export function loadClientCache() {
  return request<ClientCacheResponse>('/api/client-cache', {
    headers: jsonHeaders()
  })
}

export function saveClientPreferences(preferences: ClientPreferences) {
  return request<ClientCacheResponse>('/api/client-cache/preferences', {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(preferences)
  })
}

export function saveCanvasBoards(state: CanvasBoardState) {
  return request<ClientCacheResponse>('/api/client-cache/boards', {
    method: 'PUT',
    headers: jsonHeaders(),
    body: JSON.stringify(state)
  })
}

export function heartbeatClientCache() {
  return request<{ client_id: string; last_seen_at: string }>('/api/client-cache/heartbeat', {
    method: 'POST',
    headers: jsonHeaders()
  })
}

export function clearClientCache() {
  return request<{ success: boolean; client_id: string; removed: boolean }>('/api/client-cache', {
    method: 'DELETE',
    headers: jsonHeaders()
  })
}

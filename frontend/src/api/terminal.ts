import { API_BASE, applyAuthQuery, request } from './http'
import { clientIdHeaders, getClientId } from './clientSession'

export interface CreateTerminalSessionPayload {
  cwd?: string | null
  shell?: string | null
  rows?: number
  cols?: number
  vim_compatibility?: boolean
}

export interface TerminalSession {
  session_id: string
  cwd: string
  shell: string
  created_at: string
  last_active_at: string
  alive: boolean
  clients?: number
}

export interface TerminalSessionList {
  items: TerminalSession[]
}

export function createTerminalSession(payload: CreateTerminalSessionPayload) {
  return request<TerminalSession>('/api/terminal/sessions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...clientIdHeaders()
    },
    body: JSON.stringify(payload)
  })
}

export function listTerminalSessions() {
  return request<TerminalSessionList>('/api/terminal/sessions', {
    headers: clientIdHeaders()
  })
}

export function closeTerminalSession(sessionId: string) {
  return request<{ success: boolean }>(`/api/terminal/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: clientIdHeaders()
  })
}

export function terminalWebSocketUrl(sessionId: string) {
  const path = `/api/terminal/ws/${encodeURIComponent(sessionId)}`
  const clientId = getClientId()
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    const url = new URL(path, API_BASE)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.searchParams.set('client_id', clientId)
    applyAuthQuery(url.searchParams)
    return url.toString()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = new URL(`${API_BASE}${path}`, `${protocol}://${window.location.host}`)
  url.searchParams.set('client_id', clientId)
  applyAuthQuery(url.searchParams)
  return url.toString()
}

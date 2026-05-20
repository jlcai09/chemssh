import { API_BASE, request } from './http'

export interface CreateTerminalSessionPayload {
  cwd?: string | null
  shell?: string | null
  rows?: number
  cols?: number
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
    body: JSON.stringify(payload)
  })
}

export function listTerminalSessions() {
  return request<TerminalSessionList>('/api/terminal/sessions')
}

export function closeTerminalSession(sessionId: string) {
  return request<{ success: boolean }>(`/api/terminal/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE'
  })
}

export function terminalWebSocketUrl(sessionId: string) {
  const path = `/api/terminal/ws/${encodeURIComponent(sessionId)}`
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    const url = new URL(path, API_BASE)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.toString()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}${API_BASE}${path}`
}

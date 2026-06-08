import type { SystemInfo } from './system'
import type {
  CanvasBoardState,
  CanvasTerminalTabBinding,
  CanvasWindowState,
  ClientPreferences
} from '../types/canvasBoard'

export type WorkspaceScope = {
  key: string
  workspaceRoot: string
  label: string
}

const DEFAULT_SCOPE: WorkspaceScope = {
  key: 'default',
  workspaceRoot: '',
  label: 'default'
}

let currentScope: WorkspaceScope = DEFAULT_SCOPE

export function createWorkspaceScope(systemInfo: SystemInfo, origin = browserOrigin()): WorkspaceScope {
  const workspaceRoot = systemInfo.workspace_root || ''
  const label = [
    origin,
    systemInfo.username || '',
    systemInfo.hostname || '',
    workspaceRoot
  ].join('|')
  return {
    key: `scope_${hashScopeLabel(label)}`,
    workspaceRoot,
    label
  }
}

export function setCurrentWorkspaceScope(scope: WorkspaceScope | null | undefined) {
  currentScope = scope ?? DEFAULT_SCOPE
}

export function getCurrentWorkspaceScope() {
  return currentScope
}

export function getCurrentWorkspaceScopeKey() {
  return currentScope.key
}

export function scopedLocalStorageKey(baseKey: string) {
  const scopeKey = getCurrentWorkspaceScopeKey()
  return scopeKey === DEFAULT_SCOPE.key ? baseKey : `${baseKey}.${scopeKey}`
}

export function isPathInsideWorkspace(path: string | null | undefined, workspaceRoot: string | null | undefined) {
  if (!path || !workspaceRoot) return false
  const rootPlatform = pathPlatform(workspaceRoot)
  const targetPlatform = pathPlatform(path)
  if (rootPlatform === 'unknown' || targetPlatform === 'unknown' || rootPlatform !== targetPlatform) return false

  const root = normalizePathForCompare(workspaceRoot, rootPlatform)
  const target = normalizePathForCompare(path, targetPlatform)
  if (!root || !target) return false
  if (rootPlatform === 'windows') {
    const rootDrive = root.slice(0, 2).toLowerCase()
    const targetDrive = target.slice(0, 2).toLowerCase()
    if (rootDrive !== targetDrive) return false
  }
  if (root === '/') return target.startsWith('/')
  if (/^[a-z]:\/$/i.test(root)) return target === root || target.startsWith(root)
  return target === root || target.startsWith(`${root}/`)
}

export function workspacePathOrRoot(path: string | null | undefined, workspaceRoot: string | null | undefined) {
  return isPathInsideWorkspace(path, workspaceRoot) ? String(path) : (workspaceRoot ?? '')
}

export function sanitizeClientPreferencesForWorkspace(preferences: ClientPreferences, workspaceRoot: string): ClientPreferences {
  const workspace = preferences.workspace
  return {
    ...preferences,
    terminal: preferences.terminal
      ? {
          ...preferences.terminal,
          tabs: sanitizeTerminalTabs(preferences.terminal.tabs, workspaceRoot)
        }
      : undefined,
    workspace: workspace
      ? {
          ...workspace,
          currentPath: workspacePathOrRoot(workspace.currentPath, workspaceRoot)
        }
      : workspace,
    logs: {
      ...(preferences.logs ?? {}),
      tailLines: preferences.logs?.tailLines ?? 20
    }
  }
}

export function sanitizeCanvasBoardStateForWorkspace(state: CanvasBoardState, workspaceRoot: string): CanvasBoardState {
  if (!workspaceRoot) return state
  return {
    ...state,
    boards: state.boards.map(board => ({
      ...board,
      windows: board.windows.map(windowState => sanitizeCanvasWindowState(windowState, workspaceRoot))
    }))
  }
}

export function sanitizeTerminalTabs(
  tabs: CanvasTerminalTabBinding[] | undefined,
  workspaceRoot: string
): CanvasTerminalTabBinding[] | undefined {
  if (!Array.isArray(tabs)) return undefined
  const sanitized = tabs.flatMap(tab => {
    if (!tab.cwd || !isPathInsideWorkspace(tab.cwd, workspaceRoot)) return []
    return [tab]
  })
  const activeIndex = sanitized.findIndex(tab => tab.active)
  if (sanitized.length > 0 && activeIndex < 0) {
    sanitized[0] = { ...sanitized[0], active: true }
  }
  return sanitized
}

function sanitizeCanvasWindowState(windowState: CanvasWindowState, workspaceRoot: string): CanvasWindowState {
  const payload = { ...(windowState.payload ?? {}) }
  if (windowState.type === 'file-manager') {
    payload.path = workspacePathOrRoot(payloadString(payload.path), workspaceRoot)
    payload.selectedPaths = payloadStringArray(payload.selectedPaths).filter(path => isPathInsideWorkspace(path, workspaceRoot))
    const selectedLogPath = payloadString(payload.selectedLogPath)
    payload.selectedLogPath = isPathInsideWorkspace(selectedLogPath, workspaceRoot) ? selectedLogPath : null
  } else if (windowState.type === 'tail' || windowState.type === 'preview') {
    const path = payloadString(payload.path)
    payload.path = isPathInsideWorkspace(path, workspaceRoot) ? path : ''
  } else if (windowState.type === 'terminal') {
    payload.tabBindings = sanitizeTerminalTabs(
      Array.isArray(payload.tabBindings) ? payload.tabBindings as CanvasTerminalTabBinding[] : undefined,
      workspaceRoot
    ) ?? []
  }
  return { ...windowState, payload }
}

function payloadString(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function payloadStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function pathPlatform(path: string): 'windows' | 'posix' | 'unknown' {
  const trimmed = path.trim()
  if (/^[A-Za-z]:[\\/]/.test(trimmed)) return 'windows'
  if (/^[\\/]{2}[^\\/]/.test(trimmed)) return 'windows'
  if (trimmed.startsWith('/')) return 'posix'
  return 'unknown'
}

function normalizePathForCompare(path: string, platform: 'windows' | 'posix' | 'unknown') {
  let normalized = path.trim().replace(/\\/g, '/').replace(/\/+/g, '/')
  if (platform === 'windows') normalized = normalized.toLowerCase()
  while (normalized.length > 1 && normalized.endsWith('/') && !/^[a-z]:\/$/i.test(normalized)) {
    normalized = normalized.slice(0, -1)
  }
  return normalized
}

function hashScopeLabel(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function browserOrigin() {
  if (typeof window === 'undefined') return ''
  return window.location.origin
}

import { loadClientCache, saveClientPreferences as saveClientPreferencesRequest } from './clientCache'
import {
  getCurrentWorkspaceScope,
  sanitizeClientPreferencesForWorkspace,
  scopedLocalStorageKey,
  setCurrentWorkspaceScope,
  type WorkspaceScope
} from './workspaceScope'
import type { ClientPreferences, ThemePreferences } from '../types/canvasBoard'

const LOCAL_PREFS_KEY = 'chemssh.preferences.v1'
export const DEFAULT_THEME_PREFERENCES: ThemePreferences = {
  animatedBackdrop: false,
  glassBlur: false
}

let preferences: ClientPreferences = readLocalPreferences()
let loadPromise: Promise<ClientPreferences> | null = null
let saveTimer: number | undefined

export function getClientPreferences() {
  return preferences
}

export function configureClientPreferencesScope(scope: WorkspaceScope) {
  if (getCurrentWorkspaceScope().key === scope.key) return
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = undefined
  loadPromise = null
  setCurrentWorkspaceScope(scope)
  preferences = readLocalPreferences()
}

export function clearLocalClientPreferences() {
  preferences = defaultClientPreferences()
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = undefined
  try {
    window.localStorage.removeItem(scopedLocalStorageKey(LOCAL_PREFS_KEY))
    window.localStorage.removeItem(LOCAL_PREFS_KEY)
  } catch {
    // Ignore storage failures.
  }
}

export async function loadClientPreferencesState() {
  if (loadPromise) return loadPromise
  loadPromise = loadClientCache()
    .then(cache => {
      setClientPreferencesState(cache.preferences)
      return preferences
    })
    .catch(() => preferences)
  return loadPromise
}

export function setClientPreferencesState(next: ClientPreferences | null | undefined) {
  const patch = (next ?? { version: 1 }) as unknown as Record<string, unknown>
  preferences = normalizeScopedPreferences(deepMerge(preferences as unknown as Record<string, unknown>, patch))
  writeLocalPreferences(preferences)
}

export async function saveClientPreferencesPatch(
  patch: Partial<ClientPreferences>,
  options: { immediate?: boolean } = {}
) {
  preferences = normalizeScopedPreferences(deepMerge(preferences as unknown as Record<string, unknown>, patch as Record<string, unknown>))
  writeLocalPreferences(preferences)
  if (saveTimer) window.clearTimeout(saveTimer)
  if (options.immediate) {
    await persistPreferences()
    return
  }
  saveTimer = window.setTimeout(() => {
    void persistPreferences()
  }, 700)
}

async function persistPreferences() {
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = undefined
  await saveClientPreferencesRequest(preferences)
}

export function normalizeClientPreferences(value: Partial<ClientPreferences> | Record<string, unknown> | null | undefined): ClientPreferences {
  if (!value) return defaultClientPreferences()
  const typed = value as Partial<ClientPreferences>
  return {
    ...typed,
    version: 1,
    terminal: {
      ...(typed.terminal ?? {}),
      tabs: Array.isArray(typed.terminal?.tabs) ? typed.terminal.tabs : undefined
    },
    logs: {
      ...(typed.logs ?? {}),
      tailLines: typed.logs?.tailLines ?? 20
    },
    theme: normalizeThemePreferences(typed.theme)
  }
}

export function normalizeThemePreferences(value?: Partial<ThemePreferences> | null): ThemePreferences {
  return {
    animatedBackdrop: value?.animatedBackdrop === true,
    glassBlur: value?.glassBlur === true
  }
}

function defaultClientPreferences(): ClientPreferences {
  return {
    version: 1,
    logs: { tailLines: 20 },
    theme: normalizeThemePreferences(DEFAULT_THEME_PREFERENCES)
  }
}

function deepMerge<T extends Record<string, unknown>>(target: T, patch: Record<string, unknown>): T {
  const next = { ...target } as Record<string, unknown>
  for (const [key, value] of Object.entries(patch)) {
    if (isPlainObject(value) && isPlainObject(next[key])) {
      next[key] = deepMerge(next[key] as Record<string, unknown>, value)
    } else {
      next[key] = value
    }
  }
  return next as T
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function readLocalPreferences(): ClientPreferences {
  try {
    const scopedRaw = window.localStorage.getItem(scopedLocalStorageKey(LOCAL_PREFS_KEY))
    const raw = scopedRaw ?? window.localStorage.getItem(LOCAL_PREFS_KEY)
    if (!raw) return defaultClientPreferences()
    return normalizeScopedPreferences(JSON.parse(raw) as ClientPreferences)
  } catch {
    return defaultClientPreferences()
  }
}

function writeLocalPreferences(value: ClientPreferences) {
  try {
    window.localStorage.setItem(scopedLocalStorageKey(LOCAL_PREFS_KEY), JSON.stringify(value))
  } catch {
    // Preferences are best-effort; live UI state still updates.
  }
}

function normalizeScopedPreferences(value: Partial<ClientPreferences> | Record<string, unknown> | null | undefined): ClientPreferences {
  const normalized = normalizeClientPreferences(value)
  const workspaceRoot = getCurrentWorkspaceScope().workspaceRoot
  return workspaceRoot ? sanitizeClientPreferencesForWorkspace(normalized, workspaceRoot) : normalized
}

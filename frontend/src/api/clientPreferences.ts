import { loadClientCache, saveClientPreferences as saveClientPreferencesRequest } from './clientCache'
import type { ClientPreferences } from '../types/canvasBoard'

const LOCAL_PREFS_KEY = 'chemssh.preferences.v1'

let preferences: ClientPreferences = readLocalPreferences()
let loadPromise: Promise<ClientPreferences> | null = null
let saveTimer: number | undefined

export function getClientPreferences() {
  return preferences
}

export function clearLocalClientPreferences() {
  preferences = { version: 1, logs: { tailLines: 20 } }
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = undefined
  try {
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
  preferences = normalizeClientPreferences(deepMerge(preferences as unknown as Record<string, unknown>, patch))
  writeLocalPreferences(preferences)
}

export async function saveClientPreferencesPatch(
  patch: Partial<ClientPreferences>,
  options: { immediate?: boolean } = {}
) {
  preferences = normalizeClientPreferences(deepMerge(preferences as unknown as Record<string, unknown>, patch as Record<string, unknown>))
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
  if (!value) return { version: 1, logs: { tailLines: 20 } }
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
    }
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
    const raw = window.localStorage.getItem(LOCAL_PREFS_KEY)
    if (!raw) return { version: 1, logs: { tailLines: 20 } }
    return normalizeClientPreferences(JSON.parse(raw) as ClientPreferences)
  } catch {
    return { version: 1, logs: { tailLines: 20 } }
  }
}

function writeLocalPreferences(value: ClientPreferences) {
  try {
    window.localStorage.setItem(LOCAL_PREFS_KEY, JSON.stringify(value))
  } catch {
    // Preferences are best-effort; live UI state still updates.
  }
}

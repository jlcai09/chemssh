import type { FileItem } from './files'
import type { PreviewAutoOpenPreferences, PreviewAutoOpenSource } from '../types/canvasBoard'

export const PREVIEW_AUTO_OPEN_DEFAULT_FILENAMES = ['optimized.traj', 'OUTCAR']
export const PREVIEW_AUTO_OPEN_MAX_FILENAMES = 20

export interface PreviewAutoOpenSettings {
  enabled: boolean
  source: PreviewAutoOpenSource
  terminalTabId: string
  filenames: string[]
}

export interface PreviewAutoOpenTerminalOption {
  tabId: string
  title: string
  cwd: string
  active: boolean
}

export function defaultPreviewAutoOpenSettings(): PreviewAutoOpenSettings {
  return {
    enabled: false,
    source: 'file-manager',
    terminalTabId: '',
    filenames: [...PREVIEW_AUTO_OPEN_DEFAULT_FILENAMES]
  }
}

export function normalizePreviewAutoOpenSettings(
  value?: Partial<PreviewAutoOpenPreferences> | null
): PreviewAutoOpenSettings {
  const defaults = defaultPreviewAutoOpenSettings()
  if (!value || typeof value !== 'object') return defaults
  const source: PreviewAutoOpenSource =
    value.source === 'active-terminal' || value.source === 'terminal' || value.source === 'file-manager'
      ? value.source
      : defaults.source
  const filenames = Array.isArray(value.filenames)
    ? normalizeAutoOpenFilenames(value.filenames)
    : defaults.filenames
  return {
    enabled: value.enabled === true,
    source,
    terminalTabId: typeof value.terminalTabId === 'string' ? value.terminalTabId : '',
    filenames: filenames.length > 0 ? filenames : defaults.filenames
  }
}

export function normalizeAutoOpenFilenames(values: unknown[]): string[] {
  const filenames: string[] = []
  const seen = new Set<string>()
  for (const value of values) {
    if (typeof value !== 'string') continue
    const name = value.trim()
    if (!name || seen.has(name)) continue
    seen.add(name)
    filenames.push(name)
    if (filenames.length >= PREVIEW_AUTO_OPEN_MAX_FILENAMES) break
  }
  return filenames
}

export function toPreviewAutoOpenPreferences(settings: PreviewAutoOpenSettings): PreviewAutoOpenPreferences {
  return {
    enabled: settings.enabled,
    source: settings.source,
    terminalTabId: settings.terminalTabId,
    filenames: normalizeAutoOpenFilenames(settings.filenames)
  }
}

export function findAutoOpenCandidate(items: FileItem[], filenames: string[]): FileItem | null {
  for (const name of normalizeAutoOpenFilenames(filenames)) {
    const match = items.find(item => item.type === 'file' && item.name === name)
    if (match) return match
  }
  return null
}

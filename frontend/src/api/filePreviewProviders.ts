import type { FileItem } from './files'
import type { StructureSource } from '../types/structure'

export interface FilePreviewProvider {
  id: string
  pluginId?: string
  panelId?: string
  title: string
  priority?: number
  apiBase?: string
  accepts?: {
    extensions?: string[]
    filenames?: string[]
    preview_types?: string[]
  }
  probe?: {
    method?: string
    apiPath?: string
  }
  open?: {
    mode?: string
    reuse?: string
    structureSource?: StructureSource
  }
}

export interface PreviewProbeResponse {
  can_preview?: boolean
  reason?: string | null
}

export function extensionFromName(name: string) {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

export function providerMatchesItem(provider: FilePreviewProvider, item: FileItem) {
  const accepts = provider.accepts
  if (!accepts) return true
  const extension = (item.extension || extensionFromName(item.name)).toLowerCase()
  const extensions = (accepts.extensions ?? []).map(value => value.toLowerCase())
  const filenames = (accepts.filenames ?? []).map(value => value.toLowerCase())
  const previewTypes = accepts.preview_types ?? []
  const matchesExtension = extensions.length === 0 || extensions.includes(extension)
  const matchesFilename = filenames.length === 0 || filenames.includes(item.name.toLowerCase())
  const matchesPreviewType = previewTypes.length === 0 || previewTypes.includes(item.preview_type)
  return matchesExtension && matchesFilename && matchesPreviewType
}

export function hasActivePreviewProvider(item: FileItem, providers: FilePreviewProvider[] = []) {
  if (item.type !== 'file') return false
  return providers.some(provider => providerMatchesItem(provider, item))
}

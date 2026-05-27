import type { FileItem } from './files'
import { downloadSelectionUrl } from './http'

export const CHEMWEB_FILE_DRAG_MIME = 'application/x-chemweb-files'
export const CHEMWEB_FILE_PATHS_MIME = 'application/x-chemweb-file-paths'

export interface ChemwebFileDragPayload {
  source: 'chemweb:file-manager'
  version: 1
  paths: string[]
  items: Pick<FileItem, 'name' | 'path' | 'type' | 'size' | 'mtime' | 'extension' | 'preview_type' | 'format'>[]
}

export function createChemwebFileDragPayload(items: FileItem[]): ChemwebFileDragPayload {
  return {
    source: 'chemweb:file-manager',
    version: 1,
    paths: items.map(item => item.path),
    items: items.map(item => ({
      name: item.name,
      path: item.path,
      type: item.type,
      size: item.size,
      mtime: item.mtime,
      extension: item.extension,
      preview_type: item.preview_type,
      format: item.format
    }))
  }
}

export function formatFileDragTerminalInput(paths: string[]) {
  return paths.length === 0 ? '' : ` ${paths.join(' ')}`
}

export function getFileDragDownloadUrl(paths: string[]) {
  const relative = downloadSelectionUrl(paths)
  return new URL(relative, window.location.href).href
}

export function writeChemwebFileDrag(dataTransfer: DataTransfer, items: FileItem[]) {
  const payload = createChemwebFileDragPayload(items)
  const paths = payload.paths
  const downloadUrl = getFileDragDownloadUrl(paths)
  const filename = paths.length === 1 ? items[0]?.name ?? 'chemweb-file' : 'chemweb-selection.zip'

  dataTransfer.effectAllowed = 'copy'
  dataTransfer.setData(CHEMWEB_FILE_DRAG_MIME, JSON.stringify(payload))
  dataTransfer.setData(CHEMWEB_FILE_PATHS_MIME, JSON.stringify(paths))
  dataTransfer.setData('text/plain', formatFileDragTerminalInput(paths))
  dataTransfer.setData('text/uri-list', downloadUrl)
  dataTransfer.setData('DownloadURL', `${paths.length === 1 ? 'application/octet-stream' : 'application/zip'}:${filename}:${downloadUrl}`)
}

export function readChemwebFileDrag(dataTransfer: DataTransfer | null): ChemwebFileDragPayload | null {
  if (!dataTransfer) return null

  const payload = readJson(dataTransfer.getData(CHEMWEB_FILE_DRAG_MIME))
  if (isChemwebFileDragPayload(payload)) return payload

  const paths = readJson(dataTransfer.getData(CHEMWEB_FILE_PATHS_MIME))
  if (Array.isArray(paths) && paths.every(path => typeof path === 'string')) {
    return {
      source: 'chemweb:file-manager',
      version: 1,
      paths,
      items: paths.map(path => ({
        name: pathBaseName(path),
        path,
        type: 'file',
        size: null,
        mtime: '',
        extension: '',
        preview_type: 'file'
      }))
    }
  }

  return null
}

export function hasChemwebFileDrag(event: DragEvent) {
  return Array.from(event.dataTransfer?.types ?? []).includes(CHEMWEB_FILE_DRAG_MIME)
}

function readJson(value: string) {
  if (!value) return null
  try {
    return JSON.parse(value) as unknown
  } catch {
    return null
  }
}

function isChemwebFileDragPayload(value: unknown): value is ChemwebFileDragPayload {
  if (!value || typeof value !== 'object') return false
  const payload = value as Partial<ChemwebFileDragPayload>
  return payload.source === 'chemweb:file-manager'
    && payload.version === 1
    && Array.isArray(payload.paths)
    && payload.paths.every(path => typeof path === 'string')
}

function pathBaseName(path: string) {
  const normalized = path.trim().replace(/[\\/]+$/, '')
  if (!normalized) return path
  return normalized.split(/[\\/]/).filter(Boolean).pop() ?? normalized
}

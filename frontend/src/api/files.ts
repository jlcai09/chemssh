import { request, requestBlob } from './http'

export type FileKind = 'file' | 'directory'
export type PreviewType = 'text' | 'structure' | 'file' | 'directory'

export interface FileItem {
  name: string
  path: string
  type: FileKind
  size: number | null
  mtime: string
  extension: string
  preview_type: PreviewType
  format?: string | null
}

export interface DirectoryListing {
  path: string
  parent?: string | null
  items: FileItem[]
}

export interface FileReadResponse {
  path: string
  name: string
  encoding: string
  content: string
  preview_type: PreviewType
  format?: string | null
  size: number
}

export interface FileOperationResponse {
  success: boolean
  path?: string | null
  message: string
}

export interface TailResponse {
  path: string
  lines: number
  content: string
  truncated: boolean
}

export function listFiles(path?: string) {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  return request<DirectoryListing>(`/api/files/list${query}`)
}

export function readFile(path: string, force = false) {
  const query = new URLSearchParams({ path })
  if (force) query.set('force', 'true')
  return request<FileReadResponse>(`/api/files/read?${query.toString()}`)
}

export function writeFile(path: string, content: string) {
  return request<FileOperationResponse>('/api/files/write', {
    method: 'POST',
    body: JSON.stringify({ path, content })
  })
}

export function deletePath(path: string) {
  return request<FileOperationResponse>(`/api/files/delete?path=${encodeURIComponent(path)}`, {
    method: 'DELETE'
  })
}

export function renamePath(oldPath: string, newPath: string) {
  return request<FileOperationResponse>('/api/files/rename', {
    method: 'POST',
    body: JSON.stringify({ old_path: oldPath, new_path: newPath })
  })
}

export function makeDirectory(path: string, name: string) {
  return request<FileOperationResponse>('/api/files/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path, name })
  })
}

export function uploadFile(path: string, file: File) {
  const form = new FormData()
  form.set('path', path)
  form.set('file', file)
  return request<FileOperationResponse>('/api/files/upload', {
    method: 'POST',
    body: form
  })
}

export function tailFile(path: string, lines?: number) {
  const query = new URLSearchParams({ path })
  if (lines !== undefined) query.set('lines', String(lines))
  return request<TailResponse>(`/api/files/tail?${query.toString()}`)
}

export function downloadArchive(paths: string[]) {
  return requestBlob('/api/files/download-archive', {
    method: 'POST',
    body: JSON.stringify({ paths })
  })
}

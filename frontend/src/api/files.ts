import { clearCache } from './requestCache'
import {
  API_BASE,
  ApiError,
  authHeaders,
  cachedGet,
  isAuthRequiredError,
  promptForAuthToken,
  request,
  requestBlob
} from './http'

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

export interface MovePathEntry {
  path: string
  targetName?: string
  overwrite?: boolean
}

export interface UploadProgress {
  loaded: number
  total: number
  lengthComputable: boolean
}

export interface TailResponse {
  path: string
  lines: number
  content: string
  truncated: boolean
}

export interface ListFilesOptions {
  refresh?: boolean
}

const FILE_LIST_CACHE_TTL_MS = 1000

function fileListPath(path?: string) {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  return `/api/files/list${query}`
}

function clearRequestCacheAfter<T>(promise: Promise<T>): Promise<T> {
  return promise.then(result => {
    clearCache()
    return result
  })
}

export function listFiles(path?: string, options: ListFilesOptions = {}) {
  const requestPath = fileListPath(path)
  if (options.refresh) clearCache(`GET:${requestPath}`)
  return cachedGet<DirectoryListing>(requestPath, FILE_LIST_CACHE_TTL_MS)
}

export function readFile(path: string, force = false) {
  const query = new URLSearchParams({ path })
  if (force) query.set('force', 'true')
  return request<FileReadResponse>(`/api/files/read?${query.toString()}`)
}

export function writeFile(path: string, content: string) {
  return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/write', {
    method: 'POST',
    body: JSON.stringify({ path, content })
  }))
}

export function deletePath(path: string) {
  return clearRequestCacheAfter(request<FileOperationResponse>(`/api/files/delete?path=${encodeURIComponent(path)}`, {
    method: 'DELETE'
  }))
}

export function renamePath(oldPath: string, newPath: string) {
  return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/rename', {
    method: 'POST',
    body: JSON.stringify({ old_path: oldPath, new_path: newPath })
  }))
}

export function movePaths(paths: string[], targetDirectory: string, entries?: MovePathEntry[]) {
  return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/move', {
    method: 'POST',
    body: JSON.stringify({ paths, target_directory: targetDirectory, items: entries ?? [] })
  }))
}

export function copyPaths(paths: string[], targetDirectory: string, entries?: MovePathEntry[]) {
  return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/copy', {
    method: 'POST',
    body: JSON.stringify({ paths, target_directory: targetDirectory, items: entries ?? [] })
  }))
}

export function makeDirectory(path: string, name: string) {
  return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path, name })
  }))
}

export interface UploadFileOptions {
  relativePath?: string
  onProgress?: (progress: UploadProgress) => void
}

export function uploadFile(
  path: string,
  file: File,
  optionsOrProgress?: UploadFileOptions | ((progress: UploadProgress) => void)
) {
  const options = typeof optionsOrProgress === 'function'
    ? { onProgress: optionsOrProgress }
    : (optionsOrProgress ?? {})
  const form = new FormData()
  form.set('path', path)
  if (options.relativePath) form.set('relative_path', options.relativePath)
  form.set('file', file)

  if (!options.onProgress) {
    return clearRequestCacheAfter(request<FileOperationResponse>('/api/files/upload', {
      method: 'POST',
      body: form
    }))
  }

  async function uploadWithProgress(): Promise<FileOperationResponse> {
    for (;;) {
      try {
        return await uploadWithProgressOnce()
      } catch (error) {
        if (!isAuthRequiredError(error)) throw error
        await promptForAuthToken()
      }
    }
  }

  function uploadWithProgressOnce() {
    return new Promise<FileOperationResponse>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE}/api/files/upload`)
      xhr.withCredentials = true
      const headers = authHeaders()
      headers.forEach((value, key) => xhr.setRequestHeader(key, value))
      xhr.upload.onprogress = event => {
        options.onProgress?.({
          loaded: event.loaded,
          total: event.lengthComputable ? event.total : file.size,
          lengthComputable: event.lengthComputable
        })
      }
      xhr.onload = () => {
        let data: unknown = null
        if (xhr.responseText) {
          try {
            data = JSON.parse(xhr.responseText) as unknown
          } catch {
            data = null
          }
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          clearCache()
          resolve(data as FileOperationResponse)
          return
        }
        const error = data && typeof data === 'object' ? (data as { error?: { code?: string; message?: string } }).error : null
        reject(new ApiError(error?.code ?? 'HTTP_ERROR', error?.message ?? xhr.statusText, xhr.status))
      }
      xhr.onerror = () => reject(new ApiError('NETWORK_ERROR', 'Upload failed'))
      xhr.onabort = () => reject(new ApiError('UPLOAD_ABORTED', 'Upload aborted'))
      xhr.send(form)
    })
  }

  return uploadWithProgress()
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

import { cachedRequest, dedupeRequest } from './requestCache'

export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options
  })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    const error = data?.error
    throw new ApiError(error?.code ?? 'HTTP_ERROR', error?.message ?? response.statusText)
  }
  return data as T
}

/**
 * Cached GET request with deduplication
 * Automatically caches GET requests for 5 seconds and deduplicates concurrent requests
 */
export async function cachedGet<T>(path: string, ttl?: number): Promise<T> {
  const cacheKey = `GET:${path}`

  return cachedRequest(
    cacheKey,
    () => dedupeRequest(cacheKey, () => request<T>(path, { method: 'GET' })),
    ttl
  )
}

export async function requestBlob(path: string, options: RequestInit = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options
  })

  if (!response.ok) {
    const text = await response.text()
    let message = response.statusText
    let code = 'HTTP_ERROR'
    if (text) {
      try {
        const data = JSON.parse(text)
        code = data?.error?.code ?? code
        message = data?.error?.message ?? message
      } catch {
        message = text
      }
    }
    throw new ApiError(code, message)
  }

  const disposition = response.headers.get('content-disposition') ?? ''
  const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/)
  const encodedName = filenameMatch?.[1] ?? filenameMatch?.[2]
  return {
    blob: await response.blob(),
    filename: encodedName ? decodeURIComponent(encodedName) : undefined
  }
}

export function downloadUrl(path: string): string {
  return `${API_BASE}/api/files/download?path=${encodeURIComponent(path)}`
}

export function downloadSelectionUrl(paths: string[], options: { forceArchive?: boolean } = {}): string {
  if (paths.length === 1 && !options.forceArchive) return downloadUrl(paths[0])
  const query = new URLSearchParams()
  for (const path of paths) query.append('path', path)
  return `${API_BASE}/api/files/download-selection?${query.toString()}`
}

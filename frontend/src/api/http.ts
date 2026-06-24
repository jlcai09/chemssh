import { cachedRequest, dedupeRequest } from './requestCache'
import { ElMessageBox } from 'element-plus'
import { t } from '../i18n'

export const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const ENV_AUTH_TOKEN = import.meta.env.VITE_CHEMSSH_TOKEN ?? ''
const TOKEN_STORAGE_KEY = 'chemssh.token.v1'
const AUTH_REQUIRED_CODE = 'AUTH_REQUIRED'

declare global {
  interface Window {
    __CHEMSSH_TOKEN__?: string
  }
}

export class ApiError extends Error {
  code: string
  status?: number

  constructor(code: string, message: string, status?: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

let pendingAuthPrompt: Promise<string> | null = null

export function setAuthToken(token: string | null) {
  if (typeof window === 'undefined') return
  if (token) {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
  } else {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}

export function getAuthToken(): string | null {
  const urlToken = consumeUrlToken()
  if (urlToken) return urlToken

  if (typeof window !== 'undefined') {
    const windowToken = window.__CHEMSSH_TOKEN__?.trim()
    if (windowToken) return windowToken

    const storedToken = window.sessionStorage.getItem(TOKEN_STORAGE_KEY)?.trim()
    if (storedToken) return storedToken
  }

  const envToken = String(ENV_AUTH_TOKEN || '').trim()
  return envToken || null
}

export function authHeaders(headers?: HeadersInit, options: { replaceAuth?: boolean } = {}): Headers {
  const next = new Headers(headers)
  if (options.replaceAuth) next.delete('Authorization')
  const token = getAuthToken()
  if (token && !next.has('Authorization')) {
    next.set('Authorization', `Bearer ${token}`)
  }
  return next
}

export function applyAuthQuery(params: URLSearchParams) {
  const token = getAuthToken()
  if (token && !params.has('token') && !params.has('access_token')) {
    params.set('token', token)
  }
}

export function apiUrl(path: string): string {
  const baseUrl = /^https?:\/\//i.test(path) ? path : `${API_BASE}${path}`
  const token = getAuthToken()
  if (!token) return baseUrl

  const fallbackBase = typeof window !== 'undefined' ? window.location.href : 'http://localhost/'
  const parsed = new URL(baseUrl, fallbackBase)
  if (!parsed.searchParams.has('token') && !parsed.searchParams.has('access_token')) {
    parsed.searchParams.set('token', token)
  }
  return parsed.toString()
}

function consumeUrlToken(): string | null {
  if (typeof window === 'undefined') return null

  const url = new URL(window.location.href)
  const queryToken = url.searchParams.get('chemssh_token') ?? url.searchParams.get('token') ?? ''
  const hashParams = url.hash.startsWith('#') ? new URLSearchParams(url.hash.slice(1)) : new URLSearchParams()
  const hashToken = hashParams.get('chemssh_token') ?? hashParams.get('token') ?? ''
  const token = (queryToken || hashToken).trim()
  if (!token) return null

  setAuthToken(token)
  url.searchParams.delete('chemssh_token')
  url.searchParams.delete('token')
  hashParams.delete('chemssh_token')
  hashParams.delete('token')
  url.hash = hashParams.toString() ? `#${hashParams.toString()}` : ''
  window.history.replaceState(window.history.state, document.title, url.toString())
  return token
}

function requestHeaders(options: RequestInit, replaceAuth = false): Headers {
  const headers = authHeaders(options.headers, { replaceAuth })
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return headers
}

export function isAuthRequiredError(error: unknown): error is ApiError {
  return error instanceof ApiError && (error.code === AUTH_REQUIRED_CODE || error.status === 401)
}

export async function promptForAuthToken(message?: string): Promise<string> {
  if (!pendingAuthPrompt) {
    pendingAuthPrompt = ElMessageBox.prompt(message || t('auth.message'), t('auth.title'), {
      confirmButtonText: t('auth.confirm'),
      cancelButtonText: t('common.cancel'),
      inputType: 'password',
      inputPlaceholder: t('auth.placeholder'),
      closeOnClickModal: false,
      inputValidator: value => String(value ?? '').trim() ? true : t('auth.required')
    })
      .then(({ value }) => {
        const token = String(value ?? '').trim()
        setAuthToken(token)
        return token
      })
      .catch(() => {
        throw new ApiError('AUTH_CANCELLED', t('auth.cancelled'), 401)
      })
      .finally(() => {
        pendingAuthPrompt = null
      })
  }
  return pendingAuthPrompt
}

async function isAuthChallenge(response: Response): Promise<boolean> {
  if (response.status !== 401) return false
  try {
    const data = await response.clone().json()
    const code = data?.error?.code
    return !code || code === AUTH_REQUIRED_CODE
  } catch {
    return true
  }
}

export async function fetchWithAuthRetry(
  input: RequestInfo | URL,
  options: RequestInit = {},
  makeHeaders: (replaceAuth: boolean) => Headers = replaceAuth => authHeaders(options.headers, { replaceAuth })
): Promise<Response> {
  const { headers: _headers, credentials, ...rest } = options
  let replaceAuth = false

  for (;;) {
    const response = await fetch(input, {
      ...rest,
      credentials: credentials ?? 'include',
      headers: makeHeaders(replaceAuth)
    })
    if (!(await isAuthChallenge(response))) return response
    setAuthToken(null)
    await promptForAuthToken()
    replaceAuth = true
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: _headers, credentials, ...rest } = options
  const response = await fetchWithAuthRetry(`${API_BASE}${path}`, {
    ...rest,
    credentials: credentials ?? 'include',
    headers: options.headers
  }, replaceAuth => requestHeaders(options, replaceAuth))
  const text = await response.text()
  const data = text ? JSON.parse(text) : null

  if (!response.ok) {
    const error = data?.error
    throw new ApiError(error?.code ?? 'HTTP_ERROR', error?.message ?? response.statusText, response.status)
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
  const { headers: _headers, credentials, ...rest } = options
  const response = await fetchWithAuthRetry(`${API_BASE}${path}`, {
    ...rest,
    credentials: credentials ?? 'include',
    headers: options.headers
  }, replaceAuth => requestHeaders(options, replaceAuth))

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
    throw new ApiError(code, message, response.status)
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
  const query = new URLSearchParams({ path })
  applyAuthQuery(query)
  return `${API_BASE}/api/files/download?${query.toString()}`
}

export function downloadSelectionUrl(paths: string[], options: { forceArchive?: boolean } = {}): string {
  if (paths.length === 1 && !options.forceArchive) return downloadUrl(paths[0])
  const query = new URLSearchParams()
  for (const path of paths) query.append('path', path)
  applyAuthQuery(query)
  return `${API_BASE}/api/files/download-selection?${query.toString()}`
}

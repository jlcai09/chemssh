/**
 * API Request Cache and Optimization Utilities
 * Provides caching, debouncing, and deduplication for API requests
 */

// Request cache with TTL
interface CacheEntry<T> {
  data: T
  timestamp: number
}

const requestCache = new Map<string, CacheEntry<any>>()
const DEFAULT_CACHE_TTL = 5000 // 5 seconds
const cacheGenerations = new Map<string, number>()
let globalCacheGeneration = 0

// Request deduplication
const pendingRequests = new Map<string, Promise<any>>()

/**
 * Cached request wrapper
 * Returns cached data if available and not expired, otherwise fetches new data
 */
export async function cachedRequest<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttl: number = DEFAULT_CACHE_TTL
): Promise<T> {
  const cached = requestCache.get(key)

  if (cached && Date.now() - cached.timestamp < ttl) {
    return cached.data
  }

  const generation = cacheGenerations.get(key) ?? globalCacheGeneration
  const data = await fetcher()
  if ((cacheGenerations.get(key) ?? globalCacheGeneration) === generation) {
    requestCache.set(key, { data, timestamp: Date.now() })
  }

  return data
}

/**
 * Clear cache and pending deduplicated request for a specific key or all requests
 */
export function clearCache(key?: string): void {
  if (key) {
    requestCache.delete(key)
    pendingRequests.delete(key)
    cacheGenerations.set(key, (cacheGenerations.get(key) ?? globalCacheGeneration) + 1)
  } else {
    requestCache.clear()
    pendingRequests.clear()
    cacheGenerations.clear()
    globalCacheGeneration += 1
  }
}

/**
 * Clear expired cache entries
 */
export function clearExpiredCache(ttl: number = DEFAULT_CACHE_TTL): void {
  const now = Date.now()
  for (const [key, entry] of requestCache.entries()) {
    if (now - entry.timestamp > ttl) {
      requestCache.delete(key)
    }
  }
}

/**
 * Deduplicate concurrent requests
 * If the same request is already pending, return the existing promise
 */
export async function dedupeRequest<T>(
  key: string,
  fetcher: () => Promise<T>
): Promise<T> {
  if (pendingRequests.has(key)) {
    return pendingRequests.get(key)!
  }

  const promise = fetcher()
  pendingRequests.set(key, promise)

  try {
    const result = await promise
    return result
  } finally {
    if (pendingRequests.get(key) === promise) {
      pendingRequests.delete(key)
    }
  }
}

/**
 * Debounce helper
 * Returns a debounced version of the provided function
 */
export function debounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return function (this: any, ...args: Parameters<T>) {
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
    }

    timeoutId = setTimeout(() => {
      fn.apply(this, args)
      timeoutId = null
    }, delay)
  }
}

/**
 * Throttle helper
 * Limits function calls to once per specified interval
 */
export function throttle<T extends (...args: any[]) => any>(
  fn: T,
  interval: number
): (...args: Parameters<T>) => void {
  let lastCall = 0
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return function (this: any, ...args: Parameters<T>) {
    const now = Date.now()

    if (now - lastCall >= interval) {
      lastCall = now
      fn.apply(this, args)
    } else {
      if (timeoutId !== null) {
        clearTimeout(timeoutId)
      }

      timeoutId = setTimeout(() => {
        lastCall = Date.now()
        fn.apply(this, args)
        timeoutId = null
      }, interval - (now - lastCall))
    }
  }
}

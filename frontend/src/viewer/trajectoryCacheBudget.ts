import type { AseFrame } from '../types/structure.ts'

export const VIEWER_TRAJECTORY_BUDGET = 256 * 1024 * 1024
export const SHARED_TRAJECTORY_BUDGET = 512 * 1024 * 1024

export interface CompactAseFrame {
  readonly compact: true
  frame_index: number
  n_atoms: number
  positions: Float32Array
  cell: Float32Array
  pbc: boolean[]
  tags?: Int32Array
  fixed_mask?: Uint8Array
  energy?: number | null
  fmax?: number | null
  symbols?: string[] | null
  numbers?: number[] | null
  shared_topology?: boolean
}

export type CachedTrajectoryFrame = AseFrame | CompactAseFrame

export function isCompactAseFrame(frame: CachedTrajectoryFrame): frame is CompactAseFrame {
  return (frame as CompactAseFrame).compact === true
}

const arrayBytes = (length: number) => 64 + length * 16
const stringsBytes = (values: string[] | null | undefined) =>
  arrayBytes(values?.length ?? 0) + (values?.reduce((sum, value) => sum + 40 + value.length * 2, 0) ?? 0)

// Include nested-array headers, slots and string storage; never serialize coordinates.
export function estimateAseFrameBytes(frame: AseFrame): number {
  const matrixBytes = (rows: number[][]) =>
    arrayBytes(rows.length) + rows.reduce((sum, row) => sum + arrayBytes(row.length), 0)
  return 352 + matrixBytes(frame.positions) + matrixBytes(frame.cell)
    + arrayBytes(frame.tags.length) + arrayBytes(frame.fixed_indices.length)
    + arrayBytes(frame.numbers?.length ?? 0) + stringsBytes(frame.symbols)
    + arrayBytes(frame.pbc.length)
}

export function estimateCompactAseFrameBytes(frame: CompactAseFrame): number {
  const topologyBytes = frame.shared_topology
    ? 0
    : arrayBytes(frame.numbers?.length ?? 0) + stringsBytes(frame.symbols)
  return 352
    + frame.positions.byteLength
    + frame.cell.byteLength
    + (frame.tags?.byteLength ?? 0)
    + (frame.fixed_mask?.byteLength ?? 0)
    + arrayBytes(frame.pbc.length)
    + topologyBytes
}

export function estimateCachedFrameBytes(frame: CachedTrajectoryFrame): number {
  return isCompactAseFrame(frame) ? estimateCompactAseFrameBytes(frame) : estimateAseFrameBytes(frame)
}

export function materializeAseFrame(
  frame: CachedTrajectoryFrame,
  fallbackSymbols?: string[] | null,
  fallbackNumbers?: number[] | null
): AseFrame {
  if (!isCompactAseFrame(frame)) return frame
  const nAtoms = frame.n_atoms
  const positions: number[][] = new Array(nAtoms)
  const tags: number[] = new Array(nAtoms)
  const fixedIndices: number[] = []
  for (let atomIndex = 0; atomIndex < nAtoms; atomIndex += 1) {
    const offset = atomIndex * 3
    positions[atomIndex] = [
      frame.positions[offset] ?? 0,
      frame.positions[offset + 1] ?? 0,
      frame.positions[offset + 2] ?? 0
    ]
    tags[atomIndex] = frame.tags?.[atomIndex] ?? 0
    if (frame.fixed_mask?.[atomIndex]) fixedIndices.push(atomIndex)
  }
  const cell: number[][] = [
    [frame.cell[0] ?? 0, frame.cell[1] ?? 0, frame.cell[2] ?? 0],
    [frame.cell[3] ?? 0, frame.cell[4] ?? 0, frame.cell[5] ?? 0],
    [frame.cell[6] ?? 0, frame.cell[7] ?? 0, frame.cell[8] ?? 0]
  ]
  return {
    frame_index: frame.frame_index,
    positions,
    cell,
    pbc: frame.pbc,
    tags,
    fixed_indices: fixedIndices,
    energy: frame.energy ?? null,
    fmax: frame.fmax ?? null,
    symbols: frame.symbols ?? fallbackSymbols ?? null,
    numbers: frame.numbers ?? fallbackNumbers ?? null
  }
}

export function estimateDenseTrajectoryBytes(nFrames: number, nAtoms: number, frame: AseFrame): number {
  if (!Number.isSafeInteger(nFrames) || !Number.isSafeInteger(nAtoms) || nFrames <= 0 || nAtoms <= 0) return Infinity
  const bytes = nFrames * (17 * nAtoms + 45) + 8 * 64
    + stringsBytes(frame.symbols) + arrayBytes(frame.numbers?.length ?? 0) + arrayBytes(frame.pbc.length)
  return Number.isSafeInteger(bytes) ? bytes : Infinity
}

// Start at the requested frame: providers may shrink a 32-frame request to one.
export function trajectoryChunkRequest(index: number, nFrames: number, maxCount = 32) {
  return { start: index, count: Math.max(0, Math.min(maxCount, nFrames - index)) }
}

export function nextTrajectoryChunkIndex(start: number, count: number, nFrames: number): number {
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(count) || start < 0 || count <= 0 || start + count > nFrames) {
    throw new Error('Invalid trajectory chunk range')
  }
  return start + count
}

interface ViewerCacheState {
  entries: Map<number, CacheEntry>
  denseBytes: number
  bytes: number
  disposed: boolean
  changed: () => void
}

interface CacheEntry {
  owner: ViewerCacheState
  frame: CachedTrajectoryFrame
  bytes: number
}

export class TrajectoryCacheBudget {
  private readonly viewerLimit: number
  private readonly totalLimit: number
  private readonly lru = new Map<CacheEntry, true>()
  private readonly viewers = new Set<ViewerCacheState>()
  private used = 0
  private reserved = 0

  constructor(viewerLimit = VIEWER_TRAJECTORY_BUDGET, totalLimit = SHARED_TRAJECTORY_BUDGET) {
    if (!Number.isSafeInteger(viewerLimit) || !Number.isSafeInteger(totalLimit) || viewerLimit < 0 || totalLimit < 0) {
      throw new Error('Invalid trajectory cache budget')
    }
    this.viewerLimit = viewerLimit
    this.totalLimit = totalLimit
  }

  get totalBytes() { return this.used }
  get viewerCount() { return this.viewers.size }
  get activeViewerCount() {
    let count = 0
    for (const viewer of this.viewers) {
      if (!viewer.disposed && viewer.bytes > 0) count += 1
    }
    return count
  }

  private singleViewerCap() {
    return Math.min(this.viewerLimit, this.totalLimit)
  }

  // Elastic per-viewer cap for non-evictable dense reservations: a sole active
  // trajectory viewer can use the full single-viewer cap (256 MiB), while
  // concurrent viewers elastically share the remaining 512 MiB shared pool.
  private denseLimitFor(state: ViewerCacheState) {
    const usedByOthers = Math.max(0, this.used - state.bytes)
    return Math.min(this.singleViewerCap(), Math.max(0, this.totalLimit - usedByOthers))
  }

  private remove(entry: CacheEntry) {
    this.lru.delete(entry)
    entry.owner.entries.delete(entry.frame.frame_index)
    entry.owner.bytes -= entry.bytes
    this.used -= entry.bytes
    entry.owner.changed()
  }

  registerViewer(changed: () => void = () => {}) {
    const state: ViewerCacheState = { entries: new Map(), denseBytes: 0, bytes: 0, disposed: false, changed }
    this.viewers.add(state)
    const releaseDense = () => {
      state.bytes -= state.denseBytes
      this.used -= state.denseBytes
      this.reserved -= state.denseBytes
      state.denseBytes = 0
    }
    const reset = () => {
      for (const entry of state.entries.values()) this.remove(entry)
      releaseDense()
      changed()
    }
    const denseLimit = () => (state.disposed ? 0 : this.denseLimitFor(state))
    return {
      get size() { return state.entries.size },
      get bytes() { return state.bytes },
      get denseBytes() { return state.denseBytes },
      get denseLimit() { return denseLimit() },
      reserveDense: (bytes: number) => {
        if (state.disposed || state.denseBytes || !Number.isSafeInteger(bytes) || bytes <= 0) return false
        const denseLimit = this.denseLimitFor(state)
        // Dense is optional: do not displace another viewer's working set for it.
        if (state.bytes + bytes > denseLimit || this.used + bytes > this.totalLimit) return false
        state.denseBytes = bytes
        state.bytes += bytes
        this.used += bytes
        this.reserved += bytes
        return true
      },
      releaseDense,
      has: (index: number) => state.entries.has(index),
      get: (index: number) => {
        const entry = state.entries.get(index)
        if (!entry) return undefined
        this.lru.delete(entry)
        this.lru.set(entry, true)
        return entry.frame
      },
      take: (index: number) => {
        const entry = state.entries.get(index)
        if (!entry) return undefined
        this.remove(entry)
        return entry.frame
      },
      set: (frame: CachedTrajectoryFrame) => {
        if (state.disposed) return false
        const bytes = estimateCachedFrameBytes(frame)
        const previous = state.entries.get(frame.frame_index)
        if (previous) this.remove(previous)
        const viewerCap = this.singleViewerCap()
        if (!Number.isSafeInteger(bytes) || bytes + state.denseBytes > viewerCap || bytes + this.reserved > this.totalLimit) return false
        for (const entry of this.lru.keys()) {
          if (state.bytes + bytes <= viewerCap) break
          if (entry.owner === state) this.remove(entry)
        }
        for (const entry of this.lru.keys()) {
          if (this.used + bytes <= this.totalLimit) break
          this.remove(entry)
        }
        const entry = { owner: state, frame, bytes }
        state.entries.set(frame.frame_index, entry)
        this.lru.set(entry, true)
        state.bytes += bytes
        this.used += bytes
        changed()
        return true
      },
      values: function* () {
        for (const entry of state.entries.values()) yield entry.frame
      },
      reset,
      dispose: () => {
        reset()
        state.disposed = true
        this.viewers.delete(state)
      }
    }
  }
}

export const trajectoryCacheBudget = new TrajectoryCacheBudget()

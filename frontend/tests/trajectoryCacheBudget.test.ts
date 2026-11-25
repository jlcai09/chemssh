import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AseFrame } from '../src/types/structure.ts'
import {
  estimateAseFrameBytes,
  estimateCompactAseFrameBytes,
  estimateDenseTrajectoryBytes,
  isCompactAseFrame,
  materializeAseFrame,
  nextTrajectoryChunkIndex,
  SHARED_TRAJECTORY_BUDGET,
  TrajectoryCacheBudget,
  trajectoryChunkRequest,
  VIEWER_TRAJECTORY_BUDGET,
  type CompactAseFrame
} from '../src/viewer/trajectoryCacheBudget.ts'

function frame(index = 0): AseFrame {
  return {
    frame_index: index,
    positions: [[index, 0, 0]],
    cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    tags: [0],
    fixed_indices: [],
    numbers: [1],
    symbols: ['H'],
    pbc: [false, false, false],
    energy: index
  }
}

const frameBytes = estimateAseFrameBytes(frame())

test('dense reservation is checked before allocation and released', () => {
  const budget = new TrajectoryCacheBudget(100, 150)
  const first = budget.registerViewer()
  const second = budget.registerViewer()
  assert.equal(first.reserveDense(101), false)
  assert.equal(first.reserveDense(100), true)
  assert.equal(second.reserveDense(51), false)
  assert.equal(second.reserveDense(50), true)
  assert.equal(budget.totalBytes, 150)
  first.releaseDense()
  assert.equal(budget.totalBytes, 50)
  assert.equal(first.reserveDense(100), true)
  first.dispose()
  second.dispose()
  assert.equal(budget.totalBytes, 0)
  assert.equal(budget.viewerCount, 0)
})

test('default limits reject large dense trajectories without allocating them', () => {
  assert.equal(VIEWER_TRAJECTORY_BUDGET, 256 * 1024 * 1024)
  assert.equal(SHARED_TRAJECTORY_BUDGET, 512 * 1024 * 1024)
  const budget = new TrajectoryCacheBudget()
  const cache = budget.registerViewer()
  assert.equal(cache.reserveDense(estimateDenseTrajectoryBytes(1000, 100000, frame())), false)
  const small = estimateDenseTrajectoryBytes(10, 1, frame())
  assert.ok(small >= 10 * (17 + 45))
  assert.equal(cache.reserveDense(small), true)
  cache.reset()
  assert.equal(budget.totalBytes, 0)
})

test('elastic budget lets a sole active trajectory viewer use 256 MiB while multiple viewers share 512 MiB via LRU', () => {
  const budget = new TrajectoryCacheBudget()
  const idleStatic = budget.registerViewer()
  const first = budget.registerViewer()
  const second = budget.registerViewer()
  const third = budget.registerViewer()

  // Idle static-structure viewer (0 bytes) does not shrink the sole trajectory viewer's cap.
  assert.equal(budget.activeViewerCount, 0)
  assert.equal(first.denseLimit, 256 * 1024 * 1024)
  assert.equal(first.reserveDense(200 * 1024 * 1024), true)
  assert.equal(budget.activeViewerCount, 1)

  // A second active trajectory viewer still gets up to 256 MiB (512 / 2).
  assert.equal(second.denseLimit, 256 * 1024 * 1024)
  assert.equal(second.reserveDense(150 * 1024 * 1024), true)
  assert.equal(budget.activeViewerCount, 2)

  // A third active trajectory viewer elastically gets the remaining shared pool (512 - 350 = 162 MiB).
  assert.equal(third.denseLimit, 162 * 1024 * 1024)
  assert.equal(third.reserveDense(170 * 1024 * 1024), false) // 200 + 150 + 170 > 512
  assert.equal(third.reserveDense(160 * 1024 * 1024), true)
  assert.equal(budget.activeViewerCount, 3)

  idleStatic.dispose()
  first.dispose()
  second.dispose()
  third.dispose()
  assert.equal(budget.totalBytes, 0)
  assert.equal(budget.activeViewerCount, 0)
})

test('multi-viewer LRU evicts across the shared pool when total usage exceeds totalLimit', () => {
  const budget = new TrajectoryCacheBudget(frameBytes * 3, frameBytes * 4)
  const first = budget.registerViewer()
  const second = budget.registerViewer()
  const third = budget.registerViewer()

  // Sole active viewer bursts up to its 3-frame cap.
  first.set(frame(0))
  first.set(frame(1))
  first.set(frame(2))
  assert.equal(first.size, 3)
  assert.equal(budget.totalBytes, frameBytes * 3)

  // Additional viewers fill the shared pool (4 frames), then evict oldest frames from first via LRU.
  second.set(frame(10))
  assert.equal(budget.totalBytes, frameBytes * 4)
  third.set(frame(20))
  assert.equal(first.has(0), false)
  assert.equal(first.size, 2)
  assert.equal(second.size, 1)
  assert.equal(third.size, 1)
  assert.equal(budget.totalBytes, frameBytes * 4)
})

test('LRU evicts by access order and replacement notifies even at constant size', () => {
  let revision = 0
  const budget = new TrajectoryCacheBudget(frameBytes * 2, frameBytes * 4)
  const cache = budget.registerViewer(() => { revision += 1 })
  cache.set(frame(0))
  cache.set(frame(1))
  cache.get(0)
  const previousRevision = revision
  cache.set(frame(2))
  assert.equal(cache.size, 2)
  assert.equal(cache.has(0), true)
  assert.equal(cache.has(1), false)
  assert.equal(cache.has(2), true)
  assert.ok(revision > previousRevision)
  assert.equal(cache.bytes, frameBytes * 2)
  assert.equal(budget.totalBytes, frameBytes * 2)
})

test('shared LRU counts every viewer and notifies an evicted viewer', () => {
  const budget = new TrajectoryCacheBudget(frameBytes * 2, frameBytes * 3)
  let firstRevision = 0
  const first = budget.registerViewer(() => { firstRevision += 1 })
  const second = budget.registerViewer()
  first.set(frame(0))
  first.set(frame(1))
  second.set(frame(2))
  first.get(0)
  const revision = firstRevision
  second.set(frame(3))
  assert.equal(first.has(1), false)
  assert.equal(first.has(0), true)
  assert.ok(firstRevision > revision)
  assert.equal(first.bytes + second.bytes, budget.totalBytes)
  assert.equal(budget.totalBytes, frameBytes * 3)
})

test('dense and detached frames share the same viewer and global budgets', () => {
  const budget = new TrajectoryCacheBudget(frameBytes * 2, frameBytes * 3)
  const dense = budget.registerViewer()
  const json = budget.registerViewer()
  assert.equal(dense.reserveDense(frameBytes * 2), true)
  assert.equal(dense.set(frame()), false)
  json.set(frame(0))
  json.set(frame(1))
  assert.equal(json.has(0), false)
  assert.equal(json.size, 1)
  assert.equal(budget.totalBytes, frameBytes * 3)
  dense.releaseDense()
  json.set(frame(2))
  assert.equal(json.size, 2)
})

test('optional dense reservation does not displace existing cached frames', () => {
  const budget = new TrajectoryCacheBudget(frameBytes * 2, frameBytes * 2)
  const first = budget.registerViewer()
  const second = budget.registerViewer()
  first.set(frame())
  assert.equal(second.reserveDense(frameBytes * 2), false)
  assert.equal(first.has(0), true)
})

test('oversized frame is not cached but remains displayable by reference', () => {
  const budget = new TrajectoryCacheBudget(frameBytes - 1, frameBytes - 1)
  const cache = budget.registerViewer()
  const currentFrame = frame(4)
  assert.equal(cache.set(currentFrame), false)
  assert.equal(cache.size, 0)
  assert.equal(budget.totalBytes, 0)
  cache.reset()
  assert.deepEqual(currentFrame.positions, [[4, 0, 0]])
})

test('taking the current frame out of the cache protects its reference from eviction', () => {
  const budget = new TrajectoryCacheBudget(frameBytes, frameBytes)
  const cache = budget.registerViewer()
  const target = frame(3)
  cache.set(target)
  const currentFrame = cache.take(3)
  assert.strictEqual(currentFrame, target)
  assert.equal(budget.totalBytes, 0)
  cache.set(frame(4))
  cache.set(frame(5))
  assert.deepEqual(currentFrame?.positions, [[3, 0, 0]])
})

test('reset clears all accounting and disposal unregisters the viewer', () => {
  const budget = new TrajectoryCacheBudget(frameBytes * 3, frameBytes * 6)
  const cache = budget.registerViewer()
  cache.reserveDense(frameBytes)
  cache.set(frame(0))
  cache.set(frame(1))
  cache.reset()
  assert.equal(cache.bytes, 0)
  assert.equal(cache.denseBytes, 0)
  assert.equal(cache.size, 0)
  assert.equal(budget.totalBytes, 0)
  cache.reset()
  assert.equal(cache.set(frame(3)), true)
  cache.dispose()
  cache.dispose()
  assert.equal(cache.set(frame(4)), false)
  assert.equal(cache.reserveDense(1), false)
  assert.equal(budget.totalBytes, 0)
  assert.equal(budget.viewerCount, 0)
})

test('estimates use actual array lengths, including optional metadata and ragged coordinates', () => {
  const baseline = frame()
  const larger = frame()
  larger.positions.push([1, 2, 3, 4])
  larger.cell.push([1, 2])
  larger.tags.push(1, 2)
  larger.fixed_indices.push(0)
  larger.numbers!.push(6, 8)
  larger.symbols!.push('Carbon', 'O')
  assert.ok(estimateAseFrameBytes(larger) > estimateAseFrameBytes(baseline) + 4 * 8)
  const withoutMetadata = { ...baseline, symbols: null, numbers: null }
  assert.ok(estimateAseFrameBytes(withoutMetadata) < frameBytes)
  assert.equal(estimateAseFrameBytes({ ...baseline, frame_index: 999, energy: null }), frameBytes)
  assert.equal(estimateDenseTrajectoryBytes(Number.MAX_SAFE_INTEGER, 100000, baseline), Infinity)
})

test('32 -> 1 responses include an unaligned target and advance by actual count', () => {
  const request = trajectoryChunkRequest(47, 100)
  assert.deepEqual(request, { start: 47, count: 32 })
  const response = { start: request.start, count: 1 }
  const next = nextTrajectoryChunkIndex(response.start, response.count, 100)
  assert.ok(47 >= response.start && 47 < next)
  assert.equal(next, 48)
  assert.deepEqual(trajectoryChunkRequest(next, 100), { start: 48, count: 32 })
  assert.deepEqual(trajectoryChunkRequest(99, 100), { start: 99, count: 1 })
  assert.equal(nextTrajectoryChunkIndex(99, 1, 100), 100)
  assert.throws(() => nextTrajectoryChunkIndex(47, 0, 100))
  assert.throws(() => nextTrajectoryChunkIndex(99, 2, 100))
})

test('compact typed-array frames use ~5x less budget than nested JS AseFrames and materialize accurately', () => {
  const nAtoms = 2000
  const jsFrame: AseFrame = {
    frame_index: 5,
    positions: Array.from({ length: nAtoms }, (_, i) => [i, i + 1, i + 2]),
    cell: [[10, 0, 0], [0, 10, 0], [0, 0, 10]],
    tags: Array.from({ length: nAtoms }, (_, i) => i % 3),
    fixed_indices: [1, 3],
    numbers: Array.from({ length: nAtoms }, () => 8),
    symbols: Array.from({ length: nAtoms }, () => 'O'),
    pbc: [true, true, true],
    energy: -123.5,
    fmax: 0.02
  }
  const positions = new Float32Array(nAtoms * 3)
  const tags = new Int32Array(nAtoms)
  const fixedMask = new Uint8Array(nAtoms)
  for (let i = 0; i < nAtoms; i += 1) {
    positions[i * 3] = i
    positions[i * 3 + 1] = i + 1
    positions[i * 3 + 2] = i + 2
    tags[i] = i % 3
  }
  fixedMask[1] = 1
  fixedMask[3] = 1
  const compact: CompactAseFrame = {
    compact: true,
    frame_index: 5,
    n_atoms: nAtoms,
    positions,
    cell: new Float32Array([10, 0, 0, 0, 10, 0, 0, 0, 10]),
    pbc: [true, true, true],
    tags,
    fixed_mask: fixedMask,
    energy: -123.5,
    fmax: 0.02,
    symbols: jsFrame.symbols,
    numbers: jsFrame.numbers,
    shared_topology: true
  }

  const jsBytes = estimateAseFrameBytes(jsFrame)
  const compactBytes = estimateCompactAseFrameBytes(compact)
  assert.ok(jsBytes > compactBytes * 4, `Expected JS frame (${jsBytes}) to be >4x compact (${compactBytes})`)
  assert.ok(Math.floor(VIEWER_TRAJECTORY_BUDGET / compactBytes) >= 1800)
  assert.equal(isCompactAseFrame(compact), true)
  assert.equal(isCompactAseFrame(jsFrame), false)

  const materialized = materializeAseFrame(compact)
  assert.equal(materialized.frame_index, 5)
  assert.deepEqual(materialized.positions[0], [0, 1, 2])
  assert.deepEqual(materialized.positions[nAtoms - 1], [nAtoms - 1, nAtoms, nAtoms + 1])
  assert.deepEqual(materialized.fixed_indices, [1, 3])
  assert.deepEqual(materialized.cell, [[10, 0, 0], [0, 10, 0], [0, 0, 10]])
  assert.equal(materialized.energy, -123.5)
  assert.equal(materialized.fmax, 0.02)
})

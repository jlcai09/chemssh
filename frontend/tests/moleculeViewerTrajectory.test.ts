import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import type { AseFrame, AseFrameChunk, AsePreviewResponse } from '../src/types/structure.ts'
import * as cacheHelpers from '../src/viewer/trajectoryCacheBudget.ts'

const require = createRequire(import.meta.url)
const ts = require('typescript')
const componentSource = readFileSync(new URL('../src/components/MoleculeViewer.vue', import.meta.url), 'utf8')
const apiSource = readFileSync(new URL('../src/api/structures.ts', import.meta.url), 'utf8')
const transpile = (source: string) => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText

function loadApi(http: Record<string, unknown> = {}) {
  const exports: Record<string, any> = {}
  runInNewContext(transpile(apiSource), {
    exports, URLSearchParams, AbortController, DataView, TextDecoder, Uint8Array, Float32Array, Int32Array,
    require: (name: string) => name === './http' ? http : { elementFromNumber: () => 'H' }
  })
  return exports
}
const actualApi = loadApi()

function frame(index: number): AseFrame {
  return { frame_index: index, positions: [[index, 1, 2]], cell: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    pbc: [true, true, true], tags: [index], fixed_indices: [], symbols: ['H'], numbers: [1], energy: index, fmax: index / 2 }
}

function preview(transport: 'json' | 'binary-available' = 'binary-available'): AsePreviewResponse {
  return { path: '/same.traj', name: 'same.traj', transport, n_frames: 100, n_atoms: 1,
    is_trajectory: true, topology_stable: true, initial_frame_index: 0, frame: frame(0) }
}

function chunk(index: number): AseFrameChunk {
  return {
    header: { version: 1, dtype: 'float32-le', int_dtype: 'int32-le', start: index, count: 1,
      n_frames_total: 100, n_atoms: 1, topology_stable: true, symbols: ['H'], numbers: [1], pbc: [true, true, true], arrays: {} },
    buffer: new ArrayBuffer(0), dataStart: 0, positions: new Float32Array([index, 1, 2]),
    cells: new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]), tags: new Int32Array([index]),
    energy: new Float32Array([index]), fmax: new Float32Array([index / 2])
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
const flush = () => new Promise<void>(resolve => setImmediate(resolve))

function viewerHarness(budget: cacheHelpers.TrajectoryCacheBudget, api: Record<string, any> = {}, initial = preview()) {
  let unmount = () => {}
  const props = { asePreview: initial, active: true, styleMode: 'stick', backgroundColor: '#fff' }
  const vue = {
    ref: (value: unknown) => ({ value }), shallowRef: (value: unknown) => ({ value }),
    reactive: (value: unknown) => value,
    computed: (fn: any) => ({ get value() { return typeof fn === 'function' ? fn() : fn.get() } }),
    defineComponent: (value: unknown) => value, h: () => null, nextTick: () => Promise.resolve(),
    watch: () => {}, watchEffect: () => {}, onMounted: () => {}, onBeforeUnmount: (fn: () => void) => { unmount = fn }
  }
  const script = componentSource.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)![1]
  const context: Record<string, any> = {
    exports: {}, console, AbortController, DOMException, Float32Array, Int32Array, Uint8Array,
    defineProps: () => props, withDefaults: (value: unknown) => value, defineEmits: () => () => {},
    window: { setTimeout: () => 1, clearTimeout: () => {}, cancelAnimationFrame: () => {} },
    require: (name: string) => {
      if (name === 'vue') return vue
      if (name === '../api/structures') return { ...actualApi, ...api }
      if (name === '../viewer/trajectoryCacheBudget') return { ...cacheHelpers, trajectoryCacheBudget: budget }
      if (name === '../i18n') return { t: (value: string) => value }
      return {}
    }
  }
  runInNewContext(transpile(`${script}\n;(globalThis as any).viewer = {
    resetAseState, setFrame, pauseTrajectoryPreload, streamBinaryTrajectoryFrames, closeActiveEventSource,
    writeChunkToStore, frameCache,
    get current() { return currentFrame.value }, get store() { return trajectoryStore },
    get revision() { return cacheRevision.value }, get count() { return cachedFrameCount.value },
    get status() { return cacheStatus.value }, get onDemand() { return isOnDemandTrajectory.value },
    get preloadVersion() { return preloadVersion },
    setRenderer(value: any) { chemsshViewer = value }
  }`), context)
  return { viewer: context.viewer, props, unmount: () => unmount() }
}

test('fixed binary without dense reads the unaligned target as compact frame and prefetches bidirectionally', async () => {
  const budget = new cacheHelpers.TrajectoryCacheBudget(0, 0)
  const requests: Array<{ start: number, count: number, signal: AbortSignal }> = []
  const harness = viewerHarness(budget, {
    readStructureFrameChunk: async (_source: unknown, _path: string, start: number, count: number, _format: unknown, _force: boolean, options: { signal: AbortSignal }) => {
      requests.push({ start, count, signal: options.signal })
      return chunk(start)
    }
  })
  harness.props.active = false
  harness.viewer.resetAseState()
  harness.props.active = true
  await harness.viewer.setFrame(47)
  await flush()
  assert.equal(harness.viewer.store, null)
  assert.equal(harness.viewer.onDemand, true)
  assert.equal(harness.viewer.status, 'viewer.onDemandCachedFrames')
  assert.equal(harness.viewer.current.frame_index, 47)
  assert.equal(cacheHelpers.isCompactAseFrame(harness.viewer.current), true)
  assert.equal((harness.viewer.current.positions as Float32Array)[0], 47)
  assert.equal(harness.viewer.frameCache.size, 0)
  assert.equal(budget.totalBytes, 0)
  assert.deepEqual(
    requests.map(({ start, count }) => ({ start, count })),
    [{ start: 47, count: 32 }, { start: 48, count: 32 }, { start: 15, count: 32 }]
  )
  harness.unmount()
})

test('JSON also advances by actual count and prefetches bidirectionally without scanning the whole trajectory', async () => {
  const requests: number[] = []
  const harness = viewerHarness(new cacheHelpers.TrajectoryCacheBudget(0, 0), {
    readStructureFrameJsonChunk: async (_source: unknown, _path: string, start: number) => {
      requests.push(start)
      return { start, count: 1, frames: [frame(start)] }
    }
  }, preview('json'))
  await harness.viewer.setFrame(47)
  await flush()
  assert.deepEqual(requests, [47, 48, 15])
  assert.equal(harness.viewer.current.positions[0][0], 47)
  harness.unmount()
})

test('on-demand trajectory starting at the last frame prefetches the preceding chunk backward', async () => {
  const budget = new cacheHelpers.TrajectoryCacheBudget(20000, 20000)
  const requests: Array<{ start: number, count: number }> = []
  const lastPreview: AsePreviewResponse = {
    ...preview(),
    n_frames: 1000,
    initial_frame_index: 999,
    frame: frame(999)
  }
  const harness = viewerHarness(budget, {
    readStructureFrameChunk: async (_source: unknown, _path: string, start: number, count: number) => {
      requests.push({ start, count })
      const positions = new Float32Array(count * 3)
      const cells = new Float32Array(count * 9)
      const tags = new Int32Array(count)
      const energy = new Float32Array(count)
      const fmax = new Float32Array(count)
      for (let i = 0; i < count; i += 1) {
        positions[i * 3] = start + i
        cells[i * 9] = 1
        cells[i * 9 + 4] = 1
        cells[i * 9 + 8] = 1
        tags[i] = start + i
        energy[i] = start + i
        fmax[i] = (start + i) / 2
      }
      return {
        header: {
          version: 1, dtype: 'float32-le', int_dtype: 'int32-le', start, count,
          n_frames_total: 1000, n_atoms: 1, topology_stable: true,
          symbols: ['H'], numbers: [1], pbc: [true, true, true], arrays: {}
        },
        buffer: new ArrayBuffer(0), dataStart: 0, positions, cells, tags, energy, fmax
      }
    }
  }, lastPreview)
  // Dense reservation for 1000 frames of 1 atom (~62KB) exceeds 20KB budget -> on-demand mode.
  harness.viewer.resetAseState()
  await flush()
  assert.equal(harness.viewer.store, null)
  assert.equal(harness.viewer.onDemand, true)
  assert.equal(harness.viewer.status, 'viewer.onDemandCachedFrames')
  assert.deepEqual(requests, [{ start: 967, count: 32 }])
  assert.equal(harness.viewer.frameCache.has(998), true)
  assert.equal(harness.viewer.frameCache.has(967), true)
  // Stepping backward within the 31-frame runway should hit cache with zero extra requests.
  await harness.viewer.setFrame(998)
  await flush()
  assert.equal(requests.length, 1)
  assert.equal(harness.viewer.current.frame_index, 998)
  assert.equal(cacheHelpers.isCompactAseFrame(harness.viewer.current), true)
  harness.unmount()
})

test('new foreground aborts old foreground and same-path reset prevents stale cache writes', async () => {
  const requests: Array<{ start: number, signal: AbortSignal, result: ReturnType<typeof deferred<AseFrameChunk>> }> = []
  const harness = viewerHarness(new cacheHelpers.TrajectoryCacheBudget(3000, 3000), {
    readStructureFrameChunk: (_source: unknown, _path: string, start: number, _count: number, _format: unknown, _force: boolean, options: { signal: AbortSignal }) => {
      const result = deferred<AseFrameChunk>()
      requests.push({ start, signal: options.signal, result })
      return result.promise
    }
  })
  const first = harness.viewer.setFrame(47)
  const second = harness.viewer.setFrame(60)
  assert.equal(requests[0].signal.aborted, true)
  requests[0].result.resolve(chunk(47))
  await first
  assert.equal(harness.viewer.current.frame_index, 0)
  harness.props.asePreview = preview()
  harness.props.active = false
  harness.viewer.resetAseState()
  assert.equal(requests[1].signal.aborted, true)
  harness.props.active = true
  requests[1].result.resolve(chunk(60))
  await second
  assert.equal(harness.viewer.current.frame_index, 0)
  assert.equal(harness.viewer.frameCache.has(60), false)
  harness.unmount()
})

test('unmount aborts background neighbor reads and unregisters all bytes', async () => {
  let backgroundSignal: AbortSignal | undefined
  const background = deferred<AseFrameChunk>()
  const budget = new cacheHelpers.TrajectoryCacheBudget(0, 0)
  const harness = viewerHarness(budget, {
    readStructureFrameChunk: async (_source: unknown, _path: string, start: number, _count: number, _format: unknown, _force: boolean, options: { signal: AbortSignal }) => {
      if (start === 47) return chunk(start)
      backgroundSignal = options.signal
      return background.promise
    }
  })
  await harness.viewer.setFrame(47)
  assert.ok(backgroundSignal)
  harness.unmount()
  assert.equal(backgroundSignal.aborted, true)
  background.resolve(chunk(48))
  await flush()
  assert.equal(budget.viewerCount, 0)
  assert.equal(budget.totalBytes, 0)
})

test('dense applies full coordinates and unrelated chunks do not rerender the current frame', async () => {
  const budget = new cacheHelpers.TrajectoryCacheBudget()
  const harness = viewerHarness(budget)
  harness.props.active = false
  harness.viewer.resetAseState()
  harness.props.active = true
  assert.ok(harness.viewer.store)
  const rendered: number[] = []
  harness.viewer.setRenderer({ setFrame: (index: number) => rendered.push(index), dispose: () => {} })
  harness.viewer.writeChunkToStore(chunk(47))
  assert.deepEqual(rendered, [])
  await harness.viewer.setFrame(47)
  assert.equal(harness.viewer.current.positions[0][0], 47)
  assert.equal(harness.viewer.current.tags[0], 47)
  assert.equal(harness.viewer.current.energy, 47)
  assert.deepEqual(rendered, [47])
  harness.viewer.writeChunkToStore(chunk(48))
  assert.deepEqual(rendered, [47])
  harness.unmount()
  assert.equal(budget.totalBytes, 0)
})

test('SSE done, error, explicit close, reset and unmount all settle without polling', async () => {
  for (const reason of ['done', 'error', 'close', 'reset', 'unmount']) {
    let callbacks: { done: () => void, error: () => void } | undefined
    let closes = 0
    const harness = viewerHarness(new cacheHelpers.TrajectoryCacheBudget(), {
      streamStructureFrames: (_source: unknown, _path: string, _chunk: unknown, done: () => void, error: () => void) => {
        callbacks = { done, error }
        return { close: () => { closes += 1 } }
      }
    })
    harness.props.active = false
    harness.viewer.resetAseState()
    harness.props.active = true
    const pending = harness.viewer.streamBinaryTrajectoryFrames(harness.viewer.preloadVersion, harness.props.asePreview)
    assert.ok(callbacks)
    if (reason === 'done') callbacks.done()
    else if (reason === 'error') callbacks.error()
    else if (reason === 'reset') { harness.props.active = false; harness.viewer.resetAseState() }
    else if (reason === 'unmount') harness.unmount()
    else harness.viewer.closeActiveEventSource()
    await pending
    callbacks.done()
    assert.equal(closes, 1)
    if (reason !== 'unmount') harness.unmount()
  }
})

test('single, JSON and binary API wrappers forward optional AbortSignal', async () => {
  const signals: AbortSignal[] = []
  const api = loadApi({
    request: async (_url: string, options: { signal: AbortSignal }) => { signals.push(options.signal); return frame(0) },
    authHeaders: () => ({}), API_BASE: '',
    fetchWithAuthRetry: async (_url: string, options: { signal: AbortSignal }) => {
      signals.push(options.signal)
      throw new DOMException('Cancelled', 'AbortError')
    }
  })
  const signal = new AbortController().signal
  await api.readStructureFrame(null, '/test', 0, null, false, { signal })
  await api.readStructureFrameJsonChunk(null, '/test', 0, 32, null, false, { signal })
  await assert.rejects(api.readStructureFrameChunk(null, '/test', 0, 32, null, false, { signal }))
  await api.readAseFrame('/test', 0, null, false, { signal })
  await api.readAseFrameJsonChunk('/test', 0, 32, null, false, { signal })
  await assert.rejects(api.readAseFrameChunk('/test', 0, 32, null, false, { signal }))
  assert.equal(signals.length, 6)
  assert.ok(signals.every(value => value === signal))
})

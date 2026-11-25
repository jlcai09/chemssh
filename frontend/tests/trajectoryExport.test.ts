import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import { writeTrajectoryExport } from '../src/utils/structureExport.ts'

const require = createRequire(import.meta.url)
const ts = require('typescript')
const exportSource = readFileSync(new URL('../src/utils/structureExport.ts', import.meta.url), 'utf8')

function browserExportHarness(window: Record<string, unknown>, encoder = TextEncoder) {
  const exports: Record<string, any> = {}
  let downloads = 0
  let objectUrls = 0
  let revoked = 0
  runInNewContext(ts.transpileModule(exportSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText, {
    exports, Blob, TextEncoder: encoder,
    window: { setTimeout: (callback: () => void) => callback(), ...window },
    document: { createElement: () => ({ click: () => { downloads += 1 } }) },
    URL: {
      createObjectURL: () => { objectUrls += 1; return 'blob:test' },
      revokeObjectURL: () => { revoked += 1 }
    }
  })
  return { api: exports, get downloads() { return downloads }, get objectUrls() { return objectUrls }, get revoked() { return revoked } }
}

function frame(index: number) {
  return {
    frame_index: index,
    symbols: ['H'], numbers: [1], positions: [[index, 0, 0]],
    cell: [[2, 0, 0], [0, 2, 0], [0, 0, 2]], pbc: [true, true, true],
    tags: [0], fixed_indices: [0], energy: -index, fmax: null
  }
}

test('XYZ exports sequentially without retaining all frames and preserves constraints', async () => {
  let produced = 0
  const chunks: string[] = []
  async function* frames() {
    for (let index = 0; index < 4; index += 1) {
      assert.equal(chunks.length, index)
      produced += 1
      yield frame(index)
    }
  }
  await writeTrajectoryExport(frames(), 'xyz', 'movie.xyz', async text => { chunks.push(text) })
  assert.equal(produced, 4)
  assert.equal(chunks.length, 4)
  assert.ok(chunks[3].includes('H  3.00000000  0.00000000  0.00000000  F'))
  assert.ok(chunks[0].includes('move_mask:L:1'))
})

test('Arc writes one archive header and all frames', async () => {
  async function* frames() { yield frame(0); yield frame(1) }
  const chunks: string[] = []
  await writeTrajectoryExport(frames(), 'arc', 'movie.arc', async text => { chunks.push(text) })
  const text = chunks.join('')
  assert.equal(text.split('!BIOSYM archive 3').length - 1, 1)
  assert.equal(text.split('PBC=ON').length - 1, 1)
  assert.equal(text.split('!DATE').length - 1, 2)
  assert.ok(text.includes('1.00000000'))
})

test('failed frame load aborts export instead of skipping the frame', async () => {
  let writes = 0
  async function* frames() {
    yield frame(0)
    throw new Error('frame unavailable')
  }
  await assert.rejects(writeTrajectoryExport(frames(), 'xyz', 'movie.xyz', async () => { writes += 1 }), /frame unavailable/)
  assert.equal(writes, 1)
})

test('cancellation stops iteration and closes the generator', async () => {
  const controller = new AbortController()
  let closed = false
  let writes = 0
  async function* frames() {
    try { yield frame(0); yield frame(1) } finally { closed = true }
  }
  await assert.rejects(writeTrajectoryExport(frames(), 'xyz', 'movie.xyz', async () => {
    writes += 1
    controller.abort()
  }, controller.signal), { name: 'AbortError' })
  assert.equal(writes, 1)
  assert.equal(closed, true)
})

test('file writer aborts on frame failure without committing an incomplete file', async () => {
  let writes = 0
  let closes = 0
  let aborts = 0
  const harness = browserExportHarness({ showSaveFilePicker: async () => ({
    createWritable: async () => ({
      write: async () => { writes += 1 },
      close: async () => { closes += 1 },
      abort: async () => { aborts += 1 }
    })
  }) })
  async function* frames() { yield frame(0); throw new Error('frame unavailable') }
  await assert.rejects(harness.api.downloadTrajectoryExport(frames(), 'xyz', 'movie.xyz'), /frame unavailable/)
  assert.equal(writes, 1)
  assert.equal(closes, 0)
  assert.equal(aborts, 1)
  assert.equal(harness.downloads, 0)
})

test('cancellation during file writing aborts the writer and closes iteration', async () => {
  const controller = new AbortController()
  let closed = false
  let closes = 0
  let aborts = 0
  const harness = browserExportHarness({ showSaveFilePicker: async () => ({
    createWritable: async () => ({
      write: async () => { controller.abort() },
      close: async () => { closes += 1 },
      abort: async () => { aborts += 1 }
    })
  }) })
  async function* frames() {
    try { yield frame(0); yield frame(1) } finally { closed = true }
  }
  await assert.rejects(harness.api.downloadTrajectoryExport(frames(), 'xyz', 'movie.xyz', controller.signal), { name: 'AbortError' })
  assert.equal(closed, true)
  assert.equal(closes, 0)
  assert.equal(aborts, 1)
})

test('fallback download rejects a buffer above 64 MiB before creating a download', async () => {
  class LargeEncoder extends TextEncoder {
    override encode() { return new Uint8Array(33 * 1024 * 1024) }
  }
  const harness = browserExportHarness({}, LargeEncoder)
  let closed = false
  async function* frames() {
    try { yield frame(0); yield frame(1); yield frame(2) } finally { closed = true }
  }
  await assert.rejects(harness.api.downloadTrajectoryExport(frames(), 'xyz', 'movie.xyz'), harness.api.TrajectoryExportTooLargeError)
  assert.equal(closed, true)
  assert.equal(harness.objectUrls, 0)
  assert.equal(harness.downloads, 0)
})

test('fallback download creates and releases one complete file', async () => {
  const harness = browserExportHarness({})
  async function* frames() { yield frame(0); yield frame(1) }
  await harness.api.downloadTrajectoryExport(frames(), 'xyz', 'movie.xyz')
  assert.equal(harness.objectUrls, 1)
  assert.equal(harness.downloads, 1)
  assert.equal(harness.revoked, 1)
})

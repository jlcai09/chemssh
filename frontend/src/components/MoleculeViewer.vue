<template>
  <div class="molecule-viewer">
    <div class="viewer-toolbar">
      <el-radio-group v-model="selectedStyle" size="small">
        <el-radio-button label="stick">{{ t('viewer.styleStick') }}</el-radio-button>
        <el-radio-button label="sphere">{{ t('viewer.styleSphere') }}</el-radio-button>
        <el-radio-button label="line">{{ t('viewer.styleLine') }}</el-radio-button>
      </el-radio-group>

      <div v-if="asePreview?.is_trajectory" class="trajectory-controls">
        <span class="frame-label">{{ t('viewer.frame') }}</span>
        <el-input-number
          v-model="frameInput"
          class="frame-number"
          size="small"
          :min="0"
          :max="asePreview.n_frames - 1"
          :step="1"
          controls-position="right"
          @change="scheduleFrameChange"
        />
        <span class="frame-total">/ {{ asePreview.n_frames - 1 }}</span>
        <el-slider
          v-model="frameInput"
          class="frame-slider"
          :min="0"
          :max="asePreview.n_frames - 1"
          :show-tooltip="false"
          size="small"
          @input="scheduleFrameChange"
        />
      </div>

      <div class="toolbar-spacer" />

      <el-tooltip :content="t('toolbar.refresh')" placement="bottom">
        <el-button :icon="Refresh" circle size="small" @click="refreshStructure" />
      </el-tooltip>
      <el-tooltip :content="t('viewer.exportScreenshot')" placement="bottom">
        <el-button :icon="Download" circle size="small" @click="exportPng" />
      </el-tooltip>
    </div>
    <div class="viewer-stage">
      <div ref="container" class="viewer-canvas" />
      <div v-if="asePreview" class="viewer-floating-tools">
        <el-popover trigger="click" placement="right-start" :width="260">
          <template #reference>
            <el-button :aria-label="t('viewer.bondSettings')" :icon="Connection" circle size="small" />
          </template>
          <div class="bond-settings-panel">
            <div class="bond-settings-header">
              <span>{{ t('viewer.bondScale') }}</span>
              <strong>{{ bondScale.toFixed(2) }}</strong>
            </div>
            <el-slider
              v-model="bondScale"
              class="bond-settings-slider"
              :min="0.6"
              :max="2"
              :step="0.01"
              size="small"
            />
            <div class="bond-settings-actions">
              <el-button size="small" text @click="resetBondScale">{{ t('viewer.resetBondScale') }}</el-button>
            </div>
          </div>
        </el-popover>

        <el-popover trigger="click" placement="right-start" :width="220">
          <template #reference>
            <el-button :aria-label="t('viewer.displaySettings')" :icon="View" circle size="small" />
          </template>
          <div class="display-settings-panel">
            <el-checkbox v-model="showAtomIndex">{{ t('viewer.atomIndex') }}</el-checkbox>
            <el-checkbox v-model="showAtomTag">{{ t('viewer.atomTag') }}</el-checkbox>
          </div>
        </el-popover>

        <el-tooltip :content="t('viewer.resetView')" placement="right">
          <el-button :aria-label="t('viewer.resetView')" :icon="ResetViewIcon" circle size="small" @click="resetView" />
        </el-tooltip>
      </div>
      <div v-if="asePreview" class="viewer-overlay">
        <span>Frame: {{ currentFrame.frame_index + 1 }} / {{ asePreview.n_frames }}</span>
        <span>Energy: {{ formatMetric(currentFrame.energy, ' eV') }}</span>
        <span>Fmax: {{ formatMetric(currentFrame.fmax, ' eV/A') }}</span>
        <span v-if="cacheStatus">{{ cacheStatus }}</span>
      </div>
      <div v-if="frameLoading" class="viewer-loading">
        <el-skeleton :rows="2" animated />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Connection, Download, Refresh, View } from '@element-plus/icons-vue'
import { readAseFrame, readAseFrameChunk } from '../api/structures'
import { t } from '../i18n'
import type { AseFrame, AseFrameChunk, AsePreviewResponse } from '../types/structure'
import type { StructureFrame, TrajectoryStore, ViewerStyleMode } from '../viewer'

type StyleMode = ViewerStyleMode
type ViewerModule = typeof import('../viewer')
type ChemwebViewerInstance = InstanceType<ViewerModule['ChemwebStructureViewer']>

const props = withDefaults(
  defineProps<{
    asePreview?: AsePreviewResponse | null
    styleMode?: StyleMode
    backgroundColor?: string
  }>(),
  {
    asePreview: null,
    styleMode: 'stick',
    backgroundColor: '#ffffff'
  }
)

const emit = defineEmits<{
  refresh: []
}>()

const ResetViewIcon = defineComponent({
  name: 'ResetViewIcon',
  setup() {
    return () =>
      h('svg', { viewBox: '0 0 1024 1024', xmlns: 'http://www.w3.org/2000/svg' }, [
        h('path', {
          fill: 'currentColor',
          d: 'M512 104 208 256v312l304 152 304-152V256L512 104zm0 72 180 90-180 90-180-90 180-90zM272 327l208 104v201L272 528V327zm272 305V431l208-104v201L544 632z'
        }),
        h('path', {
          fill: 'currentColor',
          d: 'M250 721a318 318 0 0 0 431 80l-48-33 147-54 8 156-50-34a382 382 0 0 1-546-88l58-27zM774 303A318 318 0 0 0 343 223l48 33-147 54-8-156 50 34a382 382 0 0 1 546 88l-58 27z'
        })
      ])
  }
})

const container = ref<HTMLElement | null>(null)
const selectedStyle = ref<StyleMode>(props.styleMode)
const bondScale = ref(1.25)
const showAtomIndex = ref(false)
const showAtomTag = ref(false)
const frameInput = ref(0)
const frameLoading = ref(false)
const cachedFrameCount = ref(0)
const currentFrame = ref<AseFrame>(props.asePreview?.frame ?? emptyFrame())

let chemwebViewer: ChemwebViewerInstance | null = null
let resizeObserver: ResizeObserver | null = null
let renderVersion = 0
let scheduledFrame: number | null = null
let frameRequestHandle = 0
let preloadVersion = 0
let trajectoryStore: TrajectoryStore | null = null
let viewerModulePromise: Promise<ViewerModule> | null = null

const jsonFrameCache = new Map<number, AseFrame>()
const pendingChunks = new Map<number, Promise<void>>()
const chunkSize = 64
const maxLocalTrajectoryBytes = 512 * 1024 * 1024

const cacheStatus = computed(() => {
  if (!props.asePreview?.is_trajectory) return ''
  if (!canPreloadTrajectory(props.asePreview)) return 'Frames: streaming'
  if (cachedFrameCount.value >= props.asePreview.n_frames) return ''
  return `Frames: ${cachedFrameCount.value} / ${props.asePreview.n_frames}`
})

function emptyFrame(): AseFrame {
  return {
    frame_index: 0,
    positions: [],
    cell: [],
    pbc: [false, false, false],
    tags: [],
    fixed_indices: [],
    energy: null,
    fmax: null,
    symbols: [],
    numbers: []
  }
}

function loadChemwebViewer() {
  viewerModulePromise ??= import('../viewer')
  return viewerModulePromise
}

function viewerStyleMode(): ViewerStyleMode {
  return selectedStyle.value
}

function viewerStyle() {
  const mode = viewerStyleMode()
  return {
    mode,
    atomScale: mode === 'sphere' ? 0.52 : mode === 'line' ? 0.2 : 0.42,
    bondRadius: mode === 'line' ? 0.012 : 0.065,
    bondScale: bondScale.value,
    backgroundColor: props.backgroundColor,
    showCell: true
  }
}

async function renderStructure(keepView = false) {
  const version = ++renderVersion
  await nextTick()
  if (!container.value || version !== renderVersion) return

  if (!props.asePreview) {
    disposeChemwebViewer()
    container.value.innerHTML = ''
    return
  }

  try {
    await renderChemwebStructure(keepView)
  } catch (error) {
    console.warn('Chemweb viewer failed.', error)
    disposeChemwebViewer()
  }
}

async function renderChemwebStructure(keepView = false) {
  if (!container.value || !props.asePreview) return
  if (!chemwebViewer) {
    container.value.innerHTML = ''
    const { ChemwebStructureViewer } = await loadChemwebViewer()
    chemwebViewer = new ChemwebStructureViewer(container.value, {
      backgroundColor: props.backgroundColor,
      style: viewerStyle(),
      labelOptions: {
        showAtomIndex: showAtomIndex.value,
        showAtomTag: showAtomTag.value
      }
    })
  }

  chemwebViewer.setStyle(viewerStyle())
  chemwebViewer.setLabelOptions({
    showAtomIndex: showAtomIndex.value,
    showAtomTag: showAtomTag.value
  })

  if (trajectoryStore && props.asePreview.is_trajectory) {
    chemwebViewer.setTrajectory(trajectoryStore, {
      keepView,
      initialFrameIndex: currentFrame.value.frame_index
    })
    chemwebViewer.setFrame(currentFrame.value.frame_index)
    return
  }

  chemwebViewer.setStructure(frameToViewerFrame(currentFrame.value), { keepView })
}

function frameToViewerFrame(frame: AseFrame): StructureFrame {
  return {
    frameIndex: frame.frame_index,
    positions: frame.positions,
    cell: frame.cell,
    pbc: frame.pbc,
    tags: frame.tags,
    fixedIndices: frame.fixed_indices,
    energy: frame.energy,
    fmax: frame.fmax,
    symbols: frame.symbols ?? props.asePreview?.frame.symbols ?? [],
    numbers: frame.numbers ?? props.asePreview?.frame.numbers ?? []
  }
}

function resizeViewer() {
  chemwebViewer?.resize()
}

function resetView() {
  chemwebViewer?.resetView()
}

function refreshStructure() {
  emit('refresh')
}

function exportPng() {
  const uri = chemwebViewer?.screenshot()
  if (!uri) return
  const link = document.createElement('a')
  link.href = uri
  link.download = `structure-${Date.now()}.png`
  link.click()
}

function formatMetric(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A'
  return `${value.toFixed(6)}${unit}`
}

function scheduleFrameChange() {
  if (!props.asePreview) return
  scheduledFrame = clampFrameIndex(Number(frameInput.value))
  if (frameRequestHandle) return
  frameRequestHandle = window.requestAnimationFrame(() => {
    frameRequestHandle = 0
    if (scheduledFrame === null) return
    void setFrame(scheduledFrame)
  })
}

function resetBondScale() {
  bondScale.value = 1.25
}

async function setFrame(index: number) {
  const preview = props.asePreview
  if (!preview) return
  const target = clampFrameIndex(index)
  if (target === currentFrame.value.frame_index) return

  if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, target)) {
    applyTrajectoryFrame(target)
    return
  }

  if (preview.is_trajectory && canPreloadTrajectory(preview) && trajectoryStore) {
    frameLoading.value = true
    try {
      await ensureChunk(target)
      if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, target)) {
        applyTrajectoryFrame(target)
        return
      }
    } finally {
      frameLoading.value = false
    }
  }

  const cached = jsonFrameCache.get(target)
  if (cached) {
    currentFrame.value = cached
    frameInput.value = target
    await renderStructure(true)
    return
  }

  frameLoading.value = true
  try {
    const frame = await loadFrame(target)
    currentFrame.value = frame
    jsonFrameCache.set(target, frame)
    frameInput.value = target
    await renderStructure(true)
  } finally {
    frameLoading.value = false
  }
}

function applyTrajectoryFrame(index: number) {
  if (!trajectoryStore) return
  const energy = trajectoryStore.energy?.[index]
  const fmax = trajectoryStore.fmax?.[index]
  currentFrame.value = {
    ...currentFrame.value,
    frame_index: index,
    energy: energy === undefined || Number.isNaN(energy) ? null : energy,
    fmax: fmax === undefined || Number.isNaN(fmax) ? null : fmax
  }
  frameInput.value = index
  chemwebViewer?.setFrame(index)
}

async function loadFrame(index: number) {
  if (!props.asePreview) return emptyFrame()
  if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, index)) {
    return frameFromStore(index) ?? emptyFrame()
  }
  return readAseFrame(
    props.asePreview.path,
    index,
    props.asePreview.format,
    props.asePreview.size_limit_overridden === true
  )
}

function canPreloadTrajectory(preview: AsePreviewResponse) {
  return (
    preview.transport === 'binary-available' &&
    preview.topology_stable &&
    estimateTrajectoryBytes(preview) <= maxLocalTrajectoryBytes
  )
}

function estimateTrajectoryBytes(preview: AsePreviewResponse) {
  const atomFrames = preview.n_atoms * preview.n_frames
  return atomFrames * (3 * Float32Array.BYTES_PER_ELEMENT + Int32Array.BYTES_PER_ELEMENT + Uint8Array.BYTES_PER_ELEMENT) +
    preview.n_frames * (9 * Float32Array.BYTES_PER_ELEMENT + 2 * Float32Array.BYTES_PER_ELEMENT)
}

async function preloadTrajectoryFrames(version: number) {
  const preview = props.asePreview
  if (!preview?.is_trajectory || !canPreloadTrajectory(preview) || !trajectoryStore) return

  const starts = chunkStartsForFullTrajectory(preview)
  const initialStart = Math.floor(preview.initial_frame_index / chunkSize) * chunkSize
  starts.sort((left, right) => {
    if (left === initialStart) return -1
    if (right === initialStart) return 1
    return left - right
  })

  for (const start of starts) {
    if (version !== preloadVersion || !props.asePreview || props.asePreview.path !== preview.path) return
    try {
      await ensureChunkStart(start, preview)
    } catch {
      return
    }
  }
}

function chunkStartsForFullTrajectory(preview: AsePreviewResponse) {
  const starts: number[] = []
  for (let start = 0; start < preview.n_frames; start += chunkSize) {
    starts.push(start)
  }
  return starts
}

async function ensureChunk(index: number) {
  if (!props.asePreview) return
  const chunkStart = Math.floor(index / chunkSize) * chunkSize
  await ensureChunkStart(chunkStart, props.asePreview)
}

async function ensureChunkStart(chunkStart: number, preview: AsePreviewResponse) {
  if (trajectoryStore && isChunkAvailable(trajectoryStore, chunkStart, preview)) return
  const pending = pendingChunks.get(chunkStart)
  if (pending) {
    await pending
    return
  }
  const request = readAseFrameChunk(
    preview.path,
    chunkStart,
    Math.min(chunkSize, preview.n_frames - chunkStart),
    preview.format,
    preview.size_limit_overridden === true
  )
    .then(chunk => {
      writeChunkToStore(chunk)
      updateCachedFrameCount()
    })
    .finally(() => {
      pendingChunks.delete(chunkStart)
    })
  pendingChunks.set(chunkStart, request)
  await request
}

function createTrajectoryStore(preview: AsePreviewResponse): TrajectoryStore | null {
  if (!canPreloadTrajectory(preview)) return null
  const store: TrajectoryStore = {
    nFrames: preview.n_frames,
    nAtoms: preview.n_atoms,
    symbols: preview.frame.symbols ?? [],
    numbers: preview.frame.numbers ?? [],
    positions: new Float32Array(preview.n_frames * preview.n_atoms * 3),
    cells: new Float32Array(preview.n_frames * 9),
    tags: new Int32Array(preview.n_frames * preview.n_atoms),
    fixedMask: new Uint8Array(preview.n_frames * preview.n_atoms),
    energy: filledFloatArray(preview.n_frames),
    fmax: filledFloatArray(preview.n_frames),
    pbc: preview.frame.pbc,
    availableFrames: new Uint8Array(preview.n_frames),
    initialFrameIndex: preview.initial_frame_index
  }
  writeFrameToStore(store, frameToViewerFrame(preview.frame))
  return store
}

function filledFloatArray(length: number) {
  const array = new Float32Array(length)
  array.fill(Number.NaN)
  return array
}

function writeFrameToStore(store: TrajectoryStore, frame: StructureFrame) {
  if (frame.frameIndex < 0 || frame.frameIndex >= store.nFrames) return
  const atomOffset = frame.frameIndex * store.nAtoms
  const positionOffset = atomOffset * 3
  const positions = frame.positions instanceof Float32Array ? frame.positions : flattenPositions(frame.positions, store.nAtoms)
  store.positions.set(positions.subarray(0, store.nAtoms * 3), positionOffset)

  const cellOffset = frame.frameIndex * 9
  if (store.cells && frame.cell) store.cells.set(flattenCell(frame.cell), cellOffset)
  if (store.tags && frame.tags) {
    const tags = frame.tags instanceof Int32Array ? frame.tags : new Int32Array(frame.tags)
    store.tags.set(tags.subarray(0, store.nAtoms), atomOffset)
  }
  if (store.fixedMask) {
    store.fixedMask.fill(0, atomOffset, atomOffset + store.nAtoms)
    if (frame.fixedMask) {
      store.fixedMask.set(frame.fixedMask.subarray(0, store.nAtoms), atomOffset)
    } else {
      for (const index of frame.fixedIndices ?? []) {
        if (index >= 0 && index < store.nAtoms) store.fixedMask[atomOffset + index] = 1
      }
    }
  }
  if (store.energy) store.energy[frame.frameIndex] = finiteOrNaN(frame.energy)
  if (store.fmax) store.fmax[frame.frameIndex] = finiteOrNaN(frame.fmax)
  if (store.availableFrames) store.availableFrames[frame.frameIndex] = 1
}

function writeChunkToStore(chunk: AseFrameChunk) {
  if (!trajectoryStore) return
  const start = chunk.header.start
  const count = chunk.header.count
  const nAtoms = chunk.header.n_atoms
  if (nAtoms !== trajectoryStore.nAtoms) return

  trajectoryStore.positions.set(chunk.positions, start * nAtoms * 3)
  if (trajectoryStore.cells && chunk.cells) trajectoryStore.cells.set(chunk.cells, start * 9)
  if (trajectoryStore.tags && chunk.tags) trajectoryStore.tags.set(chunk.tags, start * nAtoms)
  if (trajectoryStore.fixedMask && chunk.fixedMask) trajectoryStore.fixedMask.set(chunk.fixedMask, start * nAtoms)
  if (trajectoryStore.energy && chunk.energy) trajectoryStore.energy.set(chunk.energy, start)
  if (trajectoryStore.fmax && chunk.fmax) trajectoryStore.fmax.set(chunk.fmax, start)
  trajectoryStore.symbols = chunk.header.symbols
  trajectoryStore.numbers = chunk.header.numbers
  trajectoryStore.pbc = chunk.header.pbc
  for (let localIndex = 0; localIndex < count; localIndex += 1) {
    if (trajectoryStore.availableFrames) trajectoryStore.availableFrames[start + localIndex] = 1
  }
  chemwebViewer?.setFrame(currentFrame.value.frame_index)
}

function updateCachedFrameCount() {
  cachedFrameCount.value = trajectoryStore?.availableFrames?.reduce((total, value) => total + value, 0) ?? jsonFrameCache.size
}

function isChunkAvailable(store: TrajectoryStore, chunkStart: number, preview: AsePreviewResponse) {
  const count = Math.min(chunkSize, preview.n_frames - chunkStart)
  for (let offset = 0; offset < count; offset += 1) {
    if (store.availableFrames?.[chunkStart + offset] !== 1) return false
  }
  return true
}

function isStoreFrameAvailable(store: TrajectoryStore, index: number) {
  return index >= 0 && index < store.nFrames && (!store.availableFrames || store.availableFrames[index] === 1)
}

function frameFromStore(index: number): AseFrame | null {
  if (!trajectoryStore || !isStoreFrameAvailable(trajectoryStore, index)) return null
  const nAtoms = trajectoryStore.nAtoms
  const atomOffset = index * nAtoms
  const positionOffset = atomOffset * 3
  const cellOffset = index * 9
  const positions: number[][] = []
  const tags: number[] = []
  const fixedIndices: number[] = []
  const cell: number[][] = []

  for (let atomIndex = 0; atomIndex < nAtoms; atomIndex += 1) {
    const offset = positionOffset + atomIndex * 3
    positions.push([
      trajectoryStore.positions[offset] ?? 0,
      trajectoryStore.positions[offset + 1] ?? 0,
      trajectoryStore.positions[offset + 2] ?? 0
    ])
    tags.push(trajectoryStore.tags?.[atomOffset + atomIndex] ?? 0)
    if (trajectoryStore.fixedMask?.[atomOffset + atomIndex]) fixedIndices.push(atomIndex)
  }

  for (let row = 0; row < 3; row += 1) {
    const offset = cellOffset + row * 3
    cell.push([
      trajectoryStore.cells?.[offset] ?? 0,
      trajectoryStore.cells?.[offset + 1] ?? 0,
      trajectoryStore.cells?.[offset + 2] ?? 0
    ])
  }

  const energy = trajectoryStore.energy?.[index]
  const fmax = trajectoryStore.fmax?.[index]
  return {
    frame_index: index,
    positions,
    cell,
    pbc: trajectoryStore.pbc ?? [false, false, false],
    tags,
    fixed_indices: fixedIndices,
    energy: energy === undefined || Number.isNaN(energy) ? null : energy,
    fmax: fmax === undefined || Number.isNaN(fmax) ? null : fmax,
    symbols: trajectoryStore.symbols,
    numbers: trajectoryStore.numbers
  }
}

function flattenPositions(positions: number[][], nAtoms: number) {
  const output = new Float32Array(nAtoms * 3)
  for (let index = 0; index < nAtoms; index += 1) {
    const position = positions[index] ?? [0, 0, 0]
    const offset = index * 3
    output[offset] = position[0] ?? 0
    output[offset + 1] = position[1] ?? 0
    output[offset + 2] = position[2] ?? 0
  }
  return output
}

function flattenCell(cell: Float32Array | number[][]) {
  if (cell instanceof Float32Array) return cell.subarray(0, 9)
  const output = new Float32Array(9)
  for (let row = 0; row < 3; row += 1) {
    const values = cell[row] ?? [0, 0, 0]
    const offset = row * 3
    output[offset] = values[0] ?? 0
    output[offset + 1] = values[1] ?? 0
    output[offset + 2] = values[2] ?? 0
  }
  return output
}

function finiteOrNaN(value: number | null | undefined) {
  return value === null || value === undefined || Number.isNaN(value) ? Number.NaN : value
}

function clampFrameIndex(index: number) {
  const max = Math.max(0, (props.asePreview?.n_frames ?? 1) - 1)
  if (!Number.isFinite(index)) return currentFrame.value.frame_index
  return Math.min(max, Math.max(0, Math.round(index)))
}

function resetAseState() {
  preloadVersion += 1
  jsonFrameCache.clear()
  pendingChunks.clear()
  const frame = props.asePreview?.frame ?? emptyFrame()
  currentFrame.value = frame
  frameInput.value = frame.frame_index
  jsonFrameCache.set(frame.frame_index, frame)
  trajectoryStore = props.asePreview ? createTrajectoryStore(props.asePreview) : null
  updateCachedFrameCount()
  const version = preloadVersion
  void preloadTrajectoryFrames(version)
}

function disposeChemwebViewer() {
  chemwebViewer?.dispose()
  chemwebViewer = null
}

onMounted(() => {
  resetAseState()
  void renderStructure()
  if (container.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(resizeViewer)
    resizeObserver.observe(container.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  disposeChemwebViewer()
  if (frameRequestHandle) window.cancelAnimationFrame(frameRequestHandle)
})

watch(
  () => [props.asePreview?.path, props.asePreview?.initial_frame_index],
  () => {
    resetAseState()
    bondScale.value = 1.25
    void renderStructure()
  }
)

watch(
  () => [selectedStyle.value, bondScale.value, showAtomIndex.value, showAtomTag.value],
  () => {
    if (chemwebViewer && props.asePreview) {
      chemwebViewer.setStyle(viewerStyle())
      chemwebViewer.setLabelOptions({
        showAtomIndex: showAtomIndex.value,
        showAtomTag: showAtomTag.value
      })
    } else {
      void renderStructure(true)
    }
  }
)
</script>

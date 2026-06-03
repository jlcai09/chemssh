<template>
  <div class="molecule-viewer">
    <div class="viewer-toolbar">
      <div class="viewer-style-group">
        <el-radio-group v-model="selectedStyle" size="small">
          <el-radio-button label="stick">{{ t('viewer.styleStick') }}</el-radio-button>
          <el-radio-button label="sphere">{{ t('viewer.styleSphere') }}</el-radio-button>
          <el-radio-button label="line">{{ t('viewer.styleLine') }}</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="asePreview?.is_trajectory" class="trajectory-controls">
        <button
          class="frame-mode-button"
          type="button"
          :aria-label="t('viewer.toggleFrameNumbering')"
          :aria-pressed="frameNumberMode === 'frame'"
          @click="toggleFrameNumberMode"
        >
          {{ frameNumberModeLabel }}
        </button>
        <el-input-number
          v-model="frameDisplayInput"
          class="frame-number"
          size="small"
          :min="frameDisplayMin"
          :max="frameDisplayMax"
          :step="1"
          controls-position="right"
          @change="scheduleFrameChange"
        />
        <span class="frame-total">/ {{ frameDisplayMax }}</span>
        <el-slider
          v-model="frameDisplayInput"
          class="frame-slider"
          :min="frameDisplayMin"
          :max="frameDisplayMax"
          :show-tooltip="false"
          size="small"
          @input="scheduleFrameChange"
        />
      </div>

      <div class="viewer-toolbar-actions">
        <el-tooltip :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false">
          <el-button :icon="Refresh" circle size="small" @click="refreshStructure" />
        </el-tooltip>
        <el-tooltip :content="t('viewer.exportScreenshot')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false">
          <el-button :icon="Download" circle size="small" @click="exportPng" />
        </el-tooltip>
      </div>
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

        <el-tooltip :content="t('viewer.resetView')" placement="right" popper-class="chemssh-passive-tooltip" :enterable="false">
          <el-button :aria-label="t('viewer.resetView')" :icon="ResetViewIcon" circle size="small" @click="resetView" />
        </el-tooltip>

        <el-popover trigger="click" placement="right-start" :width="236" :disabled="!structureHasCell">
          <template #reference>
            <el-button
              :aria-label="t('viewer.supercellSettings')"
              :class="{ 'is-active': hasSupercell }"
              :disabled="!structureHasCell"
              :icon="Grid"
              circle
              size="small"
            />
          </template>
          <div class="supercell-settings-panel">
            <div class="supercell-settings-header">
              <span>{{ t('viewer.supercell') }}</span>
              <strong>{{ supercellX }} x {{ supercellY }} x {{ supercellZ }}</strong>
            </div>
            <div class="supercell-axis-row">
              <span class="supercell-axis-label">X</span>
              <el-input-number
                v-model="supercellX"
                class="supercell-axis-input"
                size="small"
                :min="1"
                :max="supercellAxisMax('x')"
                :step="1"
                step-strictly
                controls-position="right"
                @change="clampSupercell"
              />
            </div>
            <div class="supercell-axis-row">
              <span class="supercell-axis-label">Y</span>
              <el-input-number
                v-model="supercellY"
                class="supercell-axis-input"
                size="small"
                :min="1"
                :max="supercellAxisMax('y')"
                :step="1"
                step-strictly
                controls-position="right"
                @change="clampSupercell"
              />
            </div>
            <div class="supercell-axis-row">
              <span class="supercell-axis-label">Z</span>
              <el-input-number
                v-model="supercellZ"
                class="supercell-axis-input"
                size="small"
                :min="1"
                :max="supercellAxisMax('z')"
                :step="1"
                step-strictly
                controls-position="right"
                @change="clampSupercell"
              />
            </div>
            <div class="supercell-settings-actions">
              <el-button size="small" text @click="resetSupercell">{{ t('viewer.resetSupercell') }}</el-button>
            </div>
          </div>
        </el-popover>

        <el-tooltip :content="t('viewer.wrapAtoms')" placement="right" popper-class="chemssh-passive-tooltip" :enterable="false">
          <el-button
            :aria-label="t('viewer.wrapAtoms')"
            :class="{ 'is-active': wrapAtoms }"
            :disabled="!structureHasCell"
            :icon="Crop"
            circle
            size="small"
            @click="toggleWrapAtoms"
          />
        </el-tooltip>
      </div>
      <div v-if="asePreview" class="viewer-overlay">
        <span>{{ frameNumberModeLabel }}: {{ currentFrameDisplayValue }} / {{ frameDisplayMax }}</span>
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
import { Connection, Crop, Download, Grid, Refresh, View } from '@element-plus/icons-vue'
import { readStructureFrame, readStructureFrameChunk, readStructureFrameJsonChunk } from '../api/structures'
import { t } from '../i18n'
import type { AseFrame, AseFrameChunk, AsePreviewResponse } from '../types/structure'
import type { StructureFrame, TrajectoryStore, ViewerStyleMode } from '../viewer'

type StyleMode = ViewerStyleMode
type ViewerModule = typeof import('../viewer')
type ChemSSHViewerInstance = InstanceType<ViewerModule['ChemSSHStructureViewer']>
type FrameNumberMode = 'index' | 'frame'

const props = withDefaults(
  defineProps<{
    asePreview?: AsePreviewResponse | null
    active?: boolean
    styleMode?: StyleMode
    backgroundColor?: string
  }>(),
  {
    asePreview: null,
    active: true,
    styleMode: 'stick',
    backgroundColor: '#ffffff'
  }
)

const emit = defineEmits<{
  refresh: []
  'render-start': []
  'render-complete': []
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
const supercellX = ref(1)
const supercellY = ref(1)
const supercellZ = ref(1)
const wrapAtoms = ref(false)
const frameNumberMode = ref<FrameNumberMode>('index')
const frameInput = ref(0)
const frameLoading = ref(false)
const cachedFrameCount = ref(0)
const currentFrame = ref<AseFrame>(props.asePreview?.frame ?? emptyFrame())

let chemsshViewer: ChemSSHViewerInstance | null = null
let resizeObserver: ResizeObserver | null = null
let renderVersion = 0
let scheduledFrame: number | null = null
let frameRequestHandle = 0
let preloadVersion = 0
let trajectoryStore: TrajectoryStore | null = null
let viewerModulePromise: Promise<ViewerModule> | null = null

const jsonFrameCache = new Map<number, AseFrame>()
const pendingChunks = new Map<number, Promise<void>>()
const pendingJsonChunks = new Map<number, Promise<void>>()
const chunkSize = 64
const jsonChunkSize = 16
const jsonWarmChunkRadius = 1
const maxLocalTrajectoryBytes = 512 * 1024 * 1024
const maxLocalJsonTrajectoryBytes = 256 * 1024 * 1024
const maxSupercellAxis = 10

const cacheStatus = computed(() => {
  if (!props.asePreview?.is_trajectory) return ''
  if (cachedFrameCount.value >= props.asePreview.n_frames) return ''
  return `Frames: ${cachedFrameCount.value} / ${props.asePreview.n_frames}`
})

const hasSupercell = computed(() => supercellX.value > 1 || supercellY.value > 1 || supercellZ.value > 1)

const structureHasCell = computed(() => hasUsableCell(currentFrame.value.cell))
const effectiveFrameNumberMode = computed<FrameNumberMode>(() => props.asePreview?.is_trajectory ? frameNumberMode.value : 'frame')
const frameNumberModeLabel = computed(() => effectiveFrameNumberMode.value === 'frame' ? t('viewer.frame') : t('viewer.index'))
const frameDisplayMin = computed(() => effectiveFrameNumberMode.value === 'frame' ? 1 : 0)
const frameDisplayMax = computed(() => {
  const frames = props.asePreview?.n_frames ?? 1
  return effectiveFrameNumberMode.value === 'frame' ? Math.max(1, frames) : Math.max(0, frames - 1)
})
const frameDisplayInput = computed({
  get: () => frameIndexToDisplayValue(frameInput.value),
  set: value => {
    frameInput.value = displayValueToFrameIndex(value)
  }
})
const currentFrameDisplayValue = computed(() => frameIndexToDisplayValue(currentFrame.value.frame_index))

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

function loadChemSSHViewer() {
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

function viewerDisplayOptions() {
  return {
    supercell: {
      x: supercellX.value,
      y: supercellY.value,
      z: supercellZ.value
    },
    wrap: wrapAtoms.value
  }
}

async function renderStructure(keepView = false) {
  const version = ++renderVersion
  emit('render-start')
  await nextTick()
  if (!container.value || version !== renderVersion) return

  if (!props.asePreview) {
    disposeChemSSHViewer()
    container.value.innerHTML = ''
    if (version === renderVersion) emit('render-complete')
    return
  }

  try {
    await renderChemSSHStructure(keepView)
  } catch (error) {
    console.warn('ChemSSH viewer failed.', error)
    disposeChemSSHViewer()
  } finally {
    if (version === renderVersion) emit('render-complete')
  }
}

async function renderChemSSHStructure(keepView = false) {
  if (!container.value || !props.asePreview) return
  if (!chemsshViewer) {
    container.value.innerHTML = ''
    const { ChemSSHStructureViewer } = await loadChemSSHViewer()
    chemsshViewer = new ChemSSHStructureViewer(container.value, {
      backgroundColor: props.backgroundColor,
      style: viewerStyle(),
      labelOptions: {
        showAtomIndex: showAtomIndex.value,
        showAtomTag: showAtomTag.value
      }
    })
  }

  chemsshViewer.setStyle(viewerStyle())
  chemsshViewer.setLabelOptions({
    showAtomIndex: showAtomIndex.value,
    showAtomTag: showAtomTag.value
  })
  chemsshViewer.setDisplayOptions(viewerDisplayOptions())

  if (trajectoryStore && props.asePreview.is_trajectory) {
    chemsshViewer.setTrajectory(trajectoryStore, {
      keepView,
      initialFrameIndex: currentFrame.value.frame_index
    })
    chemsshViewer.setFrame(currentFrame.value.frame_index)
    return
  }

  chemsshViewer.setStructure(frameToViewerFrame(currentFrame.value), { keepView })
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
  chemsshViewer?.resize()
}

function resetView() {
  chemsshViewer?.resetView()
}

function refreshStructure() {
  emit('refresh')
}

function exportPng() {
  const uri = chemsshViewer?.screenshot()
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

function resetSupercell() {
  supercellX.value = 1
  supercellY.value = 1
  supercellZ.value = 1
}

function resetStructureSwitchState() {
  resetSupercell()
  chemsshViewer?.clearSelection()
}

function toggleWrapAtoms() {
  wrapAtoms.value = !wrapAtoms.value
}

function toggleFrameNumberMode() {
  frameNumberMode.value = frameNumberMode.value === 'frame' ? 'index' : 'frame'
}

function frameIndexToDisplayValue(index: number) {
  return effectiveFrameNumberMode.value === 'frame' ? index + 1 : index
}

function displayValueToFrameIndex(value: number | undefined) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return currentFrame.value.frame_index
  return clampFrameIndex(effectiveFrameNumberMode.value === 'frame' ? numeric - 1 : numeric)
}

function supercellAxisMax(_axis: 'x' | 'y' | 'z') {
  return maxSupercellAxis
}

function clampSupercell() {
  supercellX.value = clampMultiplier(supercellX.value, supercellAxisMax('x'))
  supercellY.value = clampMultiplier(supercellY.value, supercellAxisMax('y'))
  supercellZ.value = clampMultiplier(supercellZ.value, supercellAxisMax('z'))
}

function clampMultiplier(value: number | undefined, max: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 1
  return Math.min(max, Math.max(1, Math.round(numeric)))
}

function hasUsableCell(cell: number[][] | undefined) {
  if (!cell || cell.length < 3) return false
  const ax = cell[0]?.[0] ?? 0
  const ay = cell[0]?.[1] ?? 0
  const az = cell[0]?.[2] ?? 0
  const bx = cell[1]?.[0] ?? 0
  const by = cell[1]?.[1] ?? 0
  const bz = cell[1]?.[2] ?? 0
  const cx = cell[2]?.[0] ?? 0
  const cy = cell[2]?.[1] ?? 0
  const cz = cell[2]?.[2] ?? 0
  const det = ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
  return Math.abs(det) > 1e-10
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

  if (preview.is_trajectory && !canPreloadTrajectory(preview)) {
    frameLoading.value = true
    try {
      await ensureJsonChunk(target, preview)
    } catch {
      // Fall back to the single-frame endpoint below.
    } finally {
      frameLoading.value = false
    }
  }

  const cached = jsonFrameCache.get(target)
  if (cached) {
    currentFrame.value = cached
    frameInput.value = target
    await renderStructure(true)
    warmJsonFramesAround(target)
    return
  }

  frameLoading.value = true
  try {
    const frame = await loadFrame(target)
    currentFrame.value = frame
    cacheJsonFrame(frame)
    frameInput.value = target
    await renderStructure(true)
    warmJsonFramesAround(target)
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
  chemsshViewer?.setFrame(index)
}

async function loadFrame(index: number) {
  if (!props.asePreview) return emptyFrame()
  if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, index)) {
    return frameFromStore(index) ?? emptyFrame()
  }
  return readStructureFrame(
    props.asePreview.source,
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

function canPreloadJsonTrajectory(preview: AsePreviewResponse) {
  return preview.is_trajectory && !canPreloadTrajectory(preview) && estimateJsonTrajectoryBytes(preview) <= maxLocalJsonTrajectoryBytes
}

function estimateJsonTrajectoryBytes(preview: AsePreviewResponse) {
  const sampledAtoms = Math.max(preview.n_atoms, preview.frame.positions.length)
  return sampledAtoms * preview.n_frames * 96 + preview.n_frames * 512
}

async function preloadTrajectoryFrames(version: number) {
  const preview = props.asePreview
  if (!preview?.is_trajectory) return
  if (canPreloadTrajectory(preview) && trajectoryStore) {
    await preloadBinaryTrajectoryFrames(version, preview)
    return
  }
  if (canPreloadJsonTrajectory(preview)) {
    await preloadJsonTrajectoryFrames(version, preview)
    return
  }
  warmJsonFramesAround(preview.initial_frame_index)
}

async function preloadBinaryTrajectoryFrames(version: number, preview: AsePreviewResponse) {
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

async function preloadJsonTrajectoryFrames(version: number, preview: AsePreviewResponse) {
  const starts = jsonChunkStartsForFullTrajectory(preview)
  const initialStart = jsonChunkStartForIndex(preview.initial_frame_index)
  starts.sort((left, right) => {
    if (left === initialStart) return -1
    if (right === initialStart) return 1
    return left - right
  })

  for (const start of starts) {
    if (version !== preloadVersion || !props.asePreview || props.asePreview.path !== preview.path) return
    try {
      await ensureJsonChunkStart(start, preview)
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

function jsonChunkStartsForFullTrajectory(preview: AsePreviewResponse) {
  const starts: number[] = []
  for (let start = 0; start < preview.n_frames; start += jsonChunkSize) {
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
  const request = readStructureFrameChunk(
    preview.source,
    preview.path,
    chunkStart,
    Math.min(chunkSize, preview.n_frames - chunkStart),
    preview.format,
    preview.size_limit_overridden === true
  )
    .then(chunk => {
      if (!props.asePreview || props.asePreview.path !== preview.path) return
      writeChunkToStore(chunk)
      updateCachedFrameCount()
    })
    .finally(() => {
      pendingChunks.delete(chunkStart)
    })
  pendingChunks.set(chunkStart, request)
  await request
}

async function ensureJsonChunk(index: number, preview: AsePreviewResponse) {
  await ensureJsonChunkStart(jsonChunkStartForIndex(index), preview)
}

async function ensureJsonChunkStart(chunkStart: number, preview: AsePreviewResponse) {
  if (isJsonChunkAvailable(chunkStart, preview)) return
  const pending = pendingJsonChunks.get(chunkStart)
  if (pending) {
    await pending
    return
  }

  const request = readStructureFrameJsonChunk(
    preview.source,
    preview.path,
    chunkStart,
    Math.min(jsonChunkSize, preview.n_frames - chunkStart),
    preview.format,
    preview.size_limit_overridden === true
  )
    .then(chunk => {
      if (!props.asePreview || props.asePreview.path !== preview.path) return
      for (const frame of chunk.frames) {
        jsonFrameCache.set(frame.frame_index, frame)
      }
      updateCachedFrameCount()
    })
    .finally(() => {
      pendingJsonChunks.delete(chunkStart)
    })
  pendingJsonChunks.set(chunkStart, request)
  await request
}

function warmJsonFramesAround(index: number) {
  const preview = props.asePreview
  if (!preview?.is_trajectory || canPreloadTrajectory(preview)) return
  const center = jsonChunkStartForIndex(index)
  const starts: number[] = []
  for (let radius = 0; radius <= jsonWarmChunkRadius; radius += 1) {
    starts.push(center - radius * jsonChunkSize, center + radius * jsonChunkSize)
  }
  for (const start of new Set(starts)) {
    if (start < 0 || start >= preview.n_frames) continue
    void ensureJsonChunkStart(start, preview).catch(() => undefined)
  }
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
  chemsshViewer?.setFrame(currentFrame.value.frame_index)
}

function updateCachedFrameCount() {
  cachedFrameCount.value = trajectoryStore?.availableFrames?.reduce((total, value) => total + value, 0) ?? jsonFrameCache.size
}

function cacheJsonFrame(frame: AseFrame) {
  jsonFrameCache.set(frame.frame_index, frame)
  updateCachedFrameCount()
}

function isChunkAvailable(store: TrajectoryStore, chunkStart: number, preview: AsePreviewResponse) {
  const count = Math.min(chunkSize, preview.n_frames - chunkStart)
  for (let offset = 0; offset < count; offset += 1) {
    if (store.availableFrames?.[chunkStart + offset] !== 1) return false
  }
  return true
}

function isJsonChunkAvailable(chunkStart: number, preview: AsePreviewResponse) {
  const count = Math.min(jsonChunkSize, preview.n_frames - chunkStart)
  for (let offset = 0; offset < count; offset += 1) {
    if (!jsonFrameCache.has(chunkStart + offset)) return false
  }
  return true
}

function jsonChunkStartForIndex(index: number) {
  return Math.floor(index / jsonChunkSize) * jsonChunkSize
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
  pendingJsonChunks.clear()
  const frame = props.asePreview?.frame ?? emptyFrame()
  currentFrame.value = frame
  frameInput.value = frame.frame_index
  cacheJsonFrame(frame)
  trajectoryStore = props.asePreview ? createTrajectoryStore(props.asePreview) : null
  updateCachedFrameCount()
  const version = preloadVersion
  void preloadTrajectoryFrames(version)
}

function disposeChemSSHViewer() {
  chemsshViewer?.dispose()
  chemsshViewer = null
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
  disposeChemSSHViewer()
  if (frameRequestHandle) window.cancelAnimationFrame(frameRequestHandle)
})

watch(
  () => props.asePreview,
  () => {
    resetStructureSwitchState()
    resetAseState()
    void renderStructure(true)
  }
)

watch(
  () => props.active,
  async active => {
    if (!active) return
    await nextTick()
    resizeViewer()
    if (props.asePreview) void renderStructure(true)
  },
  { flush: 'post' }
)

watch(
  () => [selectedStyle.value, bondScale.value, showAtomIndex.value, showAtomTag.value],
  () => {
    if (chemsshViewer && props.asePreview) {
      chemsshViewer.setStyle(viewerStyle())
      chemsshViewer.setLabelOptions({
        showAtomIndex: showAtomIndex.value,
        showAtomTag: showAtomTag.value
      })
    } else {
      void renderStructure(true)
    }
  }
)

watch(
  () => [supercellX.value, supercellY.value, supercellZ.value, wrapAtoms.value, structureHasCell.value],
  () => {
    if (!structureHasCell.value) {
      resetSupercell()
      wrapAtoms.value = false
      return
    }
    clampSupercell()
    if (chemsshViewer && props.asePreview) {
      chemsshViewer.setDisplayOptions(viewerDisplayOptions())
    } else {
      void renderStructure(true)
    }
  }
)
</script>

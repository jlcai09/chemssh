<template>
  <div ref="rootEl" class="molecule-viewer" tabindex="-1" @keydown="handleViewerKeydown">
    <div class="viewer-toolbar">
      <div class="viewer-style-group">
        <el-radio-group :model-value="selectedStyle" size="small" @change="handleGlobalStyleChange">
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
        <el-tooltip :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button :icon="Refresh" circle size="small" @click="refreshStructure" />
        </el-tooltip>
        <el-dropdown trigger="click" @command="handleExportCommand">
          <el-button :icon="Download" circle size="small" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="original">{{ t('viewer.exportOriginal') }}</el-dropdown-item>
              <el-dropdown-item command="current-xyz">{{ t('viewer.exportCurrentXYZ') }}</el-dropdown-item>
              <el-dropdown-item command="current-xsd">{{ t('viewer.exportCurrentXSD') }}</el-dropdown-item>
              <el-dropdown-item v-if="asePreview?.is_trajectory" command="trajectory-xyz" divided>{{ t('viewer.exportTrajectoryXYZ') }}</el-dropdown-item>
              <el-dropdown-item v-if="asePreview?.is_trajectory" command="trajectory-arc">{{ t('viewer.exportTrajectoryArc') }}</el-dropdown-item>
              <el-dropdown-item command="screenshot">{{ t('viewer.exportScreenshot') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <div class="viewer-stage">
      <div ref="container" class="viewer-canvas" />
      <div v-if="asePreview" class="atom-index-base-status" aria-live="polite">
        {{ atomIndexBaseStatus }}
        <span v-if="asePreview?.file_incomplete" class="file-incomplete-hint">{{ t('viewer.fileIncomplete') }}</span>
      </div>
      <div v-if="showExpandedStructureWarning" class="structure-warning-banner" role="status">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ structureWarningText }}</span>
        <el-tooltip :content="t('panel.close')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="structure-warning-close" type="button" :aria-label="t('panel.close')" @click="dismissStructureWarning">
            <el-icon><Close /></el-icon>
          </button>
        </el-tooltip>
      </div>
      <el-tooltip
        v-else-if="showCollapsedStructureWarning"
        :content="structureWarningText"
        placement="top"
        popper-class="chemssh-passive-tooltip"
        :enterable="false"
        :show-after="150"
      >
        <button class="structure-warning-indicator" type="button" :aria-label="structureWarningText">
          <el-icon><WarningFilled /></el-icon>
        </button>
      </el-tooltip>
      <div v-if="asePreview" class="viewer-floating-tools">
        <el-popover trigger="click" placement="right-start" :width="260" :teleported="false">
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

        <el-popover trigger="click" placement="right-start" :width="220" :teleported="false">
          <template #reference>
            <el-button :aria-label="t('viewer.displaySettings')" :icon="View" circle size="small" />
          </template>
          <div class="display-settings-panel">
            <el-checkbox v-model="showAtomIndex">{{ t('viewer.atomIndex') }}</el-checkbox>
            <el-checkbox v-model="showAtomTag">{{ t('viewer.atomTag') }}</el-checkbox>
            <div class="atom-index-base-row">
              <span>{{ t('viewer.atomIndexBase') }}</span>
              <el-segmented v-model="atomIndexBase" :options="atomIndexBaseOptions" size="small" />
            </div>
          </div>
        </el-popover>

        <el-tooltip :content="t('viewer.resetView')" placement="right" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button :aria-label="t('viewer.resetView')" :icon="ResetViewIcon" circle size="small" @click="resetView" />
        </el-tooltip>

        <el-popover trigger="click" placement="right-start" :width="236" :disabled="!structureHasCell" :teleported="false">
          <template #reference>
            <el-button
              :aria-label="t('viewer.supercellSettings')"
              :type="hasSupercell ? 'success' : undefined"
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

        <el-popover trigger="click" placement="right-start" :width="210" :disabled="!structureHasCell" :teleported="false">
          <template #reference>
            <el-button
              :aria-label="t('viewer.wrapAtoms')"
              :aria-pressed="wrapMode !== 'off'"
              :type="wrapMode !== 'off' ? 'success' : undefined"
              :disabled="!structureHasCell"
              :icon="Crop"
              circle
              size="small"
            />
          </template>
            <div class="wrap-settings-panel">
            <el-radio-group v-model="wrapMode" class="wrap-mode-group" size="small">
              <el-radio label="off">{{ t('viewer.wrapModeOff') }}</el-radio>
              <el-radio label="atom">{{ t('viewer.wrapModeAtom') }}</el-radio>
              <el-radio label="molecule">{{ t('viewer.wrapModeMolecule') }}</el-radio>
            </el-radio-group>
          </div>
        </el-popover>

        <el-tooltip :content="t('viewer.dynamicRules.title')" placement="right" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <div class="dynamic-rule-btn-wrap">
            <el-button
              :aria-label="t('viewer.dynamicRules.title')"
              :aria-pressed="dynamicPanelOpen"
              :type="activeDynamicRuleCount > 0 || dynamicPanelOpen ? 'primary' : undefined"
              :icon="Filter"
              circle
              size="small"
              @click="dynamicPanelOpen = !dynamicPanelOpen"
            />
            <span v-if="activeDynamicRuleCount > 0" class="dynamic-rule-badge">{{ activeDynamicRuleCount }}</span>
          </div>
        </el-tooltip>
      </div>

      <DynamicDisplayPanel
        v-if="asePreview && dynamicPanelOpen"
        :rules="dynamicRules"
        :match-counts="dynamicRuleMatchCounts"
        :available-formulas="dynamicAvailableFormulas"
        :selected-atoms="selectedSourceAtoms"
        :has-cell="structureHasCell"
        @update:rules="handleDynamicRulesUpdate"
        @close="dynamicPanelOpen = false"
      />
      <div v-if="asePreview" class="viewer-overlay" :class="{ 'is-collapsed': overlayCollapsed }">
        <button
          class="viewer-overlay-toggle"
          type="button"
          :aria-label="overlayCollapsed ? t('viewer.expandOverlay') : t('viewer.collapseOverlay')"
          :title="overlayCollapsed ? t('viewer.expandOverlay') : t('viewer.collapseOverlay')"
          @click="overlayCollapsed = !overlayCollapsed"
        >
          <el-icon>
            <CaretBottom v-if="overlayCollapsed" />
            <CaretTop v-else />
          </el-icon>
        </button>
        <el-tooltip
          v-if="!overlayCollapsed && trajectoryMetricsChart?.sampled"
          :content="t('viewer.sampledMetrics')"
          placement="left"
          popper-class="chemssh-passive-tooltip"
          :enterable="false"
          :show-after="500"
        >
          <span class="viewer-metric-sampled-warning" :aria-label="t('viewer.sampledMetrics')">
            <el-icon><WarningFilled /></el-icon>
          </span>
        </el-tooltip>
        <div v-if="!overlayCollapsed" class="viewer-overlay-content">
          <span class="viewer-overlay-row">{{ frameNumberModeLabel }}: {{ currentFrameDisplayValue }} / {{ frameDisplayMax }}</span>
          <span class="viewer-overlay-row">Energy: {{ formatMetric(currentFrame.energy, ' eV') }}</span>
          <span class="viewer-overlay-row">Fmax: {{ formatMetric(currentFrame.fmax, ' eV/A') }}</span>
          <div v-if="trajectoryMetricsChart" class="viewer-metrics-chart">
            <div
              v-for="curve in trajectoryMetricsChart.curves"
              :key="curve.key"
              class="viewer-metric-plot"
            >
              <div class="viewer-metric-plot-header">
                <span>{{ curve.label }}</span>
                <span>min {{ trajectoryMetricsChart.xAxisLabel }} {{ curve.min.display }}</span>
              </div>
              <svg
                aria-hidden="true"
                class="viewer-metric-svg is-clickable"
                :viewBox="`0 0 ${trajectoryMetricsChart.width} ${trajectoryMetricsChart.height}`"
                @click="handleMetricChartClick($event)"
              >
                <line
                  class="viewer-metric-axis"
                  :x1="trajectoryMetricsChart.padding.left"
                  :y1="trajectoryMetricsChart.axisY"
                  :x2="trajectoryMetricsChart.width - trajectoryMetricsChart.padding.right"
                  :y2="trajectoryMetricsChart.axisY"
                />
                <path class="viewer-metric-area" :d="curve.areaPath" :style="{ fill: curve.areaColor }" />
                <path class="viewer-metric-line" :d="curve.path" :style="{ stroke: curve.color }" />
                <circle class="viewer-metric-min-dot" :cx="curve.min.x" :cy="curve.min.y" r="2.4" :style="{ fill: curve.color }" />
                <text
                  class="viewer-metric-min-label"
                  :x="curve.min.labelX"
                  :y="curve.min.labelY"
                  :text-anchor="curve.min.anchor"
                >
                  {{ curve.min.display }}
                </text>
              </svg>
            </div>
          </div>
          <div v-if="canTrackGeometry" class="viewer-geometry-track">
            <el-checkbox v-model="trackGeometry" size="small">{{ t('viewer.trackGeometry') }}</el-checkbox>
            <div v-if="trackGeometry && geometryTrajectoryChart" class="viewer-metric-plot">
              <div class="viewer-metric-plot-header">
                <span>{{ geometryTrajectoryChart.label }}</span>
                <span>{{ geometryTrajectoryChart.currentDisplay }}</span>
              </div>
              <svg
                aria-hidden="true"
                class="viewer-metric-svg is-clickable"
                :viewBox="`0 0 ${metricChartWidth} ${metricChartHeight}`"
                @click="handleMetricChartClick($event)"
              >
                <line
                  class="viewer-metric-axis"
                  :x1="metricChartPadding.left"
                  :y1="metricChartHeight - metricChartPadding.bottom"
                  :x2="metricChartWidth - metricChartPadding.right"
                  :y2="metricChartHeight - metricChartPadding.bottom"
                />
                <path class="viewer-metric-area" :d="geometryTrajectoryChart.areaPath" style="fill: rgba(16, 185, 129, 0.16)" />
                <path class="viewer-metric-line" :d="geometryTrajectoryChart.path" style="stroke: #10b981" />
                <circle
                  v-if="geometryTrajectoryChart.currentPoint"
                  class="viewer-metric-min-dot"
                  :cx="geometryTrajectoryChart.currentPoint.x"
                  :cy="geometryTrajectoryChart.currentPoint.y"
                  r="2.6"
                  style="fill: #10b981"
                />
              </svg>
            </div>
          </div>
          <span v-if="cacheStatus">{{ cacheStatus }}</span>
        </div>
      </div>
      <div v-if="frameLoading" class="viewer-loading" aria-live="polite">
        <div class="viewer-loading-card">
          <span class="viewer-loading-title">{{ t('viewer.frameLoading') }}</span>
          <span class="viewer-loading-frame">{{ frameNumberModeLabel }} {{ frameIndexToDisplayValue(requestedFrameIndex) }}</span>
        </div>
      </div>
    </div>

    <StructureContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :has-selection="selectedSourceAtoms.length > 0"
      :has-hidden="hasHiddenAtoms"
      :is-trajectory="Boolean(asePreview?.is_trajectory)"
      :follow-selection="followSelection"
      @close="closeContextMenu"
      @action="handleContextMenuAction"
      @display="handleContextDisplayMode"
    />

    <el-dialog
      v-model="radiusDialogVisible"
      :title="radiusDialogTitle"
      width="340px"
      :z-index="3600"
      append-to-body
      destroy-on-close
    >
      <div class="radius-dialog-body">
        <div class="radius-dialog-row">
          <span>{{ t('viewer.radiusLabel') }}</span>
          <el-input-number v-model="radiusCutoff" :min="0.5" :max="50" :step="0.5" :precision="2" size="small" />
        </div>
        <el-checkbox v-model="radiusExpandFragments">{{ t('viewer.radiusExpandFragments') }}</el-checkbox>
      </div>
      <template #footer>
        <el-button size="small" @click="radiusDialogVisible = false">{{ t('viewer.radiusCancel') }}</el-button>
        <el-button size="small" type="primary" :loading="fragmentQueryLoading" @click="confirmRadiusSelection">
          {{ radiusDialogPurpose === 'select' ? t('viewer.radiusConfirm') : t('viewer.dynamicRules.apply') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch, watchEffect } from 'vue'
import { CaretBottom, CaretTop, Close, Connection, Crop, Download, Filter, Grid, Refresh, View, WarningFilled } from '@element-plus/icons-vue'
import { compactFrameFromStructureChunk, evaluateStructureDynamicDisplay, queryStructureFragments, readStructureFrame, readStructureFrameChunk, readStructureFrameJsonChunk, streamStructureFrames } from '../api/structures'
import { downloadUrl } from '../api/http'
import { t } from '../i18n'
import type { AseFrame, AseFrameChunk, AsePreviewResponse, DynamicDisplayRule, DynamicDisplayStyle, FragmentQueryMode } from '../types/structure'
import type { AtomDisplayMode, AtomIndexBase, StructureFrame, TrajectoryStore, ViewerContextMenuEvent, ViewerStyleMode, WrapMode } from '../viewer'
import { estimateDenseTrajectoryBytes, isCompactAseFrame, materializeAseFrame, nextTrajectoryChunkIndex, trajectoryCacheBudget, trajectoryChunkRequest, type CachedTrajectoryFrame } from '../viewer/trajectoryCacheBudget'
import { exportSelectedAtomsToXYZ, exportToXYZ, exportToXSD, downloadTrajectoryExport, TrajectoryExportTooLargeError, downloadTextFile, getBaseFilename } from '../utils/structureExport'
import StructureContextMenu, { type StructureContextAction } from './StructureContextMenu.vue'
import DynamicDisplayPanel from './DynamicDisplayPanel.vue'
import { ElMessage } from 'element-plus'

type StyleMode = ViewerStyleMode
type ViewerModule = typeof import('../viewer')
type ChemSSHViewerInstance = InstanceType<ViewerModule['ChemSSHStructureViewer']>
type FrameNumberMode = 'index' | 'frame'
type TrajectoryMetricKey = 'energy' | 'fmax'

interface TrajectoryMetricPoint {
  index: number
  value: number
  display: number
  x: number
  y: number
}

interface TrajectoryMetricSample {
  index: number
  value: number
}

interface TrajectoryMetricCurve {
  key: TrajectoryMetricKey
  label: string
  color: string
  areaColor: string
  sampled: boolean
  path: string
  areaPath: string
  min: TrajectoryMetricPoint & {
    labelX: number
    labelY: number
    anchor: 'start' | 'end'
  }
}

interface FrameReadContext {
  preview: AsePreviewResponse
  generation: number
  signal: AbortSignal
}

interface FrameReadResult {
  frame: CachedTrajectoryFrame | null
  nextIndex: number
}

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

const rootEl = ref<HTMLElement | null>(null)
const container = ref<HTMLElement | null>(null)
const selectedStyle = ref<StyleMode | ''>(props.styleMode)
const lastBaseStyle = ref<StyleMode>(props.styleMode)
const bondScale = ref(1.25)
const showAtomIndex = ref(false)
const showAtomTag = ref(false)
const atomIndexBase = ref<AtomIndexBase>(0)
const supercellX = ref(1)
const supercellY = ref(1)
const supercellZ = ref(1)
const wrapMode = ref<WrapMode>('off')
const selectedSourceAtoms = ref<number[]>([])
const hasHiddenAtoms = ref(false)
const followSelection = ref(false)
const trackGeometry = ref(false)
const fragmentQueryLoading = ref(false)
const radiusDialogVisible = ref(false)
const radiusDialogPurpose = ref<'select' | 'dynamic-hide-outside' | 'dynamic-dim-outside'>('select')
const radiusDialogTitle = computed(() => {
  if (radiusDialogPurpose.value === 'dynamic-hide-outside') return t('viewer.contextMenu.dynamicShowOnlyShell')
  if (radiusDialogPurpose.value === 'dynamic-dim-outside') return t('viewer.contextMenu.dynamicDimOutsideShell')
  return t('viewer.radiusDialogTitle')
})
const radiusCutoff = ref(3.5)
const radiusExpandFragments = ref(true)
const dynamicPanelOpen = ref(false)
const dynamicRules = ref<DynamicDisplayRule[]>([])
const dynamicRuleMatchCounts = ref<Record<string, number>>({})
const dynamicAvailableFormulas = ref<string[]>([])
const activeDynamicRuleCount = computed(() => dynamicRules.value.filter(r => r.enabled).length)
const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0
})
const frameNumberMode = ref<FrameNumberMode>('index')
const requestedFrameIndex = ref(0)
const frameLoading = ref(false)
const cachedFrameCount = ref(0)
const cacheRevision = ref(0)
const isOnDemandTrajectory = ref(false)
const currentFrame = shallowRef<CachedTrajectoryFrame>(props.asePreview?.frame ?? emptyFrame())
const overlayCollapsed = ref(false)
const structureWarningDismissed = ref(false)

let chemsshViewer: ChemSSHViewerInstance | null = null
let resizeObserver: ResizeObserver | null = null
let renderVersion = 0
let scheduledFrame: number | null = null
let frameRequestHandle = 0
let frameLoadVersion = 0
let frameLoadingVersion = 0
let frameLoadingTimer: number | null = null
let preloadVersion = 0
let trajectoryStore: TrajectoryStore | null = null
let viewerModulePromise: Promise<ViewerModule> | null = null
let finishActiveStream: (() => void) | null = null
let foregroundRequest: AbortController | null = null
let backgroundRequest: AbortController | null = null
let exportRequest: AbortController | null = null
let fragmentRequest: AbortController | null = null
let wrapRequest: AbortController | null = null
let dynamicDisplayRequest: AbortController | null = null
const moleculeWrapCache = new Map<string, number[][]>()
const dynamicDisplayCache = new Map<string, { atomModes: Uint8Array; matchCounts: Record<string, number>; formulas: string[] }>()
let generation = 0
let disposed = false

const frameCache = trajectoryCacheBudget.registerViewer(updateCachedFrameCount)
const chunkSize = 32
const streamChunkSize = 32
const frameLoadingDelayMs = 120
const maxSupercellAxis = 10
const metricChartWidth = 132
const metricChartHeight = 44
const metricChartPadding = { left: 8, right: 8, top: 7, bottom: 12 }
const maxMetricPlotPoints = 180
const metricSamplingFrameThreshold = 1000
const atomIndexBaseOptions = [
  { label: '0', value: 0 },
  { label: '1', value: 1 }
]

const cacheStatus = computed(() => {
  if (!props.asePreview?.is_trajectory) return ''
  if (cachedFrameCount.value >= props.asePreview.n_frames) return ''
  if (isOnDemandTrajectory.value) {
    return t('viewer.onDemandCachedFrames', { cached: cachedFrameCount.value, total: props.asePreview.n_frames })
  }
  return t('viewer.cachedFrames', { cached: cachedFrameCount.value, total: props.asePreview.n_frames })
})

const hasSupercell = computed(() => supercellX.value > 1 || supercellY.value > 1 || supercellZ.value > 1)

const structureHasCell = computed(() => hasUsableCell(currentFrame.value.cell))
const atomIndexBaseStatus = computed(() => t('viewer.atomIndexBaseStatus', { start: atomIndexBase.value }))
const effectiveFrameNumberMode = computed<FrameNumberMode>(() => props.asePreview?.is_trajectory ? frameNumberMode.value : 'frame')
const frameNumberModeLabel = computed(() => effectiveFrameNumberMode.value === 'frame' ? t('viewer.frame') : t('viewer.index'))
const frameDisplayMin = computed(() => effectiveFrameNumberMode.value === 'frame' ? 1 : 0)
const frameDisplayMax = computed(() => {
  const frames = props.asePreview?.n_frames ?? 1
  return effectiveFrameNumberMode.value === 'frame' ? Math.max(1, frames) : Math.max(0, frames - 1)
})
const frameDisplayInput = computed({
  get: () => frameIndexToDisplayValue(requestedFrameIndex.value),
  set: value => {
    requestedFrameIndex.value = displayValueToFrameIndex(value)
  }
})
const currentFrameDisplayValue = computed(() => frameIndexToDisplayValue(currentFrame.value.frame_index))
const structureWarningMessages = computed(() => {
  const warnings = props.asePreview?.warnings ?? []
  const messages: string[] = []
  if (warnings.includes('vasp_outcar_md_may_lack_structure')) {
    messages.push(t('viewer.vaspOutcarMdWarning'))
  }
  if (warnings.includes('vasp_outcar_constraints_missing') || warnings.includes('vasp_outcar_constraints_unreadable')) {
    messages.push(t('viewer.vaspOutcarConstraintWarning'))
  }
  return messages
})
const structureWarningText = computed(() => structureWarningMessages.value.join(' '))
const showStructureWarning = computed(() => structureWarningMessages.value.length > 0)
const showExpandedStructureWarning = computed(() => showStructureWarning.value && !structureWarningDismissed.value)
const showCollapsedStructureWarning = computed(() => showStructureWarning.value && structureWarningDismissed.value)

// Optimize: Cache chart computation to avoid rebuilding on every tick
const trajectoryMetricsChart = computed(() => {
  const preview = props.asePreview
  if (!props.active || !preview?.is_trajectory || preview.n_frames < 2) return null

  // LRU replacement can change the resident metrics without changing the count.
  void cacheRevision.value

  const energy = buildMetricCurve('energy', 'Energy', '#176b87', 'rgba(23, 107, 135, 0.12)')
  const fmax = buildMetricCurve('fmax', 'Fmax', '#9a5b13', 'rgba(154, 91, 19, 0.12)')
  const curves = [energy, fmax].filter((curve): curve is TrajectoryMetricCurve => curve !== null)
  if (curves.length === 0) return null

  return {
    width: metricChartWidth,
    height: metricChartHeight,
    padding: metricChartPadding,
    axisY: metricChartHeight - metricChartPadding.bottom,
    xAxisLabel: frameNumberModeLabel.value,
    sampled: curves.some(curve => curve.sampled),
    curves
  }
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

function loadChemSSHViewer() {
  viewerModulePromise ??= import('../viewer')
  return viewerModulePromise
}

function viewerStyleMode(): ViewerStyleMode {
  return selectedStyle.value || lastBaseStyle.value
}

function viewerStyle() {
  return {
    mode: viewerStyleMode(),
    atomScale: 0.42,
    bondRadius: 0.065,
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
    wrap: wrapMode.value !== 'off',
    wrapMode: wrapMode.value
  }
}

function handleGlobalStyleChange(value: string | number | boolean | undefined) {
  if (value !== 'stick' && value !== 'sphere' && value !== 'line') return
  selectedStyle.value = value
  lastBaseStyle.value = value
  if (activeDynamicRuleCount.value > 0) {
    void evaluateDynamicRulesForFrame(currentFrame.value.frame_index)
  } else {
    chemsshViewer?.setAllAtomsDisplayMode(value)
  }
}

function handleViewerContextMenu(event: ViewerContextMenuEvent) {
  contextMenu.x = event.clientX
  contextMenu.y = event.clientY
  contextMenu.visible = true
}

function closeContextMenu() {
  contextMenu.visible = false
}

function handleContextDisplayMode(mode: AtomDisplayMode) {
  const atoms = chemsshViewer?.getSelectedSourceAtomIndices() ?? []
  if (!atoms.length) return
  chemsshViewer?.setAtomDisplayMode(atoms, mode)
}

function handleContextMenuAction(action: StructureContextAction) {
  if (!chemsshViewer) return
  switch (action) {
    case 'select-connected':
      void runFragmentQuery('connected')
      break
    case 'select-same':
      void runFragmentQuery('same_formula')
      break
    case 'select-same-element':
      chemsshViewer.selectSameElement()
      break
    case 'select-within-radius':
      radiusDialogPurpose.value = 'select'
      radiusDialogVisible.value = true
      break
    case 'dynamic-hide-same-formula':
      void createDynamicFormulaRuleFromSelection('hidden')
      break
    case 'dynamic-dim-same-formula':
      void createDynamicFormulaRuleFromSelection('dim')
      break
    case 'dynamic-line-same-formula':
      void createDynamicFormulaRuleFromSelection('line')
      break
    case 'dynamic-show-only-shell':
      radiusDialogPurpose.value = 'dynamic-hide-outside'
      radiusDialogVisible.value = true
      break
    case 'dynamic-dim-outside-shell':
      radiusDialogPurpose.value = 'dynamic-dim-outside'
      radiusDialogVisible.value = true
      break
    case 'manage-dynamic-rules':
      dynamicPanelOpen.value = true
      break
    case 'invert-selection':
      chemsshViewer.invertSelection()
      break
    case 'select-all':
      chemsshViewer.selectAllAtoms()
      break
    case 'clear-selection':
      chemsshViewer.clearSelection()
      break
    case 'show-only-selected': {
      const atoms = chemsshViewer.getSelectedSourceAtomIndices()
      if (atoms.length) chemsshViewer.showOnlyAtoms(atoms)
      break
    }
    case 'show-all':
      chemsshViewer.showAllAtoms()
      break
    case 'focus-selection':
      chemsshViewer.focusOnSelection()
      break
    case 'toggle-follow-selection':
      followSelection.value = !followSelection.value
      chemsshViewer.setFollowSelection(followSelection.value)
      break
    case 'export-selected-xyz':
      exportSelectedXYZ()
      break
  }
}

async function runFragmentQuery(
  mode: FragmentQueryMode,
  options: { seedAtoms?: number[]; radius?: number; expandFragments?: boolean } = {}
) {
  const preview = props.asePreview
  if (!preview || !chemsshViewer) return
  const seeds = options.seedAtoms ?? chemsshViewer.getSelectedSourceAtomIndices()
  if (mode !== 'whole_molecule_wrap' && !seeds.length) return

  fragmentRequest?.abort()
  const controller = new AbortController()
  fragmentRequest = controller
  const requestGen = generation
  fragmentQueryLoading.value = true

  try {
    const response = await queryStructureFragments(
      preview.source,
      {
        path: preview.path,
        format: preview.format,
        force: preview.size_limit_overridden === true,
        frame_index: currentFrame.value.frame_index,
        bond_scale: bondScale.value,
        seed_atoms: seeds,
        mode,
        use_pbc: structureHasCell.value,
        radius: options.radius,
        expand_fragments: options.expandFragments ?? true
      },
      { signal: controller.signal }
    )
    if (disposed || requestGen !== generation || controller.signal.aborted) return
    chemsshViewer.setSelectedSourceAtoms(response.atom_indices)
    if (response.atom_indices.length > 0 && mode !== 'connected') {
      ElMessage.success(t('viewer.fragmentSelected', { atoms: response.atom_indices.length, fragments: response.fragment_count }))
    }
  } catch (error) {
    if (!(error instanceof Error && error.name === 'AbortError')) {
      console.warn('Fragment query failed.', error)
      ElMessage.error(t('viewer.fragmentQueryFailed'))
    }
  } finally {
    if (fragmentRequest === controller) fragmentRequest = null
    fragmentQueryLoading.value = false
  }
}

async function confirmRadiusSelection() {
  radiusDialogVisible.value = false
  if (radiusDialogPurpose.value === 'select') {
    await runFragmentQuery('within_radius', {
      radius: radiusCutoff.value,
      expandFragments: radiusExpandFragments.value
    })
    return
  }
  const atoms = chemsshViewer?.getSelectedSourceAtomIndices() ?? []
  if (!atoms.length) return
  const style: DynamicDisplayStyle = radiusDialogPurpose.value === 'dynamic-hide-outside' ? 'hidden' : 'dim'
  const newRule: DynamicDisplayRule = {
    id: `rule_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
    enabled: true,
    type: 'shell',
    style,
    anchor_type: 'atoms',
    anchor_atoms: [...atoms],
    radius: radiusCutoff.value,
    outside: true,
    expand_fragments: radiusExpandFragments.value
  }
  handleDynamicRulesUpdate([...dynamicRules.value, newRule])
  ElMessage.success(t('viewer.dynamicRules.ruleAdded'))
}

async function createDynamicFormulaRuleFromSelection(style: DynamicDisplayStyle) {
  const preview = props.asePreview
  if (!preview || !chemsshViewer) return
  const seeds = chemsshViewer.getSelectedSourceAtomIndices()
  if (!seeds.length) return
  try {
    const response = await queryStructureFragments(preview.source, {
      path: preview.path,
      format: preview.format,
      force: preview.size_limit_overridden === true,
      frame_index: currentFrame.value.frame_index,
      bond_scale: bondScale.value,
      seed_atoms: seeds,
      mode: 'connected',
      use_pbc: structureHasCell.value
    })
    if (!response.formulas.length) return
    const newRule: DynamicDisplayRule = {
      id: `rule_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
      enabled: true,
      type: 'formula',
      style,
      formulas: [...response.formulas]
    }
    handleDynamicRulesUpdate([...dynamicRules.value, newRule])
    ElMessage.success(t('viewer.dynamicRules.ruleAdded'))
  } catch (error) {
    console.warn('Failed to create dynamic formula rule.', error)
    ElMessage.error(t('viewer.fragmentQueryFailed'))
  }
}

function handleDynamicRulesUpdate(nextRules: DynamicDisplayRule[]) {
  dynamicRules.value = nextRules
  const hasEnabled = nextRules.some(r => r.enabled)
  if (!hasEnabled) {
    dynamicRuleMatchCounts.value = {}
    chemsshViewer?.setAllAtomsDisplayMode(lastBaseStyle.value)
    return
  }
  void evaluateDynamicRulesForFrame(currentFrame.value.frame_index)
}

async function evaluateDynamicRulesForFrame(frameIndex: number) {
  const preview = props.asePreview
  if (!preview || !chemsshViewer) return
  const enabledRules = dynamicRules.value.filter(r => r.enabled)
  if (!enabledRules.length) return

  const cacheKey = `${preview.path}|${frameIndex}|${bondScale.value.toFixed(2)}|${lastBaseStyle.value}|${structureHasCell.value ? 1 : 0}|${JSON.stringify(enabledRules)}`
  const cached = dynamicDisplayCache.get(cacheKey)
  if (cached) {
    dynamicRuleMatchCounts.value = cached.matchCounts
    dynamicAvailableFormulas.value = cached.formulas
    if (currentFrame.value.frame_index === frameIndex) {
      chemsshViewer.applyAtomModeCodes(cached.atomModes)
    }
    return
  }

  dynamicDisplayRequest?.abort()
  const controller = new AbortController()
  dynamicDisplayRequest = controller
  const requestGen = generation

  try {
    const response = await evaluateStructureDynamicDisplay(
      preview.source,
      {
        path: preview.path,
        format: preview.format,
        force: preview.size_limit_overridden === true,
        frame_index: frameIndex,
        bond_scale: bondScale.value,
        use_pbc: structureHasCell.value,
        default_style: lastBaseStyle.value,
        rules: enabledRules
      },
      { signal: controller.signal }
    )
    if (disposed || requestGen !== generation || controller.signal.aborted) return
    const modesArr = new Uint8Array(response.atom_modes)
    if (dynamicDisplayCache.size >= 128) {
      const firstKey = dynamicDisplayCache.keys().next().value
      if (firstKey !== undefined) dynamicDisplayCache.delete(firstKey)
    }
    dynamicDisplayCache.set(cacheKey, {
      atomModes: modesArr,
      matchCounts: response.rule_match_counts,
      formulas: response.available_formulas
    })
    if (currentFrame.value.frame_index === frameIndex) {
      dynamicRuleMatchCounts.value = response.rule_match_counts
      dynamicAvailableFormulas.value = response.available_formulas
      chemsshViewer.applyAtomModeCodes(modesArr)
    }
  } catch (error) {
    if (!(error instanceof Error && error.name === 'AbortError')) {
      console.warn('Dynamic display evaluation failed.', error)
      ElMessage.error(t('viewer.dynamicRules.evalFailed'))
    }
  } finally {
    if (dynamicDisplayRequest === controller) dynamicDisplayRequest = null
  }
}

function exportSelectedXYZ() {
  const preview = props.asePreview
  const frame = getCurrentFrame()
  const atoms = chemsshViewer?.getSelectedSourceAtomIndices() ?? []
  if (!preview || !frame || !atoms.length) return
  try {
    const basename = getBaseFilename(preview.path)
    const suffix = preview.is_trajectory ? `-frame-${frame.frame_index}-selected` : '-selected'
    const content = exportSelectedAtomsToXYZ(frame, atoms, basename)
    downloadTextFile(content, `${basename}${suffix}.xyz`, 'chemical/x-xyz')
  } catch (error) {
    console.error('Failed to export selected XYZ:', error)
  }
}

async function ensureWholeMoleculeWrapForFrame(frameIndex: number) {
  const preview = props.asePreview
  if (!preview || !chemsshViewer || wrapMode.value !== 'molecule' || !structureHasCell.value) return
  const cacheKey = `${preview.path}|${frameIndex}|${bondScale.value.toFixed(2)}`
  const cached = moleculeWrapCache.get(cacheKey)
  if (cached) {
    chemsshViewer.setMoleculeWrappedPositions(frameIndex, cached)
    return
  }

  wrapRequest?.abort()
  const controller = new AbortController()
  wrapRequest = controller
  const requestGen = generation
  try {
    const response = await queryStructureFragments(
      preview.source,
      {
        path: preview.path,
        format: preview.format,
        force: preview.size_limit_overridden === true,
        frame_index: frameIndex,
        bond_scale: bondScale.value,
        mode: 'whole_molecule_wrap',
        use_pbc: true
      },
      { signal: controller.signal }
    )
    if (disposed || requestGen !== generation || controller.signal.aborted) return
    if (response.wrapped_positions) {
      if (moleculeWrapCache.size >= 64) {
        const firstKey = moleculeWrapCache.keys().next().value
        if (firstKey !== undefined) moleculeWrapCache.delete(firstKey)
      }
      moleculeWrapCache.set(cacheKey, response.wrapped_positions)
      if (wrapMode.value === 'molecule' && currentFrame.value.frame_index === frameIndex) {
        chemsshViewer.setMoleculeWrappedPositions(frameIndex, response.wrapped_positions)
      }
    }
  } catch (error) {
    if (!(error instanceof Error && error.name === 'AbortError')) {
      console.warn('Whole-molecule wrap failed.', error)
    }
  } finally {
    if (wrapRequest === controller) wrapRequest = null
  }
}

function handleViewerKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return
  if (event.key === 'Escape') {
    if (contextMenu.visible) {
      closeContextMenu()
    } else if (selectedSourceAtoms.value.length > 0) {
      chemsshViewer?.clearSelection()
    }
    return
  }
  if ((event.ctrlKey || event.metaKey) && !event.altKey) {
    const lower = event.key.toLowerCase()
    if (lower === 'a') {
      event.preventDefault()
      chemsshViewer?.selectAllAtoms()
    } else if (lower === 'i') {
      event.preventDefault()
      chemsshViewer?.invertSelection()
    }
  }
}

function handleMetricChartClick(event: MouseEvent) {
  const preview = props.asePreview
  if (!preview?.is_trajectory || preview.n_frames < 2) return
  const svg = event.currentTarget as SVGSVGElement | null
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  if (rect.width <= 0) return
  const relX = ((event.clientX - rect.left) / rect.width) * metricChartWidth
  const plotWidth = metricChartWidth - metricChartPadding.left - metricChartPadding.right
  const ratio = Math.min(1, Math.max(0, (relX - metricChartPadding.left) / Math.max(1, plotWidth)))
  const targetFrame = Math.round(ratio * (preview.n_frames - 1))
  requestedFrameIndex.value = targetFrame
  void setFrame(targetFrame)
}

const canTrackGeometry = computed(() => {
  if (!props.asePreview?.is_trajectory) return false
  const len = selectedSourceAtoms.value.length
  return len >= 2 && len <= 4
})

function measureSelectedGeometryAt(positions: Float32Array, indices: readonly number[]): number | null {
  const getVec = (idx: number): [number, number, number] | null => {
    const off = idx * 3
    if (off + 2 >= positions.length) return null
    return [positions[off], positions[off + 1], positions[off + 2]]
  }
  if (indices.length === 2) {
    const a = getVec(indices[0])
    const b = getVec(indices[1])
    if (!a || !b) return null
    return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])
  }
  if (indices.length === 3) {
    const a = getVec(indices[0])
    const b = getVec(indices[1])
    const c = getVec(indices[2])
    if (!a || !b || !c) return null
    const ux = a[0] - b[0], uy = a[1] - b[1], uz = a[2] - b[2]
    const vx = c[0] - b[0], vy = c[1] - b[1], vz = c[2] - b[2]
    const denom = Math.hypot(ux, uy, uz) * Math.hypot(vx, vy, vz)
    if (denom <= 1e-12) return null
    const cos = Math.min(1, Math.max(-1, (ux * vx + uy * vy + uz * vz) / denom))
    return (Math.acos(cos) * 180) / Math.PI
  }
  if (indices.length === 4) {
    const p0 = getVec(indices[0])
    const p1 = getVec(indices[1])
    const p2 = getVec(indices[2])
    const p3 = getVec(indices[3])
    if (!p0 || !p1 || !p2 || !p3) return null
    const b0 = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]]
    const b1Raw = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]]
    const b1Len = Math.hypot(b1Raw[0], b1Raw[1], b1Raw[2]) || 1
    const b1 = [b1Raw[0] / b1Len, b1Raw[1] / b1Len, b1Raw[2] / b1Len]
    const b2 = [p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2]]
    const dot = (u: number[], v: number[]) => u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    const cross = (u: number[], v: number[]) => [
      u[1] * v[2] - u[2] * v[1],
      u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0]
    ]
    const d0 = dot(b0, b1)
    const d2 = dot(b2, b1)
    const v = [b0[0] - d0 * b1[0], b0[1] - d0 * b1[1], b0[2] - d0 * b1[2]]
    const w = [b2[0] - d2 * b1[0], b2[1] - d2 * b1[1], b2[2] - d2 * b1[2]]
    return (Math.atan2(dot(cross(b1, v), w), dot(v, w)) * 180) / Math.PI
  }
  return null
}

const geometryTrajectoryChart = computed(() => {
  void cacheRevision.value
  const preview = props.asePreview
  const atoms = selectedSourceAtoms.value
  if (!trackGeometry.value || !preview?.is_trajectory || preview.n_frames < 2) return null
  if (atoms.length < 2 || atoms.length > 4) return null

  const store = trajectoryStore
  if (!store || !store.positions.length) return null

  const nFrames = preview.n_frames
  const stride = Math.max(1, Math.ceil(nFrames / maxMetricPlotPoints))
  const samples: Array<{ index: number; value: number }> = []
  const frameSize = store.nAtoms * 3
  let minVal = Number.POSITIVE_INFINITY
  let maxVal = Number.NEGATIVE_INFINITY

  for (let frameIdx = 0; frameIdx < nFrames; frameIdx += stride) {
    if (store.availableFrames && store.availableFrames[frameIdx] !== 1) continue
    const slice = store.positions.subarray(frameIdx * frameSize, (frameIdx + 1) * frameSize)
    const val = measureSelectedGeometryAt(slice, atoms)
    if (val === null || !Number.isFinite(val)) continue
    samples.push({ index: frameIdx, value: val })
    if (val < minVal) minVal = val
    if (val > maxVal) maxVal = val
  }

  if (samples.length < 2) return null
  const span = maxVal - minVal
  const yMin = span === 0 ? minVal - 1 : minVal - span * 0.1
  const yMax = span === 0 ? maxVal + 1 : maxVal + span * 0.1
  const plotWidth = metricChartWidth - metricChartPadding.left - metricChartPadding.right
  const plotHeight = metricChartHeight - metricChartPadding.top - metricChartPadding.bottom
  const axisY = metricChartHeight - metricChartPadding.bottom

  const pts = samples.map(s => ({
    index: s.index,
    value: s.value,
    x: metricChartPadding.left + (s.index / (nFrames - 1)) * plotWidth,
    y: metricChartPadding.top + (1 - (s.value - yMin) / (yMax - yMin)) * plotHeight
  }))
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const areaPath = `${path} L ${pts[pts.length - 1].x.toFixed(1)} ${axisY.toFixed(1)} L ${pts[0].x.toFixed(1)} ${axisY.toFixed(1)} Z`

  const curIdx = currentFrame.value.frame_index
  let currentVal: number | null = null
  if (!store.availableFrames || store.availableFrames[curIdx] === 1) {
    const curSlice = store.positions.subarray(curIdx * frameSize, (curIdx + 1) * frameSize)
    currentVal = measureSelectedGeometryAt(curSlice, atoms)
  }
  const unit = atoms.length === 2 ? ' Å' : '°'
  const digits = atoms.length === 2 ? 3 : 1
  const label = atoms.length === 2
    ? t('viewer.geometryDistance')
    : atoms.length === 3
      ? t('viewer.geometryAngle')
      : t('viewer.geometryDihedral')

  const currentPoint = currentVal !== null && Number.isFinite(currentVal)
    ? {
        x: metricChartPadding.left + (curIdx / (nFrames - 1)) * plotWidth,
        y: metricChartPadding.top + (1 - (currentVal - yMin) / (yMax - yMin)) * plotHeight
      }
    : null

  return {
    label,
    currentDisplay: currentVal !== null && Number.isFinite(currentVal) ? `${currentVal.toFixed(digits)}${unit}` : 'N/A',
    path,
    areaPath,
    currentPoint
  }
})

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
    await renderChemSSHStructure(keepView, version, generation)
  } catch (error) {
    console.warn('ChemSSH viewer failed.', error)
    disposeChemSSHViewer()
  } finally {
    if (version === renderVersion) emit('render-complete')
  }
}

async function renderChemSSHStructure(keepView: boolean, version: number, readGeneration: number) {
  if (disposed || !container.value || !props.asePreview) return
  if (!chemsshViewer) {
    container.value.innerHTML = ''
    const { ChemSSHStructureViewer } = await loadChemSSHViewer()
    if (disposed || !container.value || version !== renderVersion || readGeneration !== generation) return
    chemsshViewer = new ChemSSHStructureViewer(container.value, {
      backgroundColor: props.backgroundColor,
      style: viewerStyle(),
      labelOptions: {
        showAtomIndex: showAtomIndex.value,
        showAtomTag: showAtomTag.value,
        atomIndexBase: atomIndexBase.value
      },
      onContextMenu: handleViewerContextMenu,
      onSelectionChange: atoms => {
        selectedSourceAtoms.value = atoms
      },
      onDisplayModeChange: (uniformMode, hidden) => {
        selectedStyle.value = uniformMode ?? ''
        if (uniformMode) lastBaseStyle.value = uniformMode
        hasHiddenAtoms.value = hidden
      },
      onAtomDoubleClick: atomIndex => {
        void runFragmentQuery('connected', { seedAtoms: [atomIndex] })
      }
    })
  }

  chemsshViewer.setStyle({
    bondScale: bondScale.value,
    backgroundColor: props.backgroundColor,
    showCell: true
  })
  chemsshViewer.setLabelOptions({
    showAtomIndex: showAtomIndex.value,
    showAtomTag: showAtomTag.value,
    atomIndexBase: atomIndexBase.value
  })
  chemsshViewer.setDisplayOptions(viewerDisplayOptions())

  if (trajectoryStore && props.asePreview.is_trajectory) {
    chemsshViewer.setTrajectory(trajectoryStore, {
      keepView,
      initialFrameIndex: currentFrame.value.frame_index
    })
    if (wrapMode.value === 'molecule') {
      void ensureWholeMoleculeWrapForFrame(currentFrame.value.frame_index)
    }
    if (activeDynamicRuleCount.value > 0) {
      void evaluateDynamicRulesForFrame(currentFrame.value.frame_index)
    }
    return
  }

  chemsshViewer.setStructure(frameToViewerFrame(currentFrame.value), { keepView })
  if (wrapMode.value === 'molecule') {
    void ensureWholeMoleculeWrapForFrame(currentFrame.value.frame_index)
  }
  if (activeDynamicRuleCount.value > 0) {
    void evaluateDynamicRulesForFrame(currentFrame.value.frame_index)
  }
}

function frameToViewerFrame(frame: CachedTrajectoryFrame): StructureFrame {
  if (isCompactAseFrame(frame)) {
    return {
      frameIndex: frame.frame_index,
      positions: frame.positions,
      cell: frame.cell,
      pbc: frame.pbc,
      tags: frame.tags,
      fixedMask: frame.fixed_mask,
      energy: frame.energy,
      fmax: frame.fmax,
      symbols: frame.symbols ?? props.asePreview?.frame.symbols ?? [],
      numbers: frame.numbers ?? props.asePreview?.frame.numbers ?? []
    }
  }
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

function dismissStructureWarning() {
  structureWarningDismissed.value = true
}

function handleExportCommand(command: string) {
  switch (command) {
    case 'original':
      exportOriginal()
      break
    case 'current-xyz':
      exportCurrentXYZ()
      break
    case 'current-xsd':
      exportCurrentXSD()
      break
    case 'trajectory-xyz':
      exportTrajectoryXYZ()
      break
    case 'trajectory-arc':
      exportTrajectoryArc()
      break
    case 'screenshot':
      exportPng()
      break
  }
}

function exportOriginal() {
  if (!props.asePreview) return
  const path = props.asePreview.path
  const url = downloadUrl(path)
  const link = document.createElement('a')
  link.href = url
  link.download = props.asePreview.name
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function exportCurrentXYZ() {
  if (!props.asePreview) return
  try {
    const basename = getBaseFilename(props.asePreview.path)
    const frame = getCurrentFrame()
    if (!frame) return
    const suffix = props.asePreview.is_trajectory ? `-frame-${frame.frame_index}` : ''
    const content = exportToXYZ(frame, basename)
    downloadTextFile(content, `${basename}${suffix}.xyz`, 'chemical/x-xyz')
  } catch (error) {
    console.error('Failed to export current XYZ:', error)
  }
}

function exportCurrentXSD() {
  if (!props.asePreview) return
  try {
    const basename = getBaseFilename(props.asePreview.path)
    const frame = getCurrentFrame()
    if (!frame) return
    const suffix = props.asePreview.is_trajectory ? `-frame-${frame.frame_index}` : ''
    const content = exportToXSD(frame, basename)
    downloadTextFile(content, `${basename}${suffix}.xsd`, 'chemical/x-xsd')
  } catch (error) {
    console.error('Failed to export current XSD:', error)
  }
}

function exportTrajectoryXYZ() {
  return exportTrajectory('xyz')
}

function exportTrajectoryArc() {
  return exportTrajectory('arc')
}

async function exportTrajectory(output: 'xyz' | 'arc') {
  const preview = props.asePreview
  if (!preview || exportRequest) return
  const controller = new AbortController()
  exportRequest = controller
  const exportGeneration = generation
  async function* frames(): AsyncGenerator<AseFrame> {
    for (let index = 0; index < preview!.n_frames; index += 1) {
      controller.signal.throwIfAborted()
      if (disposed || generation !== exportGeneration || props.asePreview !== preview) {
        throw new DOMException('Trajectory export cancelled', 'AbortError')
      }
      const cached = index === currentFrame.value.frame_index ? currentFrame.value : frameCache.get(index) ?? frameFromStore(index)
      const frame = cached
        ? materializeAseFrame(cached, preview!.frame.symbols, preview!.frame.numbers)
        : await readStructureFrame(preview!.source, preview!.path, index, preview!.format,
          preview!.size_limit_overridden === true, { signal: controller.signal })
      controller.signal.throwIfAborted()
      if (frame.frame_index !== index) throw new Error('Trajectory export received an unexpected frame')
      yield frame
    }
  }
  try {
    await downloadTrajectoryExport(frames(), output, `${getBaseFilename(preview.path)}.${output}`, controller.signal)
  } catch (error) {
    if (!(error instanceof Error && error.name === 'AbortError')) {
      ElMessage.error(t(error instanceof TrajectoryExportTooLargeError ? 'viewer.exportMemoryLimit' : 'viewer.exportFailed'))
    }
  } finally {
    if (exportRequest === controller) exportRequest = null
  }
}

function getCurrentFrame(): AseFrame | null {
  // Use the current frame ref directly, materializing compact typed-array frames on demand for export.
  if (currentFrame.value) {
    return materializeAseFrame(currentFrame.value, props.asePreview?.frame.symbols, props.asePreview?.frame.numbers)
  }
  return props.asePreview?.frame || null
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
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A'
  return `${value.toFixed(6)}${unit}`
}

function buildMetricCurve(
  key: TrajectoryMetricKey,
  label: string,
  color: string,
  areaColor: string
): TrajectoryMetricCurve | null {
  const preview = props.asePreview
  if (!preview?.is_trajectory || preview.n_frames < 2) return null

  const series = collectMetricSamples(key, preview.n_frames)
  if (!series || series.count < 2 || series.samples.length < 2) return null

  const minValue = series.min
  const maxValue = series.max
  const span = maxValue - minValue
  const yMin = span === 0 ? minValue - 1 : minValue - span * 0.08
  const yMax = span === 0 ? maxValue + 1 : maxValue + span * 0.08
  const plotWidth = metricChartWidth - metricChartPadding.left - metricChartPadding.right
  const plotHeight = metricChartHeight - metricChartPadding.top - metricChartPadding.bottom

  const points = series.samples.map(sample => {
    const x = metricChartPadding.left + (sample.index / (preview.n_frames - 1)) * plotWidth
    const y = metricChartPadding.top + (1 - (sample.value - yMin) / (yMax - yMin)) * plotHeight
    return { index: sample.index, value: sample.value, display: frameIndexToDisplayValue(sample.index), x, y }
  })
  const minX = metricChartPadding.left + (series.minPoint.index / (preview.n_frames - 1)) * plotWidth
  const minY = metricChartPadding.top + (1 - (series.minPoint.value - yMin) / (yMax - yMin)) * plotHeight
  const min: TrajectoryMetricPoint = {
    index: series.minPoint.index,
    value: series.minPoint.value,
    display: frameIndexToDisplayValue(series.minPoint.index),
    x: minX,
    y: minY
  }
  if (!points.some(point => point.index === min.index)) {
    points.push(min)
    points.sort((left, right) => left.index - right.index)
  }
  if (points.length < 2) return null

  const path = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${roundSvg(point.x)} ${roundSvg(point.y)}`).join(' ')
  const axisY = metricChartHeight - metricChartPadding.bottom
  const areaPath = `${path} L ${roundSvg(points[points.length - 1].x)} ${axisY} L ${roundSvg(points[0].x)} ${axisY} Z`
  const anchor = min.x > metricChartWidth - 42 ? 'end' : 'start'
  const labelX = anchor === 'end' ? min.x - 4 : min.x + 4
  const labelY = min.y > metricChartPadding.top + 9 ? min.y - 4 : min.y + 10

  return {
    key,
    label,
    color,
    areaColor,
    sampled: series.sampled,
    path,
    areaPath,
    min: {
      ...min,
      labelX: clampNumber(labelX, metricChartPadding.left, metricChartWidth - metricChartPadding.right),
      labelY: clampNumber(labelY, metricChartPadding.top + 6, axisY - 2),
      anchor
    }
  }
}

function collectMetricSamples(key: TrajectoryMetricKey, nFrames: number) {
  const samples = new Map<number, TrajectoryMetricSample>()
  const sampled = nFrames > metricSamplingFrameThreshold
  const sampleEvery = sampled ? Math.max(1, Math.floor(nFrames / maxMetricPlotPoints)) : 1
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY
  let count = 0
  let minPoint: TrajectoryMetricSample | null = null
  let firstPoint: TrajectoryMetricSample | null = null
  let lastPoint: TrajectoryMetricSample | null = null

  const visit = (index: number, rawValue: number | null | undefined) => {
    const value = finiteOrNaN(rawValue)
    if (!Number.isFinite(value) || index < 0 || index >= nFrames) return false
    const point = { index, value }
    count += 1
    min = Math.min(min, value)
    max = Math.max(max, value)
    if (!minPoint || value < minPoint.value) minPoint = point
    if (!firstPoint || index < firstPoint.index) firstPoint = point
    if (!lastPoint || index > lastPoint.index) lastPoint = point
    if (index === 0 || index === nFrames - 1 || index % sampleEvery === 0) samples.set(index, point)
    return true
  }

  const storeValues = trajectoryStore?.[key]
  if (storeValues) {
    for (let index = 0; index < Math.min(nFrames, storeValues.length); index += 1) {
      visit(index, storeValues[index])
    }
  } else {
    const visited = new Set<number>()
    for (const frame of frameCache.values()) {
      if (visit(frame.frame_index, frame[key])) visited.add(frame.frame_index)
    }
    const currentIndex = currentFrame.value.frame_index
    if (!visited.has(currentIndex)) visit(currentIndex, currentFrame.value[key])
  }

  const firstSample = firstPoint as TrajectoryMetricSample | null
  const lastSample = lastPoint as TrajectoryMetricSample | null
  const minSample = minPoint as TrajectoryMetricSample | null
  if (!minSample || !firstSample || !lastSample) return null
  samples.set(firstSample.index, firstSample)
  samples.set(lastSample.index, lastSample)
  samples.set(minSample.index, minSample)
  return {
    min,
    max,
    count,
    minPoint: minSample,
    sampled,
    samples: [...samples.values()].sort((left, right) => left.index - right.index)
  }
}

function roundSvg(value: number) {
  return Number(value.toFixed(2))
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function scheduleFrameChange() {
  if (!props.asePreview) return
  scheduledFrame = clampFrameIndex(Number(requestedFrameIndex.value))
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
  closeContextMenu()
  fragmentRequest?.abort()
  fragmentRequest = null
  wrapRequest?.abort()
  wrapRequest = null
  dynamicDisplayRequest?.abort()
  dynamicDisplayRequest = null
  moleculeWrapCache.clear()
  dynamicDisplayCache.clear()
  dynamicPanelOpen.value = false
  dynamicRules.value = []
  dynamicRuleMatchCounts.value = {}
  dynamicAvailableFormulas.value = []
  selectedSourceAtoms.value = []
  hasHiddenAtoms.value = false
  followSelection.value = false
  trackGeometry.value = false
  selectedStyle.value = lastBaseStyle.value
  chemsshViewer?.resetAtomStates()
  chemsshViewer?.resetView()
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

function hasUsableCell(cell: Float32Array | number[][] | undefined) {
  if (!cell) return false
  if (cell instanceof Float32Array) {
    if (cell.length < 9) return false
    const ax = cell[0] ?? 0
    const ay = cell[1] ?? 0
    const az = cell[2] ?? 0
    const bx = cell[3] ?? 0
    const by = cell[4] ?? 0
    const bz = cell[5] ?? 0
    const cx = cell[6] ?? 0
    const cy = cell[7] ?? 0
    const cz = cell[8] ?? 0
    const det = ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return Math.abs(det) > 1e-10
  }
  if (cell.length < 3) return false
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
  if (!preview || !props.active || disposed) return
  foregroundRequest?.abort()
  foregroundRequest = null
  cancelBackgroundRequest()
  const target = clampFrameIndex(index)
  requestedFrameIndex.value = target
  const requestVersion = ++frameLoadVersion
  const readGeneration = generation
  const isCurrent = () => !disposed && props.active && generation === readGeneration
    && props.asePreview === preview && requestVersion === frameLoadVersion && requestedFrameIndex.value === target
  if (target === currentFrame.value.frame_index) {
    clearFrameLoading(requestVersion)
    warmFramesAround(target)
    return
  }

  if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, target)) {
    applyTrajectoryFrame(target, requestVersion)
    return
  }
  const cachedFrame = frameCache.take(target)
  if (cachedFrame) {
    clearFrameLoading(requestVersion)
    applyCachedFrame(cachedFrame)
    await renderStructure(true)
    if (isCurrent()) warmFramesAround(target)
    return
  }

  const controller = new AbortController()
  foregroundRequest = controller
  const context: FrameReadContext = { preview, generation: readGeneration, signal: controller.signal }
  showFrameLoading(requestVersion)
  try {
    const result = await readFrameForDisplay(target, context)
    if (!isCurrent() || controller.signal.aborted) return
    if (trajectoryStore && isStoreFrameAvailable(trajectoryStore, target)) {
      applyTrajectoryFrame(target, requestVersion)
    } else if (result.frame) {
      applyCachedFrame(result.frame)
      await renderStructure(true)
    }
    if (isCurrent()) warmFramesAround(target, result.nextIndex)
  } catch (error) {
    if (isCurrent() && !controller.signal.aborted) console.warn('Failed to load trajectory frame.', error)
  } finally {
    if (foregroundRequest === controller) foregroundRequest = null
    if (frameLoadingVersion === requestVersion) clearFrameLoading(requestVersion)
  }
}

function applyCachedFrame(frame: CachedTrajectoryFrame) {
  const previous = currentFrame.value
  frameCache.take(frame.frame_index)
  // The displayed frame is the sole unbudgeted frame; it need not fit the cache.
  currentFrame.value = frame
  if (!trajectoryStore && previous.frame_index !== frame.frame_index) frameCache.set(previous)
  updateCachedFrameCount()
}

function showFrameLoading(version: number) {
  frameLoadingVersion = version
  if (frameLoadingTimer !== null) {
    window.clearTimeout(frameLoadingTimer)
    frameLoadingTimer = null
  }
  frameLoadingTimer = window.setTimeout(() => {
    frameLoadingTimer = null
    if (frameLoadingVersion === version) frameLoading.value = true
  }, frameLoadingDelayMs)
}

function clearFrameLoading(version: number) {
  frameLoadingVersion = version
  if (frameLoadingTimer !== null) {
    window.clearTimeout(frameLoadingTimer)
    frameLoadingTimer = null
  }
  frameLoading.value = false
}

function applyTrajectoryFrame(index: number, requestVersion = frameLoadVersion) {
  if (requestVersion !== frameLoadVersion || requestedFrameIndex.value !== index) return
  const frame = frameFromStore(index)
  if (!frame) return
  currentFrame.value = frame
  requestedFrameIndex.value = index
  clearFrameLoading(requestVersion)
  chemsshViewer?.setFrame(index)
  if (wrapMode.value === 'molecule') {
    void ensureWholeMoleculeWrapForFrame(index)
  }
  if (activeDynamicRuleCount.value > 0) {
    void evaluateDynamicRulesForFrame(index)
  }
}

function canUseBinaryStream(preview: AsePreviewResponse) {
  return preview.transport === 'binary-available'
}

function canUseFixedBinaryStore(preview: AsePreviewResponse) {
  return canUseBinaryStream(preview) && preview.topology_stable
}

async function preloadTrajectoryFrames(version: number) {
  const preview = props.asePreview
  if (!props.active || !preview?.is_trajectory || disposed) return
  if (trajectoryStore) {
    if (trajectoryStore.availableFrames?.every(value => value === 1)) return
    await streamBinaryTrajectoryFrames(version, preview)
    return
  }
  warmFramesAround(currentFrame.value.frame_index)
}

async function streamBinaryTrajectoryFrames(version: number, preview: AsePreviewResponse) {
  const store = trajectoryStore
  const readGeneration = generation
  if (!store) return
  closeActiveEventSource()
  cancelBackgroundRequest()

  await new Promise<void>((resolve) => {
    let es: EventSource | null = null
    let finished = false
    const finish = () => {
      if (finished) return
      finished = true
      es?.close()
      if (finishActiveStream === finish) finishActiveStream = null
      resolve()
    }
    finishActiveStream = finish
    try {
      es = streamStructureFrames(
        preview.source,
        preview.path,
        chunk => {
          if (finished) return
          if (disposed || generation !== readGeneration || version !== preloadVersion || !props.active
            || props.asePreview !== preview || trajectoryStore !== store) {
            finish()
            return
          }
          if (chunk.header.frame_encoding || chunk.header.n_atoms !== store.nAtoms) {
            finish()
            return
          }
          writeChunkToStore(chunk)
          updateCachedFrameCount()
        },
        finish,
        finish,
        preview.format,
        preview.size_limit_overridden === true,
        streamChunkSize
      )
      if (finished) es.close()
    } catch {
      finish()
    }
  })
}

function closeActiveEventSource() {
  finishActiveStream?.()
}

function cancelBackgroundRequest() {
  backgroundRequest?.abort()
  backgroundRequest = null
}

function assertReadActive(context: FrameReadContext) {
  if (disposed || context.signal.aborted || context.generation !== generation
    || !props.active || props.asePreview !== context.preview) {
    throw new DOMException('Trajectory request cancelled', 'AbortError')
  }
}

async function readFrameForDisplay(index: number, context: FrameReadContext, count = chunkSize): Promise<FrameReadResult> {
  assertReadActive(context)
  const preview = context.preview
  if (preview.is_trajectory) {
    if (canUseBinaryStream(preview)) {
      try {
        // Fixed topology without a dense reservation uses the same detached-frame cache.
        return trajectoryStore
          ? await ensureChunk(index, context, count)
          : await ensureVariableChunk(index, context, count)
      } catch {
        assertReadActive(context)
      }
    }
    try {
      return await ensureJsonChunk(index, context, count)
    } catch {
      assertReadActive(context)
    }
  }
  const frame = await readStructureFrame(preview.source, preview.path, index, preview.format,
    preview.size_limit_overridden === true, { signal: context.signal })
  assertReadActive(context)
  if (frame.frame_index !== index) throw new Error('Trajectory response does not contain the requested frame')
  if (trajectoryStore) {
    writeFrameToStore(trajectoryStore, frameToViewerFrame(frame))
    updateCachedFrameCount()
  }
  return { frame, nextIndex: index + 1 }
}

async function readBinaryChunk(index: number, context: FrameReadContext, count: number) {
  const preview = context.preview
  const range = trajectoryChunkRequest(index, preview.n_frames, count)
  const chunk = await readStructureFrameChunk(preview.source, preview.path, range.start, range.count,
    preview.format, preview.size_limit_overridden === true, { signal: context.signal })
  assertReadActive(context)
  const nextIndex = nextTrajectoryChunkIndex(chunk.header.start, chunk.header.count, preview.n_frames)
  if (index < chunk.header.start || index >= nextIndex) throw new Error('Trajectory chunk misses the requested frame')
  return { chunk, nextIndex }
}

async function ensureChunk(index: number, context: FrameReadContext, count: number): Promise<FrameReadResult> {
  const { chunk, nextIndex } = await readBinaryChunk(index, context, count)
  assertReadActive(context)
  if (!trajectoryStore || chunk.header.frame_encoding || chunk.header.n_atoms !== trajectoryStore.nAtoms) {
    throw new Error('Trajectory topology changed')
  }
  writeChunkToStore(chunk)
  updateCachedFrameCount()
  return { frame: null, nextIndex }
}

async function ensureVariableChunk(index: number, context: FrameReadContext, count: number): Promise<FrameReadResult> {
  const { chunk, nextIndex } = await readBinaryChunk(index, context, count)
  assertReadActive(context)
  const frame = writeVariableChunkToCache(chunk, index)
  if (!frame) throw new Error('Trajectory chunk misses the requested frame')
  return { frame, nextIndex }
}

async function ensureJsonChunk(index: number, context: FrameReadContext, count: number): Promise<FrameReadResult> {
  const preview = context.preview
  const range = trajectoryChunkRequest(index, preview.n_frames, count)
  const chunk = await readStructureFrameJsonChunk(preview.source, preview.path, range.start, range.count,
    preview.format, preview.size_limit_overridden === true, { signal: context.signal })
  assertReadActive(context)
  const nextIndex = nextTrajectoryChunkIndex(chunk.start, chunk.count, preview.n_frames)
  if (chunk.frames.length !== chunk.count || chunk.frames.some((item, offset) => item.frame_index !== chunk.start + offset)) {
    throw new Error('Trajectory JSON chunk is not contiguous')
  }
  const frame = chunk.frames.find(item => item.frame_index === index)
  if (index < chunk.start || index >= nextIndex || !frame) throw new Error('Trajectory chunk misses the requested frame')
  for (const item of chunk.frames) {
    if (trajectoryStore) writeFrameToStore(trajectoryStore, frameToViewerFrame(item))
    else if (item.frame_index !== index) cacheFrame(item)
  }
  updateCachedFrameCount()
  return { frame, nextIndex }
}

function computeWarmTargets(index: number, nFrames: number, nextIndex: number): Array<{ start: number; count: number }> {
  const lowWatermark = Math.max(1, Math.floor(chunkSize / 2))
  const targets: Array<{ start: number; count: number }> = []

  // Forward runway check: count contiguous cached frames immediately after `index`.
  let forwardCursor = Math.max(index + 1, nextIndex)
  const forwardHorizon = Math.min(nFrames, index + chunkSize + 1)
  while (forwardCursor < forwardHorizon && frameCache.has(forwardCursor)) {
    forwardCursor += 1
  }
  const forwardRunway = forwardCursor - (index + 1)
  if (forwardCursor < nFrames && forwardRunway < lowWatermark) {
    const count = Math.min(chunkSize, nFrames - forwardCursor)
    if (count > 0) targets.push({ start: forwardCursor, count })
  }

  // Backward runway check: count contiguous cached frames immediately before `index`.
  let backwardCursor = index - 1
  const backwardHorizon = Math.max(0, index - chunkSize)
  while (backwardCursor >= backwardHorizon && frameCache.has(backwardCursor)) {
    backwardCursor -= 1
  }
  const backwardRunway = (index - 1) - backwardCursor
  if (backwardCursor >= 0 && backwardRunway < lowWatermark) {
    const start = Math.max(0, backwardCursor - chunkSize + 1)
    const count = backwardCursor - start + 1
    if (count > 0) targets.push({ start, count })
  }

  return targets
}

function warmFramesAround(index: number, nextIndex = index + 1) {
  const preview = props.asePreview
  if (disposed || !props.active || !preview?.is_trajectory || trajectoryStore) return
  cancelBackgroundRequest()
  const targets = computeWarmTargets(index, preview.n_frames, nextIndex)
  if (targets.length === 0) return
  const controller = new AbortController()
  backgroundRequest = controller
  const context: FrameReadContext = { preview, generation, signal: controller.signal }
  // Bounded bidirectional neighbor prefetch (at most one forward + one backward chunk), never scanning the trajectory.
  void (async () => {
    try {
      for (const target of targets) {
        assertReadActive(context)
        const result = await readFrameForDisplay(target.start, context, target.count)
        assertReadActive(context)
        if (result.frame) cacheFrame(result.frame)
      }
    } catch {
      // Cancelled or transient background prefetch failure; foreground reads will retry on demand.
    } finally {
      if (backgroundRequest === controller) backgroundRequest = null
    }
  })()
}

function createTrajectoryStore(preview: AsePreviewResponse): TrajectoryStore | null {
  if (!preview.is_trajectory || !canUseFixedBinaryStore(preview)) return null
  const bytes = estimateDenseTrajectoryBytes(preview.n_frames, preview.n_atoms, preview.frame)
  if (!frameCache.reserveDense(bytes)) return null
  try {
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
  } catch {
    frameCache.releaseDense()
    return null
  }
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
  const currentIndex = currentFrame.value.frame_index
  if (currentIndex >= start && currentIndex < start + count) {
    const frame = frameFromStore(currentIndex)
    if (frame) currentFrame.value = frame
    chemsshViewer?.setFrame(currentIndex)
  }
}

function writeVariableChunkToCache(chunk: AseFrameChunk, target: number): CachedTrajectoryFrame | null {
  const sharedSymbols = props.asePreview?.frame.symbols ?? null
  const sharedNumbers = props.asePreview?.frame.numbers ?? null
  let requested: CachedTrajectoryFrame | null = null
  for (let localIndex = 0; localIndex < chunk.header.count; localIndex += 1) {
    const frame = compactFrameFromStructureChunk(chunk, localIndex, sharedSymbols, sharedNumbers)
    if (!frame) continue
    if (frame.frame_index === target) requested = frame
    else cacheFrame(frame)
  }
  return requested
}

function updateCachedFrameCount() {
  cacheRevision.value += 1
  const fixedCount = trajectoryStore?.availableFrames?.reduce((total, value) => total + value, 0)
  cachedFrameCount.value = fixedCount ?? frameCache.size + (props.asePreview ? 1 : 0)
}

function cacheFrame(frame: CachedTrajectoryFrame) {
  if (frame.frame_index !== currentFrame.value.frame_index) frameCache.set(frame)
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
  return value === null || value === undefined || !Number.isFinite(value) ? Number.NaN : value
}

function clampFrameIndex(index: number) {
  const max = Math.max(0, (props.asePreview?.n_frames ?? 1) - 1)
  if (!Number.isFinite(index)) return currentFrame.value.frame_index
  return Math.min(max, Math.max(0, Math.round(index)))
}

function resetAseState() {
  exportRequest?.abort()
  exportRequest = null
  generation += 1
  renderVersion += 1
  pauseTrajectoryPreload()
  disposeChemSSHViewer()
  trajectoryStore = null
  frameCache.reset()
  const frame = props.asePreview?.frame ?? emptyFrame()
  currentFrame.value = frame
  requestedFrameIndex.value = frame.frame_index
  trajectoryStore = props.asePreview ? createTrajectoryStore(props.asePreview) : null
  isOnDemandTrajectory.value = Boolean(props.asePreview?.is_trajectory && !trajectoryStore)
  updateCachedFrameCount()
  startTrajectoryPreload()
}

function pauseTrajectoryPreload() {
  preloadVersion += 1
  frameLoadVersion += 1
  closeActiveEventSource()
  foregroundRequest?.abort()
  foregroundRequest = null
  cancelBackgroundRequest()
  clearFrameLoading(frameLoadVersion)
  if (frameRequestHandle) window.cancelAnimationFrame(frameRequestHandle)
  frameRequestHandle = 0
  scheduledFrame = null
}

function startTrajectoryPreload() {
  if (!props.active || !props.asePreview?.is_trajectory) return
  const version = ++preloadVersion
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
  exportRequest?.abort()
  exportRequest = null
  fragmentRequest?.abort()
  fragmentRequest = null
  wrapRequest?.abort()
  wrapRequest = null
  dynamicDisplayRequest?.abort()
  dynamicDisplayRequest = null
  moleculeWrapCache.clear()
  dynamicDisplayCache.clear()
  disposed = true
  generation += 1
  renderVersion += 1
  pauseTrajectoryPreload()
  resizeObserver?.disconnect()
  resizeObserver = null
  disposeChemSSHViewer()
  trajectoryStore = null
  frameCache.dispose()
  currentFrame.value = emptyFrame()
  viewerModulePromise = null
})

watch(
  () => props.asePreview,
  () => {
    structureWarningDismissed.value = false
    resetStructureSwitchState()
    resetAseState()
    void renderStructure()
  }
)

watch(
  showStructureWarning,
  visible => {
    if (!visible) structureWarningDismissed.value = false
  }
)

watch(
  () => props.active,
  async active => {
    if (!active) {
      pauseTrajectoryPreload()
      return
    }
    await nextTick()
    resizeViewer()
    startTrajectoryPreload()
  },
  { flush: 'post' }
)

// Optimize: Combine style and display option watches into a single watchEffect
watchEffect(() => {
  // Track dependencies first
  const styleChanged = [bondScale.value, showAtomIndex.value, showAtomTag.value, atomIndexBase.value]
  const displayChanged = [supercellX.value, supercellY.value, supercellZ.value, wrapMode.value, structureHasCell.value]

  // Early return if viewer not ready, but still track dependencies
  if (!chemsshViewer || !props.asePreview) {
    // If viewer doesn't exist but dependencies changed, trigger re-render
    void styleChanged
    void displayChanged
    void renderStructure(true)
    return
  }

  // Keep cell-only controls constrained without blocking atom labels or bond styling.
  if (!structureHasCell.value) {
    if (supercellX.value !== 1 || supercellY.value !== 1 || supercellZ.value !== 1) resetSupercell()
    if (wrapMode.value !== 'off') wrapMode.value = 'off'
  } else {
    clampSupercell()
  }

  // Apply updates to viewer without clobbering per-atom mixed display modes
  chemsshViewer.setStyle({
    bondScale: bondScale.value,
    backgroundColor: props.backgroundColor,
    showCell: true
  })
  chemsshViewer.setLabelOptions({
    showAtomIndex: showAtomIndex.value,
    showAtomTag: showAtomTag.value,
    atomIndexBase: atomIndexBase.value
  })
  chemsshViewer.setDisplayOptions(viewerDisplayOptions())
  if (wrapMode.value === 'molecule' && structureHasCell.value) {
    void ensureWholeMoleculeWrapForFrame(currentFrame.value.frame_index)
  }
  if (activeDynamicRuleCount.value > 0) {
    void evaluateDynamicRulesForFrame(currentFrame.value.frame_index)
  }
})
</script>

<style scoped>
.dynamic-rule-btn-wrap {
  position: relative;
  display: inline-flex;
}

.dynamic-rule-badge {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--el-color-danger, #ef4444);
  color: #ffffff;
  font-size: 10px;
  font-weight: 700;
  line-height: 15px;
  text-align: center;
  pointer-events: none;
}

.wrap-settings-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wrap-mode-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.wrap-mode-group :deep(.el-radio) {
  margin-right: 0;
  height: auto;
}

.viewer-geometry-track {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 2px;
}

.viewer-metric-svg.is-clickable {
  cursor: pointer;
}

.radius-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.radius-dialog-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>

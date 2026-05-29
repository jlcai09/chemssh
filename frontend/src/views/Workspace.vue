<template>
  <div
    ref="workspaceRef"
    class="workspace-view"
    :class="{ 'is-resizing': Boolean(activeResize), 'is-drag-upload': dragUploadActive }"
    :style="workspaceStyle"
    @dragenter="handleWorkspaceDragEnter"
    @dragover="handleWorkspaceDragOver"
    @dragleave="handleWorkspaceDragLeave"
    @drop="handleWorkspaceDrop"
  >
    <section ref="leftPaneRef" class="workspace-left">
      <div class="path-bar">
        <el-input
          v-model="pathInput"
          class="path-input"
          size="small"
          clearable
          spellcheck="false"
          @keyup.enter="openPathFromInput"
          @clear="openDirectory()"
        >
          <template #append>
            <el-tooltip :content="t('toolbar.go')" placement="bottom">
              <el-button :icon="ArrowRight" @click="openPathFromInput" />
            </el-tooltip>
          </template>
        </el-input>
      </div>

      <FileToolbar
        :selected-items="selectedItems"
        :can-go-up="Boolean(listing?.parent)"
        :show-hidden-files="showHiddenFiles"
        @refresh="loadDirectory(currentPath)"
        @go-up="goUp"
        @mkdir="promptMkdir"
        @upload="handleUpload"
        @download="downloadSelected"
        @rename="promptRename"
        @delete="confirmDelete"
        @update:show-hidden-files="setShowHiddenFiles"
      />

      <div class="file-table-shell" v-loading="loadingFiles">
        <FileTree
          :items="visibleItems"
          :selected-items="selectedItems"
          :preview-providers="previewProviders"
          @selection-change="handleSelectionChange"
          @context-menu="openFileContextMenu"
          @open="openItem"
        />
      </div>
    </section>

    <div
      class="pane-splitter pane-splitter-vertical left-splitter"
      role="separator"
      :aria-label="t('resize.fileList')"
      tabindex="0"
      @pointerdown="startColumnResize('left', $event)"
      @dblclick="resetColumnLayout"
    />

    <section ref="mainPaneRef" class="workspace-main">
      <TerminalPanel
        class="workspace-terminal"
        :initial-cwd="terminalInitialPath"
        :current-file-manager-path="currentPath"
        :layout-version="terminalLayoutVersion"
        @cwd-change="openDirectoryFromTerminal"
      />
    </section>

    <div
      class="pane-splitter pane-splitter-vertical right-splitter"
      role="separator"
      :aria-label="t('resize.previewSide')"
      tabindex="0"
      @pointerdown="startColumnResize('right', $event)"
      @dblclick="resetColumnLayout"
    />

    <aside ref="sidePaneRef" class="workspace-side" :style="sideStyle">
      <section class="side-work-panel">
        <div class="side-panel-tabbar">
          <button
            v-for="panel in workPanels"
            :key="panel.id"
            class="side-panel-tab"
            :class="{ 'is-active': panel.id === activeWorkPanelId }"
            type="button"
            draggable="true"
            @click="activeWorkPanelId = panel.id"
            @dragstart="onWorkPanelDragStart(panel.id, $event)"
            @dragover="onWorkPanelDragOver(panel.id, $event)"
            @drop="onWorkPanelDrop(panel.id, $event)"
          >
            <span>{{ panelTitle(panel) }}</span>
            <el-tooltip :content="t('panel.close')" placement="bottom">
              <el-button
                class="side-panel-close"
                :icon="Close"
                circle
                size="small"
                text
                @click.stop="closeWorkPanel(panel.id)"
              />
            </el-tooltip>
          </button>
          <el-dropdown trigger="click" @command="openWorkPanelCommand">
            <el-button class="side-panel-add" :icon="Plus" circle size="small" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="builtin:preview">{{ t('preview.type.preview') }}</el-dropdown-item>
                <el-dropdown-item command="builtin:queue">{{ props.systemInfo?.scheduler?.toUpperCase() ?? t('queue.title') }}</el-dropdown-item>
                <el-dropdown-item
                  v-for="item in pluginPanelCommands"
                  :key="item.command"
                  :command="item.command"
                  divided
                >
                  {{ item.title }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="side-panel-body">
          <FilePreview
            v-if="activeWorkPanel?.kind === 'preview'"
            :file="preview"
            :ase-structure="asePreview"
            :mode="previewMode"
            :loading="previewLoading"
            :structure-candidate="structurePreviewCandidate"
            :structure-error="previewError"
            @update:mode="setPreviewMode"
            @refresh="refreshPreview"
            @save="savePreview"
            @dragover="handlePreviewDragOver"
            @drop="handlePreviewDrop"
          />
          <QueueStatus
            v-else-if="activeWorkPanel?.kind === 'queue'"
            class="side-queue"
            :initial-interval="5"
            :workspace-root="props.systemInfo?.workspace_root"
            @open-workdir="openQueueWorkdir"
          />
          <iframe
            v-else-if="activeWorkPanel?.kind === 'plugin'"
            class="plugin-panel-frame"
            :src="activeWorkPanel.assetUrl"
            :title="activeWorkPanel.title"
            @load="handlePluginFrameLoad($event, activeWorkPanel)"
          />
          <div v-else class="empty-state">
            <el-empty :description="t('panel.empty')" />
          </div>
        </div>
      </section>

      <div
        class="pane-splitter pane-splitter-horizontal side-splitter"
        role="separator"
        :aria-label="t('resize.queueLog')"
        tabindex="0"
        @pointerdown="startSideResize"
        @dblclick="resetSideLayout"
      />

      <LogViewer class="side-log" :path="logPath" />
    </aside>

    <div v-if="dragUploadActive" class="workspace-drop-overlay" aria-live="polite">
      <el-icon><UploadFilled /></el-icon>
      <span>{{ t('file.dropUpload') }}</span>
    </div>

    <div
      v-if="uploadState.active"
      class="upload-progress-widget"
      :class="{ 'is-open': uploadProgressOpen }"
      @mouseenter="uploadProgressOpen = true"
      @mouseleave="uploadProgressOpen = false"
    >
      <button
        class="upload-progress-orb"
        type="button"
        :aria-label="t('upload.progress')"
        @focus="uploadProgressOpen = true"
        @blur="uploadProgressOpen = false"
      >
        <span class="upload-progress-ring" />
        <span class="upload-progress-value">{{ uploadPercent }}%</span>
      </button>
      <div v-if="uploadProgressOpen" class="upload-progress-panel" role="status">
        <div class="upload-progress-title">{{ t('upload.progress') }}</div>
        <div class="upload-progress-file" :title="uploadState.currentFile">{{ uploadState.currentFile }}</div>
        <div class="upload-progress-bar" aria-hidden="true">
          <span :style="{ width: `${uploadPercent}%` }" />
        </div>
        <div class="upload-progress-meta">
          <span>{{ uploadPercent }}%</span>
          <span>{{ uploadSpeedLabel }}</span>
          <span>{{ uploadState.done }}/{{ uploadState.totalFiles }}</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="uploadConflictDialog.visible" class="upload-conflict-backdrop">
        <div class="upload-conflict-dialog" role="dialog" aria-modal="true">
          <div class="upload-conflict-title">{{ t('upload.conflictTitle') }}</div>
          <p>{{ t('upload.conflictMessage', { name: uploadConflictDialog.name }) }}</p>
          <label class="upload-conflict-apply">
            <input v-model="uploadConflictDialog.applyAll" type="checkbox" />
            <span>{{ t('upload.applyAll') }}</span>
          </label>
          <div class="upload-conflict-actions">
            <el-button type="primary" @click="chooseUploadConflict('overwrite')">{{ t('upload.overwrite') }}</el-button>
            <el-button @click="chooseUploadConflict('skip')">{{ t('upload.skip') }}</el-button>
            <el-button @click="chooseUploadConflict('suffix')">{{ t('upload.renameNew') }}</el-button>
            <el-button @click="chooseUploadConflict('cancel')">{{ t('common.cancel') }}</el-button>
          </div>
        </div>
      </div>

      <div
        v-if="contextMenu.visible"
        class="file-context-menu"
        :class="{ 'opens-left': contextMenu.opensLeft }"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
        role="menu"
        @click.stop
        @contextmenu.prevent
      >
        <div class="context-menu-item has-submenu" role="menuitem" tabindex="0">
          <el-icon><Promotion /></el-icon>
          <span>{{ t('context.submitQueue') }}</span>
          <el-icon class="submenu-arrow"><ArrowRight /></el-icon>
          <div class="context-submenu" role="menu">
            <button class="context-menu-item" type="button" role="menuitem" @click="submitContextJob('qsub')">
              qsub
            </button>
            <button class="context-menu-item" type="button" role="menuitem" @click="submitContextJob('sbatch')">
              sbatch
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, Close, Plus, Promotion, UploadFilled } from '@element-plus/icons-vue'
import {
  deletePath,
  downloadArchive,
  listFiles,
  makeDirectory,
  readFile,
  renamePath,
  uploadFile,
  writeFile,
  type DirectoryListing,
  type FileItem,
  type FileReadResponse,
  type UploadProgress
} from '../api/files'
import { API_BASE, ApiError, downloadUrl, request } from '../api/http'
import { hasChemwebFileDrag, readChemwebFileDrag } from '../api/fileDrag'
import {
  providerMatchesItem,
  type FilePreviewProvider,
  type PreviewProbeResponse
} from '../api/filePreviewProviders'
import { submitJob, type SubmitCommand } from '../api/jobs'
import { activatePlugin, deactivatePlugin, listPlugins, type PluginManifest } from '../api/plugins'
import { ASE_STRUCTURE_SOURCE, readStructurePreview } from '../api/structures'
import type { SystemInfo } from '../api/system'
import type { AsePreviewResponse, StructureSource } from '../types/structure'
import FilePreview from '../components/FilePreview.vue'
import FileToolbar from '../components/FileToolbar.vue'
import FileTree from '../components/FileTree.vue'
import LogViewer from '../components/LogViewer.vue'
import QueueStatus from '../components/QueueStatus.vue'
import TerminalPanel from '../components/terminal/TerminalPanel.vue'
import { t } from '../i18n'

type OpenPathRequest = {
  path: string
  id: number
}

const props = defineProps<{
  systemInfo?: SystemInfo | null
  openPathRequest?: OpenPathRequest | null
}>()

const listing = ref<DirectoryListing | null>(null)
const currentPath = ref('')
const pathInput = ref('')
const selectedItems = ref<FileItem[]>([])
const selectedItem = ref<FileItem | null>(null)
const showHiddenFiles = ref(false)
const preview = ref<FileReadResponse | null>(null)
const asePreview = ref<AsePreviewResponse | null>(null)
const previewMode = ref<PreviewMode>('text')
const previewCandidate = ref<FileItem | null>(null)
const previewError = ref<string | null>(null)
const loadingFiles = ref(false)
const previewLoading = ref(false)
const dragUploadDepth = ref(0)
const forcedLargeTextPreviews = new Set<string>()
const forcedLargeStructurePreviews = new Set<string>()

type ResizeTarget = 'left' | 'right' | 'side'
type WorkPanelKind = 'preview' | 'queue' | 'plugin'
type PreviewMode = 'structure' | 'text'
type WorkPanel = {
  id: string
  kind: WorkPanelKind
  title: string
  pluginId?: string
  panelId?: string
  assetUrl?: string
  apiBase?: string
}
type ContextMenuState = {
  visible: boolean
  x: number
  y: number
  opensLeft: boolean
  item: FileItem | null
}
type UploadState = {
  active: boolean
  currentFile: string
  done: number
  totalFiles: number
  loaded: number
  total: number
  speedBytesPerSecond: number
}
type UploadConflictAction = 'overwrite' | 'skip' | 'suffix' | 'cancel'
type UploadConflictResolution = {
  action: UploadConflictAction
  applyAll: boolean
}
type UploadConflictDialogState = {
  visible: boolean
  name: string
  applyAll: boolean
  resolve: ((resolution: UploadConflictResolution) => void) | null
}
type UploadEntry = {
  file: File
  relativePath: string
  displayPath: string
  rootName: string
}
type FileSystemEntryLike = {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?: (callback: (file: File) => void, errorCallback?: (error: unknown) => void) => void
  createReader?: () => {
    readEntries: (callback: (entries: FileSystemEntryLike[]) => void, errorCallback?: (error: unknown) => void) => void
  }
}

const workspaceRef = ref<HTMLElement | null>(null)
const leftPaneRef = ref<HTMLElement | null>(null)
const mainPaneRef = ref<HTMLElement | null>(null)
const sidePaneRef = ref<HTMLElement | null>(null)
const activeResize = ref<ResizeTarget | null>(null)
const leftPaneWidth = ref<number | null>(null)
const sidePaneWidth = ref<number | null>(null)
const sideQueueHeight = ref<number | null>(null)
const terminalLayoutVersion = ref(0)
const workPanels = ref<WorkPanel[]>([
  { id: 'builtin:preview', kind: 'preview', title: t('preview.type.preview') },
  { id: 'builtin:queue', kind: 'queue', title: t('queue.title') }
])
const activeWorkPanelId = ref('builtin:preview')
const pluginManifests = ref<PluginManifest[]>([])
const previewProviders = ref<FilePreviewProvider[]>([])
const currentStructureSource = ref<StructureSource>(ASE_STRUCTURE_SOURCE)
const contextMenu = ref<ContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  opensLeft: false,
  item: null
})
const uploadState = ref<UploadState>({
  active: false,
  currentFile: '',
  done: 0,
  totalFiles: 0,
  loaded: 0,
  total: 0,
  speedBytesPerSecond: 0
})
const uploadConflictDialog = ref<UploadConflictDialogState>({
  visible: false,
  name: '',
  applyAll: false,
  resolve: null
})
const uploadProgressOpen = ref(false)
let previousBodyCursor = ''
let previousBodyUserSelect = ''

const SPLITTER_SIZE = 6
const MIN_LEFT_WIDTH = 260
const MIN_MAIN_WIDTH = 320
const MIN_SIDE_WIDTH = 300
const MIN_QUEUE_HEIGHT = 180
const MIN_LOG_HEIGHT = 120
const CONTEXT_MENU_WIDTH = 190
const CONTEXT_MENU_HEIGHT = 48

const workspaceStyle = computed<Record<string, string | undefined>>(() => ({
  '--workspace-left': leftPaneWidth.value === null ? undefined : `${leftPaneWidth.value}px`,
  '--workspace-side': sidePaneWidth.value === null ? undefined : `${sidePaneWidth.value}px`
}))

const dragUploadActive = computed(() => dragUploadDepth.value > 0)
const uploadPercent = computed(() => {
  if (!uploadState.value.active || uploadState.value.total <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((uploadState.value.loaded / uploadState.value.total) * 100)))
})
const uploadSpeedLabel = computed(() => formatUploadSpeed(uploadState.value.speedBytesPerSecond))

const sideStyle = computed<Record<string, string | undefined>>(() => ({
  '--workspace-queue': sideQueueHeight.value === null ? undefined : `${sideQueueHeight.value}px`
}))

const terminalInitialPath = computed(() => currentPath.value || props.systemInfo?.workspace_root || '')

const visibleItems = computed(() => (listing.value?.items ?? []).filter(item => showHiddenFiles.value || !isHiddenItem(item)))
const logPath = computed(() => selectedItems.value.find(item => item.type === 'file')?.path ?? null)
const structurePreviewCandidate = computed(() => {
  if (previewCandidate.value) return isStructureCandidate(previewCandidate.value) || providerLightMatchExists(previewCandidate.value)
  if (asePreview.value) return true
  return preview.value?.preview_type === 'structure' || false
})
const activeWorkPanel = computed(() => workPanels.value.find(panel => panel.id === activeWorkPanelId.value) ?? null)
const pluginPanelCommands = computed(() =>
  pluginManifests.value.flatMap(plugin =>
    (plugin.panels ?? []).map(panel => ({
      command: `plugin:${plugin.id}:${panel.id}`,
      title: panel.title || plugin.name || plugin.id,
      plugin,
      panel
    }))
  )
)

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function isSideVisible() {
  if (!sidePaneRef.value) return false
  return window.getComputedStyle(sidePaneRef.value).display !== 'none'
}

function measuredWidth(element: HTMLElement | null, fallback: number) {
  const width = element?.getBoundingClientRect().width
  return width && width > 0 ? width : fallback
}

function measuredHeight(element: HTMLElement | null, fallback: number) {
  const height = element?.getBoundingClientRect().height
  return height && height > 0 ? height : fallback
}

function currentLeftWidth() {
  return leftPaneWidth.value ?? measuredWidth(leftPaneRef.value, 360)
}

function currentSideWidth() {
  return sidePaneWidth.value ?? measuredWidth(sidePaneRef.value, 360)
}

function currentQueueHeight() {
  const panel = sidePaneRef.value?.querySelector('.side-work-panel') as HTMLElement | null
  return sideQueueHeight.value ?? measuredHeight(panel, 260)
}

function beginResize(cursor: string) {
  previousBodyCursor = document.body.style.cursor
  previousBodyUserSelect = document.body.style.userSelect
  document.body.style.cursor = cursor
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopResize, { once: true })
  window.addEventListener('pointercancel', stopResize, { once: true })
}

function startColumnResize(target: 'left' | 'right', event: PointerEvent) {
  if (!workspaceRef.value) return
  event.preventDefault()
  closeContextMenu()
  activeResize.value = target
  leftPaneWidth.value = currentLeftWidth()
  if (isSideVisible()) sidePaneWidth.value = currentSideWidth()
  beginResize('col-resize')
}

function startSideResize(event: PointerEvent) {
  if (!sidePaneRef.value) return
  event.preventDefault()
  closeContextMenu()
  activeResize.value = 'side'
  sideQueueHeight.value = currentQueueHeight()
  beginResize('row-resize')
}

function handlePointerMove(event: PointerEvent) {
  if (!activeResize.value) return
  if (activeResize.value === 'side') {
    resizeSide(event.clientY)
    return
  }
  resizeColumns(activeResize.value, event.clientX)
}

function resizeColumns(target: 'left' | 'right', clientX: number) {
  if (!workspaceRef.value) return
  const rect = workspaceRef.value.getBoundingClientRect()
  const totalWidth = rect.width
  const sideVisible = isSideVisible()
  const splitterTotal = sideVisible ? SPLITTER_SIZE * 2 : SPLITTER_SIZE

  if (target === 'left') {
    const reservedSide = sideVisible ? currentSideWidth() : 0
    const maxLeft = totalWidth - reservedSide - MIN_MAIN_WIDTH - splitterTotal
    leftPaneWidth.value = clamp(clientX - rect.left, MIN_LEFT_WIDTH, maxLeft)
    notifyTerminalLayoutChanged()
    return
  }

  if (!sideVisible) return
  const reservedLeft = currentLeftWidth()
  const maxSide = totalWidth - reservedLeft - MIN_MAIN_WIDTH - splitterTotal
  sidePaneWidth.value = clamp(rect.right - clientX, MIN_SIDE_WIDTH, maxSide)
  notifyTerminalLayoutChanged()
}

function resizeSide(clientY: number) {
  if (!sidePaneRef.value) return
  const rect = sidePaneRef.value.getBoundingClientRect()
  const maxQueue = rect.height - MIN_LOG_HEIGHT - SPLITTER_SIZE
  sideQueueHeight.value = clamp(clientY - rect.top, MIN_QUEUE_HEIGHT, maxQueue)
}

function stopResize() {
  if (!activeResize.value) return
  const target = activeResize.value
  activeResize.value = null
  document.body.style.cursor = previousBodyCursor
  document.body.style.userSelect = previousBodyUserSelect
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', stopResize)
  window.removeEventListener('pointercancel', stopResize)
  if (target === 'left' || target === 'right') notifyTerminalLayoutChanged()
}

function resetColumnLayout() {
  leftPaneWidth.value = null
  sidePaneWidth.value = null
  notifyTerminalLayoutChanged()
}

function resetSideLayout() {
  sideQueueHeight.value = null
}

function notifyTerminalLayoutChanged() {
  terminalLayoutVersion.value += 1
  window.requestAnimationFrame(() => window.dispatchEvent(new Event('chemweb:terminal-fit')))
}

function setSelection(items: FileItem[], primary: FileItem | null) {
  selectedItems.value = items
  selectedItem.value = primary ?? items[items.length - 1] ?? null
}

function isHiddenItem(item: FileItem) {
  return item.name.startsWith('.')
}

function isForcedStructureName(name: string) {
  return name.toUpperCase().includes('POSCAR') || name.toUpperCase().includes('CONTCAR')
}

function isStructureCandidate(item: FileItem) {
  return item.preview_type === 'structure' || isForcedStructureName(item.name)
}

function panelTitle(panel: WorkPanel) {
  if (panel.kind === 'preview') return t('preview.type.preview')
  if (panel.kind === 'queue') return props.systemInfo?.scheduler?.toUpperCase() ?? t('queue.title')
  return panel.title
}

function syncBuiltinPanelTitles() {
  workPanels.value = workPanels.value.map(panel => {
    if (panel.kind === 'preview') return { ...panel, title: t('preview.type.preview') }
    if (panel.kind === 'queue') return { ...panel, title: props.systemInfo?.scheduler?.toUpperCase() ?? t('queue.title') }
    return panel
  })
}

function openBuiltinPanel(kind: 'preview' | 'queue') {
  const id = `builtin:${kind}`
  if (!workPanels.value.some(panel => panel.id === id)) {
    workPanels.value.push({
      id,
      kind,
      title: kind === 'preview' ? t('preview.type.preview') : (props.systemInfo?.scheduler?.toUpperCase() ?? t('queue.title'))
    })
  }
  activeWorkPanelId.value = id
}

function moveWorkPanel(fromId: string, toId: string) {
  if (fromId === toId) return
  const fromIndex = workPanels.value.findIndex(panel => panel.id === fromId)
  const toIndex = workPanels.value.findIndex(panel => panel.id === toId)
  if (fromIndex < 0 || toIndex < 0) return
  const next = [...workPanels.value]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  workPanels.value = next
}

function closeWorkPanel(panelId: string) {
  const panel = workPanels.value.find(item => item.id === panelId)
  workPanels.value = workPanels.value.filter(item => item.id !== panelId)
  if (panel?.kind === 'plugin' && panel.pluginId) {
    unregisterProvidersByPlugin(panel.pluginId)
    if (!workPanels.value.some(item => item.kind === 'plugin' && item.pluginId === panel.pluginId)) {
      void deactivatePlugin(panel.pluginId).catch(() => undefined)
    }
  }
  if (activeWorkPanelId.value === panelId) {
    activeWorkPanelId.value = workPanels.value[workPanels.value.length - 1]?.id ?? ''
  }
}

function onWorkPanelDragStart(panelId: string, event: DragEvent) {
  if (!event.dataTransfer) return
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('application/x-chemweb-work-panel', panelId)
}

function onWorkPanelDragOver(panelId: string, event: DragEvent) {
  const types = Array.from(event.dataTransfer?.types ?? [])
  if (!types.includes('application/x-chemweb-work-panel')) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function onWorkPanelDrop(panelId: string, event: DragEvent) {
  const fromId = event.dataTransfer?.getData('application/x-chemweb-work-panel')
  if (!fromId) return
  event.preventDefault()
  moveWorkPanel(fromId, panelId)
}

async function openWorkPanelCommand(command: string | number | object) {
  if (typeof command !== 'string') return
  if (command === 'builtin:preview') {
    openBuiltinPanel('preview')
    return
  }
  if (command === 'builtin:queue') {
    openBuiltinPanel('queue')
    return
  }
  if (!command.startsWith('plugin:')) return
  const [, pluginId, panelId] = command.split(':')
  await openPluginPanel(pluginId, panelId)
}

async function loadPluginManifests() {
  try {
    const response = await listPlugins()
    pluginManifests.value = response.plugins
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('plugin.loadFailed'))
  }
}

async function openPluginPanel(pluginId: string, panelId: string) {
  const manifest = pluginManifests.value.find(plugin => plugin.id === pluginId)
  const panel = manifest?.panels.find(item => item.id === panelId)
  if (!manifest || !panel) return

  const existing = workPanels.value.find(item => item.kind === 'plugin' && item.pluginId === pluginId && item.panelId === panelId)
  if (existing && panel.singleton !== false) {
    activeWorkPanelId.value = existing.id
    return
  }

  try {
    const runtime = await activatePlugin(pluginId)
    const id = `plugin:${pluginId}:${panelId}:${Date.now()}`
    workPanels.value.push({
      id,
      kind: 'plugin',
      title: panel.title || manifest.name || pluginId,
      pluginId,
      panelId,
      assetUrl: `${API_BASE}${runtime.asset_url}`,
      apiBase: runtime.api_base
    })
    activeWorkPanelId.value = id
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('plugin.activateFailed'))
  }
}

function handlePluginFrameLoad(event: Event, panel: WorkPanel | null) {
  const frame = event.target instanceof HTMLIFrameElement ? event.target : null
  if (!frame?.contentWindow || !panel || !panel.pluginId || !panel.panelId) return
  frame.contentWindow.postMessage({
    type: 'chemweb:plugin:init',
    version: 1,
    pluginId: panel.pluginId,
    panelId: panel.panelId,
    instanceId: panel.id,
    locale: window.navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en',
    theme: 'light',
    apiBase: panel.apiBase,
    assetBase: panel.assetUrl,
    initialFile: previewCandidate.value
      ? { path: previewCandidate.value.path, name: previewCandidate.value.name }
      : null
  }, new URL(panel.assetUrl ?? window.location.href, window.location.href).origin)
}

function handlePluginMessage(event: MessageEvent) {
  if (!isTrustedPluginOrigin(event.origin)) return
  const data = event.data as { type?: string; provider?: FilePreviewProvider; providerId?: string }
  if (data?.type === 'chemweb:file-manager:register-preview-provider' && data.provider) {
    registerPreviewProvider(data.provider)
  } else if (data?.type === 'chemweb:file-manager:unregister-preview-provider' && data.providerId) {
    unregisterPreviewProvider(data.providerId)
  }
}

function isTrustedPluginOrigin(origin: string) {
  if (origin === window.location.origin) return true
  if (!API_BASE) return false
  try {
    return origin === new URL(API_BASE, window.location.href).origin
  } catch {
    return false
  }
}

function registerPreviewProvider(provider: FilePreviewProvider) {
  previewProviders.value = [
    ...previewProviders.value.filter(item => item.id !== provider.id),
    provider
  ].sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0))
}

function unregisterPreviewProvider(providerId: string) {
  previewProviders.value = previewProviders.value.filter(provider => provider.id !== providerId)
}

function unregisterProvidersByPlugin(pluginId: string) {
  previewProviders.value = previewProviders.value.filter(provider => provider.pluginId !== pluginId)
}

function providerLightMatchExists(item: FileItem) {
  return previewProviders.value.some(provider => providerMatchesItem(provider, item))
}

async function resolvePreviewProvider(item: FileItem) {
  const candidates = previewProviders.value.filter(provider => providerMatchesItem(provider, item))
  for (const provider of candidates) {
    if (!provider.probe?.apiPath || !provider.apiBase) return provider
    try {
      const response = await request<PreviewProbeResponse>(`${provider.apiBase}${provider.probe.apiPath}`, {
        method: provider.probe.method ?? 'POST',
        body: JSON.stringify({ path: item.path, item })
      })
      if (response.can_preview) return provider
    } catch {
      // Ignore a failed plugin probe and continue with the next provider.
    }
  }
  return null
}

function providerStructureSource(provider: FilePreviewProvider): StructureSource | null {
  const source = provider.open?.structureSource
  if (!source?.apiBase) return null
  return source
}

function setShowHiddenFiles(value: boolean) {
  showHiddenFiles.value = value
  if (value) return
  const visibleSelection = selectedItems.value.filter(item => !isHiddenItem(item))
  const primary = selectedItem.value && !isHiddenItem(selectedItem.value) ? selectedItem.value : (visibleSelection[visibleSelection.length - 1] ?? null)
  setSelection(visibleSelection, primary)
}

function handleSelectionChange(items: FileItem[], primary: FileItem | null) {
  setSelection(items, primary)
}

async function loadDirectory(path?: string | null) {
  loadingFiles.value = true
  try {
    listing.value = await listFiles(path ?? undefined)
    currentPath.value = listing.value.path
    pathInput.value = listing.value.path
    setSelection([], null)
    preview.value = null
    asePreview.value = null
    previewCandidate.value = null
    previewError.value = null
    currentStructureSource.value = ASE_STRUCTURE_SOURCE
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.directoryLoadFailed'))
  } finally {
    loadingFiles.value = false
  }
}

async function openDirectory(path?: string | null) {
  await loadDirectory(path)
}

async function openQueueWorkdir(path: string) {
  await openDirectory(path)
}

async function openDirectoryFromTerminal(path: string) {
  if (!path || path === currentPath.value) return
  await openDirectory(path)
}

async function openPathFromInput() {
  const value = pathInput.value.trim()
  await loadDirectory(value || undefined)
}

async function goUp() {
  if (listing.value?.parent) await loadDirectory(listing.value.parent)
}

async function openItem(item: FileItem) {
  setSelection([item], item)
  if (item.type === 'directory') {
    await loadDirectory(item.path)
    return
  }
  await previewFile(item)
}

async function previewFile(itemOrPath: FileItem | string) {
  const path = typeof itemOrPath === 'string' ? itemOrPath : itemOrPath.path
  const item = typeof itemOrPath === 'string'
    ? selectedItem.value?.path === path
      ? selectedItem.value
      : previewCandidate.value?.path === path
        ? previewCandidate.value
        : null
    : itemOrPath

  previewLoading.value = true
  preview.value = null
  asePreview.value = null
  previewCandidate.value = item
  previewError.value = null
  try {
    const provider = item ? await resolvePreviewProvider(item) : null
    const providerSource = provider ? providerStructureSource(provider) : null
    if (providerSource) {
      previewMode.value = 'structure'
      currentStructureSource.value = providerSource
      const structure = await readStructurePreviewWithLargeConfirmation(path, providerSource)
      if (structure) {
        asePreview.value = structure
        openBuiltinPanel('preview')
      }
      return
    }

    if (item && isStructureCandidate(item)) {
      previewMode.value = 'structure'
      currentStructureSource.value = ASE_STRUCTURE_SOURCE
      try {
        const structure = await readStructurePreviewWithLargeConfirmation(path, ASE_STRUCTURE_SOURCE)
        if (structure) {
          asePreview.value = structure
          openBuiltinPanel('preview')
        }
        return
      } catch (error) {
        previewError.value = error instanceof Error ? error.message : t('message.previewFailed')
        previewMode.value = 'text'
      }
    } else {
      previewMode.value = 'text'
    }

    const file = await readTextPreviewWithLargeConfirmation(path)
    if (file) {
      preview.value = file
      openBuiltinPanel('preview')
    }
  } catch (error) {
    preview.value = null
    ElMessage.error(error instanceof Error ? error.message : t('message.previewFailed'))
  } finally {
    previewLoading.value = false
  }
}

async function loadTextPreview() {
  const path = asePreview.value?.path ?? preview.value?.path ?? previewCandidate.value?.path
  if (!path || preview.value) return
  await readTextPreview(path)
}

async function refreshTextPreview() {
  const path = preview.value?.path ?? asePreview.value?.path ?? previewCandidate.value?.path
  if (!path) return
  await readTextPreview(path)
}

async function refreshPreview() {
  if (previewMode.value === 'structure') {
    await refreshStructurePreview()
    return
  }
  await refreshTextPreview()
}

async function readTextPreview(path: string) {
  previewLoading.value = true
  try {
    const file = await readTextPreviewWithLargeConfirmation(path)
    if (file) {
      preview.value = file
      openBuiltinPanel('preview')
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.previewFailed'))
  } finally {
    previewLoading.value = false
  }
}

async function loadStructurePreview() {
  const path = asePreview.value?.path ?? preview.value?.path ?? previewCandidate.value?.path
  if (!path || asePreview.value) return
  previewLoading.value = true
  previewError.value = null
  try {
    const structure = await readStructurePreviewWithLargeConfirmation(path, currentStructureSource.value)
    if (structure) asePreview.value = structure
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : t('message.previewFailed')
    previewMode.value = 'text'
    await loadTextPreview()
  } finally {
    previewLoading.value = false
  }
}

async function refreshStructurePreview() {
  const path = asePreview.value?.path ?? preview.value?.path ?? previewCandidate.value?.path
  if (!path) return
  previewLoading.value = true
  previewError.value = null
  try {
    const structure = await readStructurePreviewWithLargeConfirmation(path, currentStructureSource.value)
    if (structure) {
      asePreview.value = structure
      openBuiltinPanel('preview')
    }
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : t('message.previewFailed')
    ElMessage.error(previewError.value)
  } finally {
    previewLoading.value = false
  }
}

async function readTextPreviewWithLargeConfirmation(path: string) {
  try {
    return await readFile(path, forcedLargeTextPreviews.has(path))
  } catch (error) {
    if (!isLargePreviewError(error, 'FILE_TOO_LARGE')) throw error
    const confirmed = await confirmLargePreview(error, 'text')
    if (!confirmed) return null
    forcedLargeTextPreviews.add(path)
    return readFile(path, true)
  }
}

async function readStructurePreviewWithLargeConfirmation(path: string, source: StructureSource = ASE_STRUCTURE_SOURCE) {
  const cacheKey = `${source.id}:${path}`
  try {
    return await readStructurePreview(source, path, undefined, forcedLargeStructurePreviews.has(cacheKey))
  } catch (error) {
    if (!isLargePreviewError(error, 'STRUCTURE_FILE_TOO_LARGE')) throw error
    const confirmed = await confirmLargePreview(error, 'structure')
    if (!confirmed) return null
    forcedLargeStructurePreviews.add(cacheKey)
    return readStructurePreview(source, path, undefined, true)
  }
}

function isLargePreviewError(error: unknown, code: 'FILE_TOO_LARGE' | 'STRUCTURE_FILE_TOO_LARGE') {
  return error instanceof ApiError && error.code === code
}

async function confirmLargePreview(error: unknown, kind: 'text' | 'structure') {
  const message = error instanceof Error ? error.message : t('message.previewFailed')
  const title = kind === 'structure' ? t('preview.largeStructureTitle') : t('preview.largeFileTitle')
  const body = kind === 'structure'
    ? t('preview.largeStructureMessage', { message })
    : t('preview.largeFileMessage', { message })

  try {
    await ElMessageBox.confirm(body, title, {
      confirmButtonText: t('preview.loadAnyway'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    return true
  } catch {
    return false
  }
}

function setPreviewMode(mode: PreviewMode) {
  previewMode.value = mode
  if (mode === 'text') {
    void loadTextPreview()
  } else {
    void loadStructurePreview()
  }
}

async function savePreview(content: string) {
  if (!preview.value) return
  const path = preview.value.path
  try {
    await writeFile(path, content)
    ElMessage.success(t('message.saved'))
    const file = await readTextPreviewWithLargeConfirmation(path)
    if (file) preview.value = file
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.saveFailed'))
  }
}

function openFileContextMenu(item: FileItem, event: MouseEvent) {
  if (item.type !== 'file') {
    closeContextMenu()
    return
  }

  contextMenu.value = {
    visible: true,
    x: clamp(event.clientX, 8, window.innerWidth - CONTEXT_MENU_WIDTH - 8),
    y: clamp(event.clientY, 8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8),
    opensLeft: event.clientX > window.innerWidth - 360,
    item
  }
}

function closeContextMenu() {
  if (!contextMenu.value.visible) return
  contextMenu.value = {
    visible: false,
    x: 0,
    y: 0,
    opensLeft: false,
    item: null
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeContextMenu()
}

async function submitContextJob(command: SubmitCommand) {
  const item = contextMenu.value.item
  if (!item || item.type !== 'file') return
  closeContextMenu()
  try {
    const response = await submitJob(currentPath.value, item.name, command)
    ElMessage.success(response.message || t('submit.jobSubmitted', { id: response.job_id ?? '' }))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.submitFailed'))
  }
}

async function promptMkdir() {
  const result = await ElMessageBox.prompt(t('prompt.folderName'), t('prompt.newFolder'), {
    inputPattern: /^[A-Za-z0-9._-]+$/,
    inputErrorMessage: t('message.namePattern'),
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel')
  })
  try {
    await makeDirectory(currentPath.value, result.value)
    await loadDirectory(currentPath.value)
    ElMessage.success(t('message.folderCreated'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.createFailed'))
  }
}

async function handleUpload(files: File[]) {
  const entries = filesToUploadEntries(files)
  await handleUploadEntries(entries)
}

function filesToUploadEntries(files: File[]) {
  return files
    .filter(file => file.name)
    .map(file => {
      const relativePath = sanitizeRelativePath(file.webkitRelativePath || file.name)
      return {
        file,
        relativePath,
        displayPath: relativePath,
        rootName: relativePath.split('/')[0] ?? file.name
      } satisfies UploadEntry
    })
}

async function handleUploadEntries(entries: UploadEntry[]) {
  if (entries.length === 0) return

  const prepared = await prepareUploadEntries(entries)
  if (!prepared || prepared.length === 0) return

  let uploaded = 0
  let firstError: unknown = null
  const totalBytes = prepared.reduce((sum, entry) => sum + entry.file.size, 0)
  let completedBytes = 0
  uploadState.value = {
    active: true,
    currentFile: prepared[0]?.displayPath ?? '',
    done: 0,
    totalFiles: prepared.length,
    loaded: 0,
    total: totalBytes,
    speedBytesPerSecond: 0
  }
  uploadProgressOpen.value = false

  for (const entry of prepared) {
    const file = entry.file
    try {
      uploadState.value.currentFile = entry.displayPath
      let lastProgressLoaded = 0
      let lastProgressAt = performance.now()
      await uploadFile(currentPath.value, file, {
        relativePath: entry.relativePath,
        onProgress: (progress: UploadProgress) => {
        const fileLoaded = Math.min(progress.loaded, progress.total || file.size)
        const now = performance.now()
        const elapsedSeconds = Math.max((now - lastProgressAt) / 1000, 0.001)
        const deltaBytes = Math.max(0, fileLoaded - lastProgressLoaded)
        const instantSpeed = deltaBytes / elapsedSeconds
        uploadState.value.speedBytesPerSecond = uploadState.value.speedBytesPerSecond === 0
          ? instantSpeed
          : uploadState.value.speedBytesPerSecond * 0.72 + instantSpeed * 0.28
        lastProgressLoaded = fileLoaded
        lastProgressAt = now
        uploadState.value.loaded = Math.min(totalBytes, completedBytes + fileLoaded)
        }
      })
      uploaded += 1
      completedBytes += file.size
      uploadState.value.done = uploaded
      uploadState.value.loaded = Math.min(totalBytes, completedBytes)
    } catch (error) {
      firstError ??= error
      completedBytes += file.size
      uploadState.value.loaded = Math.min(totalBytes, completedBytes)
    }
  }

  await loadDirectory(currentPath.value)
  uploadState.value.active = false
  uploadProgressOpen.value = false

  if (uploaded === prepared.length) {
    ElMessage.success(
      prepared.length === 1 ? t('message.uploadComplete') : t('message.uploadCompleteMany', { count: prepared.length })
    )
  } else {
    const failed = prepared.length - uploaded
    const message = firstError instanceof Error ? firstError.message : t('message.uploadFailed')
    ElMessage.error(t('message.uploadPartial', { message, uploaded, failed }))
  }
}

function sanitizeRelativePath(path: string) {
  return path.replace(/\\/g, '/').split('/').filter(part => part && part !== '.' && part !== '..').join('/')
}

async function prepareUploadEntries(entries: UploadEntry[]) {
  const normalized = entries
    .map(entry => ({
      ...entry,
      relativePath: sanitizeRelativePath(entry.relativePath),
      displayPath: sanitizeRelativePath(entry.displayPath || entry.relativePath)
    }))
    .filter(entry => entry.relativePath)

  if (normalized.length === 0) return []

  const topLevelItems = new Map((await listFiles(currentPath.value)).items.map(item => [item.name, item] as const))
  const resolved: UploadEntry[] = []
  let applyAllAction: UploadConflictAction | null = null

  const groups = new Map<string, UploadEntry[]>()
  for (const entry of normalized) {
    const rootName = entry.relativePath.split('/')[0] ?? entry.file.name
    const group = groups.get(rootName)
    if (group) group.push(entry)
    else groups.set(rootName, [entry])
  }

  for (const [rootName, group] of groups) {
    const isFolderUpload = group.some(entry => entry.relativePath.includes('/'))
    const existing = topLevelItems.get(rootName) ?? null

    let action: UploadConflictAction = 'overwrite'
    if (existing) {
      const resolution: UploadConflictResolution = applyAllAction
        ? { action: applyAllAction, applyAll: true }
        : await promptUploadConflict(rootName)
      if (resolution.applyAll) applyAllAction = resolution.action
      action = resolution.action
    }

    if (action === 'cancel') return null
    if (action === 'skip') continue

    let finalRootName = rootName
    if (action === 'suffix') {
      finalRootName = uniqueSuffixedName(rootName, topLevelItems)
    }

    for (const entry of group) {
      const suffix = entry.relativePath === rootName ? '' : entry.relativePath.slice(rootName.length)
      const relativePath = `${finalRootName}${suffix}`
      resolved.push({
        ...entry,
        relativePath,
        displayPath: relativePath,
        rootName: finalRootName
      })
    }

    topLevelItems.set(finalRootName, {
      name: finalRootName,
      path: joinDisplayPath(currentPath.value, finalRootName),
      type: isFolderUpload ? 'directory' : 'file',
      size: null,
      mtime: '',
      extension: '',
      preview_type: isFolderUpload ? 'directory' : 'file',
      format: null
    })
  }

  return resolved
}

function uniqueSuffixedName(name: string, existing: Map<string, FileItem>) {
  let candidate = `${name}.new`
  while (existing.has(candidate)) {
    candidate = `${candidate}.new`
  }
  return candidate
}

function joinDisplayPath(parent: string, name: string) {
  if (!parent) return name
  const separator = parent.includes('\\') ? '\\' : '/'
  return `${parent.replace(/[\\/]+$/, '')}${separator}${name}`
}

async function promptUploadConflict(name: string) {
  return new Promise<UploadConflictResolution>(resolve => {
    uploadConflictDialog.value = {
      visible: true,
      name,
      applyAll: false,
      resolve
    }
  })
}

function chooseUploadConflict(action: UploadConflictAction) {
  const dialog = uploadConflictDialog.value
  if (!dialog.resolve) return
  dialog.resolve({ action, applyAll: dialog.applyAll })
  uploadConflictDialog.value = {
    visible: false,
    name: '',
    applyAll: false,
    resolve: null
  }
}

function formatUploadSpeed(bytesPerSecond: number) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '0.0 MB/s'
  return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`
}

function hasFileDrag(event: DragEvent) {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

function setUploadDropEffect(event: DragEvent) {
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleWorkspaceDragEnter(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  closeContextMenu()
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleWorkspaceDragOver(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleWorkspaceDragLeave(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  const root = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const related = event.relatedTarget instanceof Node ? event.relatedTarget : null
  if (root && related && root.contains(related)) return
  dragUploadDepth.value = 0
}

function handleWorkspaceDrop(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 0
  void collectDropUploadEntries(event).then(entries => {
    if (entries.length > 0) void handleUploadEntries(entries)
  })
}

async function collectDropUploadEntries(event: DragEvent) {
  const items = Array.from(event.dataTransfer?.items ?? [])
  if (items.length > 0) {
    const entries = await Promise.all(items.map(item => collectDataTransferItem(item)))
    const flattened = entries.flat().filter(entry => entry.file.name)
    if (flattened.length > 0) return flattened
  }
  return filesToUploadEntries(Array.from(event.dataTransfer?.files ?? []).filter(file => file.name))
}

async function collectDataTransferItem(item: DataTransferItem): Promise<UploadEntry[]> {
  if (item.kind !== 'file') return []
  const getEntry = (item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntryLike | null }).webkitGetAsEntry
  const entry = getEntry?.call(item)
  if (!entry) {
    const file = item.getAsFile()
    return file ? filesToUploadEntries([file]) : []
  }
  return collectFileSystemEntry(entry, '')
}

async function collectFileSystemEntry(entry: FileSystemEntryLike, parentPath: string): Promise<UploadEntry[]> {
  const relativePath = sanitizeRelativePath(parentPath ? `${parentPath}/${entry.name}` : entry.name)
  if (entry.isFile) {
    const file = await readFileSystemEntryFile(entry)
    return file
      ? [{
          file,
          relativePath,
          displayPath: relativePath,
          rootName: relativePath.split('/')[0] ?? file.name
        }]
      : []
  }
  if (!entry.isDirectory || !entry.createReader) return []
  const children = await readAllDirectoryEntries(entry)
  const nested = await Promise.all(children.map(child => collectFileSystemEntry(child, relativePath)))
  return nested.flat()
}

function readFileSystemEntryFile(entry: FileSystemEntryLike) {
  return new Promise<File | null>(resolve => {
    if (!entry.file) {
      resolve(null)
      return
    }
    entry.file(file => resolve(file), () => resolve(null))
  })
}

async function readAllDirectoryEntries(entry: FileSystemEntryLike) {
  const reader = entry.createReader?.()
  if (!reader) return []
  const entries: FileSystemEntryLike[] = []
  while (true) {
    const batch = await new Promise<FileSystemEntryLike[]>(resolve => {
      reader.readEntries(resolve, () => resolve([]))
    })
    if (batch.length === 0) break
    entries.push(...batch)
  }
  return entries
}

function handlePreviewDragOver(event: DragEvent) {
  if (!hasChemwebFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handlePreviewDrop(event: DragEvent) {
  const payload = readChemwebFileDrag(event.dataTransfer)
  const path = payload?.paths[0]
  if (!path) return
  event.preventDefault()
  openBuiltinPanel('preview')
  void previewFile(payload.items[0] ?? path)
}

function triggerDownload(path: string) {
  const link = document.createElement('a')
  link.href = downloadUrl(path)
  link.rel = 'noopener'
  link.click()
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function downloadSelected() {
  const targets = selectedItems.value.filter(item => item.type === 'file' || item.type === 'directory')
  if (targets.length === 0) return

  if (targets.length === 1 && targets[0].type === 'file') {
    triggerDownload(targets[0].path)
    return
  }

  try {
    const response = await downloadArchive(targets.map(item => item.path))
    triggerBlobDownload(response.blob, response.filename ?? 'chemweb-selection.zip')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.downloadFailed'))
  }
}

async function promptRename() {
  if (selectedItems.value.length !== 1 || !selectedItem.value) return
  const oldPath = selectedItem.value.path
  const result = await ElMessageBox.prompt(t('prompt.newName'), t('prompt.rename'), {
    inputValue: selectedItem.value.name,
    inputPattern: /^[A-Za-z0-9._-]+$/,
    inputErrorMessage: t('message.namePattern'),
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel')
  })
  const separator = oldPath.includes('\\') ? '\\' : '/'
  const parent = oldPath.split(/[\\/]/).slice(0, -1).join(separator)
  try {
    await renamePath(oldPath, `${parent}${separator}${result.value}`)
    await loadDirectory(currentPath.value)
    ElMessage.success(t('message.renamed'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.renameFailed'))
  }
}

async function confirmDelete() {
  const targets = selectedItems.value.length > 0 ? selectedItems.value : selectedItem.value ? [selectedItem.value] : []
  if (!targets.length) return
  await ElMessageBox.confirm(t('prompt.deleteItems', { count: targets.length }), t('prompt.confirmDelete'), {
    type: 'warning',
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel')
  })
  try {
    for (const item of targets) {
      await deletePath(item.path)
    }
    setSelection([], null)
    preview.value = null
    asePreview.value = null
    previewCandidate.value = null
    previewError.value = null
    currentStructureSource.value = ASE_STRUCTURE_SOURCE
    await loadDirectory(currentPath.value)
    ElMessage.success(t('message.deleted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.deleteFailed'))
  }
}

onMounted(() => {
  void loadDirectory()
  void loadPluginManifests()
  window.addEventListener('click', closeContextMenu)
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('message', handlePluginMessage)
  window.addEventListener('resize', closeContextMenu)
  window.addEventListener('scroll', closeContextMenu, true)
})

watch(
  () => props.openPathRequest?.id,
  () => {
    const path = props.openPathRequest?.path
    if (path) void openDirectory(path)
  }
)

watch(
  () => props.systemInfo?.scheduler,
  () => {
    syncBuiltinPanelTitles()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (uploadConflictDialog.value.resolve) chooseUploadConflict('cancel')
  stopResize()
  window.removeEventListener('click', closeContextMenu)
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('message', handlePluginMessage)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('scroll', closeContextMenu, true)
})
</script>

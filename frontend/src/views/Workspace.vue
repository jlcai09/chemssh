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
        <div class="side-panel-tabs">
          <el-segmented v-model="activeSidePanel" :options="sidePanelOptions" size="small" />
        </div>
        <div class="side-panel-body">
          <FilePreview
            v-if="activeSidePanel === 'preview'"
            :file="preview"
            :ase-structure="asePreview"
            :mode="previewMode"
            :loading="previewLoading"
            :structure-candidate="structurePreviewCandidate"
            :structure-error="previewError"
            @update:mode="setPreviewMode"
            @refresh="refreshPreview"
            @save="savePreview"
          />
          <QueueStatus
            v-else
            class="side-queue"
            :initial-interval="5"
            :workspace-root="props.systemInfo?.workspace_root"
            @open-workdir="openQueueWorkdir"
          />
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

    <Teleport to="body">
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
import { ArrowRight, Promotion, UploadFilled } from '@element-plus/icons-vue'
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
  type FileReadResponse
} from '../api/files'
import { ApiError, downloadUrl } from '../api/http'
import { submitJob, type SubmitCommand } from '../api/jobs'
import { readAsePreview } from '../api/structures'
import type { SystemInfo } from '../api/system'
import type { AsePreviewResponse } from '../types/structure'
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
type SidePanel = 'preview' | 'queue'
type PreviewMode = 'structure' | 'text'
type ContextMenuState = {
  visible: boolean
  x: number
  y: number
  opensLeft: boolean
  item: FileItem | null
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
const activeSidePanel = ref<SidePanel>('preview')
const contextMenu = ref<ContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  opensLeft: false,
  item: null
})
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

const sideStyle = computed<Record<string, string | undefined>>(() => ({
  '--workspace-queue': sideQueueHeight.value === null ? undefined : `${sideQueueHeight.value}px`
}))

const terminalInitialPath = computed(() => currentPath.value || props.systemInfo?.workspace_root || '')

const visibleItems = computed(() => (listing.value?.items ?? []).filter(item => showHiddenFiles.value || !isHiddenItem(item)))
const logPath = computed(() => selectedItems.value.find(item => item.type === 'file')?.path ?? null)
const structurePreviewCandidate = computed(() => {
  if (previewCandidate.value) return isStructureCandidate(previewCandidate.value)
  if (asePreview.value) return true
  return preview.value?.preview_type === 'structure' || false
})
const sidePanelOptions = computed(() => [
  { label: t('preview.type.preview'), value: 'preview' },
  { label: props.systemInfo?.scheduler?.toUpperCase() ?? t('queue.title'), value: 'queue' }
])

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
    if (item && isStructureCandidate(item)) {
      previewMode.value = 'structure'
      try {
        const structure = await readStructurePreviewWithLargeConfirmation(path)
        if (structure) {
          asePreview.value = structure
          activeSidePanel.value = 'preview'
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
      activeSidePanel.value = 'preview'
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
      activeSidePanel.value = 'preview'
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
    const structure = await readStructurePreviewWithLargeConfirmation(path)
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
    const structure = await readStructurePreviewWithLargeConfirmation(path)
    if (structure) {
      asePreview.value = structure
      activeSidePanel.value = 'preview'
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

async function readStructurePreviewWithLargeConfirmation(path: string) {
  try {
    return await readAsePreview(path, undefined, forcedLargeStructurePreviews.has(path))
  } catch (error) {
    if (!isLargePreviewError(error, 'STRUCTURE_FILE_TOO_LARGE')) throw error
    const confirmed = await confirmLargePreview(error, 'structure')
    if (!confirmed) return null
    forcedLargeStructurePreviews.add(path)
    return readAsePreview(path, undefined, true)
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
  if (files.length === 0) return

  let uploaded = 0
  let firstError: unknown = null

  for (const file of files) {
    try {
      await uploadFile(currentPath.value, file)
      uploaded += 1
    } catch (error) {
      firstError ??= error
    }
  }

  await loadDirectory(currentPath.value)

  if (uploaded === files.length) {
    ElMessage.success(
      files.length === 1 ? t('message.uploadComplete') : t('message.uploadCompleteMany', { count: files.length })
    )
  } else {
    const failed = files.length - uploaded
    const message = firstError instanceof Error ? firstError.message : t('message.uploadFailed')
    ElMessage.error(t('message.uploadPartial', { message, uploaded, failed }))
  }
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
  const files = Array.from(event.dataTransfer?.files ?? []).filter(file => file.name)
  if (files.length > 0) void handleUpload(files)
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
    await loadDirectory(currentPath.value)
    ElMessage.success(t('message.deleted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.deleteFailed'))
  }
}

onMounted(() => {
  void loadDirectory()
  window.addEventListener('click', closeContextMenu)
  window.addEventListener('keydown', handleGlobalKeydown)
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

onBeforeUnmount(() => {
  stopResize()
  window.removeEventListener('click', closeContextMenu)
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('scroll', closeContextMenu, true)
})
</script>

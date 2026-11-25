<template>
  <div
    class="canvas-file-manager"
    :class="{ 'is-drag-upload': dragUploadActive || currentDirectoryDragActive }"
    @dragenter="handleDragEnter"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >
    <div class="canvas-file-manager-bar">
      <el-input
        v-model="pathInput"
        class="canvas-file-path"
        size="small"
        clearable
        spellcheck="false"
        @keyup.enter="openPath(pathInput)"
      >
        <template #append>
          <el-tooltip :content="t('toolbar.go')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
            <el-button :icon="ArrowRight" @click="openPath(pathInput)" />
          </el-tooltip>
        </template>
      </el-input>
    </div>

    <FileToolbar
      :selected-items="selectedItems"
      :can-go-back="canGoBack"
      :history-entries="directoryHistoryEntries"
      :show-hidden-files="showHiddenFiles"
      @refresh="loadDirectory(currentPath, { refresh: true })"
      @go-back="goBack"
      @history-select="openHistoryPath"
      @create-file="promptCreateFile"
      @mkdir="promptMkdir"
      @upload="handleUpload"
      @download="downloadSelected"
      @rename="promptRename"
      @delete="confirmDelete"
      @update:show-hidden-files="value => showHiddenFiles = value"
    />

    <div class="canvas-file-tree-shell">
      <FileTree
        :items="visibleItems"
        :parent-path="listing?.parent"
        :selected-items="selectedItems"
        :loading="loading"
        :system-icon-provider="launcherSystemIconProvider"
        :preview-providers="previewProviders"
        :empty-notice="fileTreeEmptyNotice"
        @empty-action="openDefaultDirectory"
        @selection-change="handleSelectionChange"
        @context-menu="handleContextMenu"
        @blank-context-menu="handleBlankContextMenu"
        @move-items="handleMoveItems"
        @upload-drop="handleExternalUploadDrop"
        @upload-target-change="externalDropTargetPath = $event"
        @open="openItem"
        @delete="confirmDelete"
      />
    </div>

    <div
      v-if="dragUploadActive && !externalDropTargetPath"
      class="canvas-file-drop-overlay is-upload-overlay"
      aria-live="polite"
    >
      <el-icon><UploadFilled /></el-icon>
      <span>{{ t('file.dropUpload') }}</span>
    </div>

    <div
      v-else-if="currentDirectoryDragActive"
      class="canvas-file-drop-actions"
      aria-live="polite"
      @dragleave.stop="handleCurrentDirectoryDropDragLeave"
    >
      <div
        class="canvas-file-drop-overlay"
        :class="{ 'is-disabled': !canDropCurrentDirectoryMove }"
        @dragenter.stop.prevent="handleCurrentDirectoryActionDragOver('move', $event)"
        @dragover.stop.prevent="handleCurrentDirectoryActionDragOver('move', $event)"
        @drop.stop.prevent="handleCurrentDirectoryActionDrop('move', $event)"
      >
        <el-icon><UploadFilled /></el-icon>
        <span>{{ t('file.dropMoveCurrent') }}</span>
      </div>
      <div
        class="canvas-file-drop-overlay is-copy-action"
        :class="{ 'is-disabled': !canDropCurrentDirectoryCopy }"
        @dragenter.stop.prevent="handleCurrentDirectoryActionDragOver('copy', $event)"
        @dragover.stop.prevent="handleCurrentDirectoryActionDragOver('copy', $event)"
        @drop.stop.prevent="handleCurrentDirectoryActionDrop('copy', $event)"
      >
        <el-icon><CopyDocument /></el-icon>
        <span>{{ t('file.dropCopyCurrent') }}</span>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="contextMenu.visible && contextMenu.item"
        class="file-context-menu"
        :class="{ 'opens-left': contextMenu.opensLeft }"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
        role="menu"
        @click.stop
        @contextmenu.prevent
      >
        <button
          v-if="contextMenu.item && canLauncherOpenItem(contextMenu.item, 'default')"
          class="context-menu-item"
          type="button"
          role="menuitem"
          @click="openContextWithLocalApp"
        >
          <el-icon>
            <component :is="contextMenu.item?.type === 'directory' ? FolderOpened : Document" />
          </el-icon>
          <span>{{ t('context.openLocal') }}</span>
          <span />
        </button>
        <button
          v-if="contextMenu.item && canLauncherOpenItem(contextMenu.item, 'text')"
          class="context-menu-item"
          type="button"
          role="menuitem"
          @click="openContextWithNotepad"
        >
          <el-icon><EditPen /></el-icon>
          <span>{{ t('context.openNotepad') }}</span>
          <span />
        </button>
        <button class="context-menu-item" type="button" role="menuitem" @click="copyContextPath">
          <el-icon><CopyDocument /></el-icon>
          <span>{{ t('context.copyPath') }}</span>
          <span />
        </button>
        <div v-if="contextMenu.item?.type === 'file'" class="context-menu-item has-submenu" role="menuitem" tabindex="0">
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
        <span class="context-menu-separator" role="separator" />
        <button class="context-menu-item" type="button" role="menuitem" @click="copyContextItems">
          <el-icon><CopyDocument /></el-icon>
          <span>{{ t('context.copy') }}</span>
          <span />
        </button>
        <div v-if="archiveFormats.length > 0" class="context-menu-item has-submenu" role="menuitem" tabindex="0">
          <el-icon><Files /></el-icon>
          <span>{{ t('context.compress') }}</span>
          <el-icon class="submenu-arrow"><ArrowRight /></el-icon>
          <div class="context-submenu" role="menu">
            <button
              v-for="format in archiveFormats"
              :key="format"
              class="context-menu-item"
              type="button"
              role="menuitem"
              @click="compressSelection(format)"
            >
              <el-icon><Files /></el-icon>
              <span>{{ t('context.compressAs', { format }) }}</span>
              <span />
            </button>
          </div>
        </div>
        <button
          class="context-menu-item"
          type="button"
          role="menuitem"
          :disabled="!canExtractSelection"
          @click="extractSelection"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>{{ t('context.extract') }}</span>
          <span />
        </button>
        <button
          class="context-menu-item"
          type="button"
          role="menuitem"
          :disabled="selectedItems.length !== 1"
          @click="renameContextItem"
        >
          <el-icon><EditPen /></el-icon>
          <span>{{ t('context.rename') }}</span>
          <span />
        </button>
        <button class="context-menu-item is-danger" type="button" role="menuitem" @click="deleteContextItems">
          <el-icon><Delete /></el-icon>
          <span>{{ t('context.delete') }}</span>
          <span />
        </button>
      </div>

      <div
        v-if="contextMenu.visible && contextMenu.blank"
        class="file-context-menu"
        :class="{ 'opens-left': contextMenu.opensLeft }"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
        role="menu"
        @click.stop
        @contextmenu.prevent
      >
        <button class="context-menu-item" type="button" role="menuitem" @click="selectAllFromMenu">
          <el-icon><Select /></el-icon>
          <span>{{ t('context.selectAll') }}</span>
          <span />
        </button>
        <button class="context-menu-item" type="button" role="menuitem" @click="refreshFromMenu">
          <el-icon><Refresh /></el-icon>
          <span>{{ t('context.refresh') }}</span>
          <span />
        </button>
        <button
          class="context-menu-item"
          type="button"
          role="menuitem"
          :disabled="!hasFileClipboard"
          @click="pasteFromMenu"
        >
          <el-icon><DocumentCopy /></el-icon>
          <span>{{ t('context.paste') }}</span>
          <span />
        </button>
        <span class="context-menu-separator" role="separator" />
        <button class="context-menu-item" type="button" role="menuitem" @click="copyFolderPathFromMenu">
          <el-icon><CopyDocument /></el-icon>
          <span>{{ t('context.copyFolderPath') }}</span>
          <span />
        </button>
        <span class="context-menu-separator" role="separator" />
        <div class="context-menu-item has-submenu" role="menuitem" tabindex="0">
          <el-icon><Plus /></el-icon>
          <span>{{ t('context.new') }}</span>
          <el-icon class="submenu-arrow"><ArrowRight /></el-icon>
          <div class="context-submenu" role="menu">
            <button class="context-menu-item" type="button" role="menuitem" @click="newFolderFromMenu">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ t('context.newFolder') }}</span>
              <span />
            </button>
            <button class="context-menu-item" type="button" role="menuitem" @click="newFileFromMenu">
              <el-icon><Document /></el-icon>
              <span>{{ t('context.newFile') }}</span>
              <span />
            </button>
          </div>
        </div>
      </div>

      <div v-if="uploadConflictDialog.visible" class="upload-conflict-backdrop">
        <div class="upload-conflict-dialog" role="dialog" aria-modal="true">
          <div class="upload-conflict-title">
            {{
              uploadConflictDialog.mode === 'copy'
                ? t('copy.conflictTitle')
                : uploadConflictDialog.mode === 'move'
                  ? t('move.conflictTitle')
                  : t('upload.conflictTitle')
            }}
          </div>
          <p>
            {{
              uploadConflictDialog.mode === 'copy'
                ? t('copy.conflictMessage', { name: uploadConflictDialog.name })
                : uploadConflictDialog.mode === 'move'
                ? t('move.conflictMessage', { name: uploadConflictDialog.name })
                : t('upload.conflictMessage', { name: uploadConflictDialog.name })
            }}
          </p>
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
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowRight,
  CopyDocument,
  Delete,
  Document,
  DocumentCopy,
  EditPen,
  Files,
  FolderOpened,
  Plus,
  Promotion,
  Refresh,
  Select,
  UploadFilled
} from '@element-plus/icons-vue'
import {
  getActiveChemSSHFileDragPayload,
  hasChemSSHFileDrag,
  readChemSSHFileDrag,
  type ChemSSHFileDragPayload
} from '../../api/fileDrag'
import { copyApiErrorMessage, moveApiErrorMessage, prepareMoveEntries } from '../../api/fileMove'
import { ApiError, downloadUrl } from '../../api/http'
import { apiErrorMessage, localizeBackendMessage } from '../../api/apiMessages'
import {
  isPathInsideWorkspace,
  launcherFileIconUrl,
  openWithLocalApp,
  openWithNotepad,
  parentDirectoryPath,
  type LauncherBridgeCapabilities
} from '../../api/launcherBridge'
import {
  canExtractName,
  compressPaths,
  copyPaths,
  deletePath,
  downloadArchive,
  extractArchive,
  getArchiveTools,
  listFiles,
  makeDirectory,
  movePaths,
  renamePath,
  uploadFile,
  writeFile,
  type DirectoryListing,
  type ArchiveFormat,
  type ArchiveTools,
  type FileItem
} from '../../api/files'
import type { FilePreviewProvider } from '../../api/filePreviewProviders'
import {
  collectDropUploadEntries,
  filesToUploadEntries,
  hasFileDrag,
  joinDisplayPath,
  prepareUploadEntries,
  SAFE_UPLOAD_SEGMENT_RE,
  setUploadDropEffect,
  type UploadConflictAction,
  type UploadConflictResolution,
  type UploadEntry
} from '../../api/uploadEntries'
import { confirmOversizedUpload } from '../../api/uploadSizeCheck'
import { fileClipboardItems, hasFileClipboard, setFileClipboard } from '../../stores/fileClipboard'
import { useSystemStore } from '../../stores/system'
import { submitJob, type SubmitCommand } from '../../api/jobs'
import { t } from '../../i18n'
import FileToolbar from '../FileToolbar.vue'
import FileTree from '../FileTree.vue'

const props = defineProps<{
  initialPath?: string | null
  refreshToken?: number
  launcherBridgeCapabilities?: LauncherBridgeCapabilities | null
  workspaceRoot?: string | null
  previewProviders?: FilePreviewProvider[]
}>()

const emit = defineEmits<{
  'path-change': [path: string]
  'open-file': [item: FileItem]
  'selection-change': [items: FileItem[], primary: FileItem | null]
  'directories-change': [paths: string[]]
}>()

const systemStore = useSystemStore()

const listing = shallowRef<DirectoryListing | null>(null)
const directoryLoadError = ref<{ path: string; message: string; code?: string } | null>(null)
const currentPath = ref(props.initialPath ?? '')
const pathInput = ref(props.initialPath ?? '')
const selectedItems = ref<FileItem[]>([])
const selectedItem = ref<FileItem | null>(null)
const showHiddenFiles = ref(false)
const loading = ref(false)
const dragUploadDepth = ref(0)
const currentDirectoryDragDepth = ref(0)
const externalDropTargetPath = ref<string | null>(null)
const directoryHistory = ref<string[]>([])
const contextMenu = ref<ContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  opensLeft: false,
  blank: false,
  item: null
})
const uploadConflictDialog = ref<UploadConflictDialogState>({
  visible: false,
  mode: 'upload',
  name: '',
  applyAll: false,
  resolve: null
})

type ContextMenuState = {
  visible: boolean
  x: number
  y: number
  opensLeft: boolean
  // `blank` marks the directory-level menu opened on empty space; `item` is
  // null in that mode.
  blank: boolean
  item: FileItem | null
}

type UploadConflictDialogState = {
  visible: boolean
  mode: 'upload' | 'move' | 'copy'
  name: string
  applyAll: boolean
  resolve: ((resolution: UploadConflictResolution) => void) | null
}

const visibleItems = computed(() => {
  const items = listing.value?.items ?? []
  return showHiddenFiles.value ? items : items.filter(item => !item.name.startsWith('.'))
})

const defaultDirectory = computed(() => props.workspaceRoot || systemStore.systemInfo?.workspace_root || '')

// The tree is empty whenever a directory fails to load, so replace the blank
// pane with a warning and a one-click way back to the configured root.
const fileTreeEmptyNotice = computed(() => {
  const error = directoryLoadError.value
  if (!error) return null
  // An empty requested path means "configured root", so there is nowhere else to go.
  const failedPath = error.path || defaultDirectory.value
  const canReturnToDefault = Boolean(defaultDirectory.value) && failedPath !== defaultDirectory.value
  return {
    title: error.code === 'DIRECTORY_NOT_FOUND' ? t('file.directoryMissing') : t('message.directoryLoadFailed'),
    description: error.message,
    actionLabel: canReturnToDefault ? t('file.backToDefaultDirectory') : undefined
  }
})
const dragUploadActive = computed(() => dragUploadDepth.value > 0)
const canGoBack = computed(() => directoryHistory.value.length > 0)
const directoryHistoryEntries = computed(() => directoryHistory.value.map(path => ({
  path,
  label: directoryHistoryLabel(path)
})))
const currentDirectoryDragActive = computed(() => currentDirectoryDragDepth.value > 0)
const canDropCurrentDirectoryMove = computed(() => {
  const payload = getActiveChemSSHFileDragPayload()
  return Boolean(payload && isValidCurrentDirectoryMove(payload))
})
const canDropCurrentDirectoryCopy = computed(() => {
  const payload = getActiveChemSSHFileDragPayload()
  return Boolean(payload && isValidCurrentDirectoryCopy(payload))
})

const currentDirectoryItem = computed<FileItem>(() => ({
  name: currentPath.value.split(/[\\/]/).filter(Boolean).pop() ?? currentPath.value,
  path: currentPath.value,
  type: 'directory',
  size: null,
  mtime: '',
  extension: '',
  preview_type: 'directory',
  format: null
}))

const DIRECTORY_HISTORY_LIMIT = 20
const CONTEXT_MENU_WIDTH = 190
const CONTEXT_MENU_HEIGHT = 156

const launcherSystemIconProvider = computed(() => ({
  enabled: Boolean(
    props.launcherBridgeCapabilities?.enabled &&
    props.launcherBridgeCapabilities.features.system_icons &&
    props.launcherBridgeCapabilities.endpoints.icon
  ),
  iconUrl: (item: FileItem) => launcherFileIconUrl(item, 16)
}))

onMounted(() => {
  void loadDirectory(currentPath.value || undefined)
  void loadArchiveTools()
  window.addEventListener('click', closeContextMenu)
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('resize', closeContextMenu)
  window.addEventListener('scroll', closeContextMenu, true)
})

watch(
  () => props.initialPath,
  path => {
    if (!path || path === currentPath.value) return
    void loadDirectory(path, { recordHistory: true })
  }
)

watch(
  () => props.refreshToken,
  (token, previous) => {
    if (token === previous) return
    const targetPath = props.initialPath && props.initialPath !== currentPath.value
      ? props.initialPath
      : currentPath.value || props.initialPath || undefined
    void loadDirectory(targetPath, { recordHistory: false, refresh: true })
  }
)

async function loadDirectory(path?: string, options: { recordHistory?: boolean; refresh?: boolean } = {}) {
  const previousPath = currentPath.value
  loading.value = true
  try {
    const response = await listFiles(path || undefined, { refresh: options.refresh })
    listing.value = response
    directoryLoadError.value = null
    currentPath.value = response.path
    pathInput.value = response.path
    if (options.recordHistory) recordDirectoryHistory(previousPath, response.path)
    selectedItems.value = []
    selectedItem.value = null
    emit('path-change', response.path)
  } catch (error) {
    const message = apiErrorMessage(error, 'message.directoryLoadFailed')
    ElMessage.error(message)
    listing.value = null
    selectedItems.value = []
    selectedItem.value = null
    directoryLoadError.value = {
      path: (path ?? '').trim(),
      message,
      code: error instanceof ApiError ? error.code : undefined
    }
    if (path?.trim()) pathInput.value = path
  } finally {
    loading.value = false
  }
}

async function openDefaultDirectory() {
  const target = defaultDirectory.value
  if (!target) return
  await loadDirectory(target, { recordHistory: true, refresh: true })
}

function openPath(path: string) {
  void loadDirectory(path.trim() || undefined, { recordHistory: true })
}

function goBack() {
  const path = directoryHistory.value[0]
  if (!path) return
  directoryHistory.value = directoryHistory.value.slice(1)
  void loadDirectory(path, { recordHistory: false })
}

function openHistoryPath(path: string) {
  if (!path) return
  directoryHistory.value = directoryHistory.value.filter(item => item !== path)
  void loadDirectory(path, { recordHistory: false })
}

function openItem(item: FileItem) {
  if (item.type === 'directory') {
    void loadDirectory(item.path, { recordHistory: true })
    return
  }
  emit('open-file', item)
}

function recordDirectoryHistory(previousPath: string, nextPath: string) {
  if (!previousPath || previousPath === nextPath) return
  directoryHistory.value = [previousPath, ...directoryHistory.value.filter(path => path !== previousPath)].slice(0, DIRECTORY_HISTORY_LIMIT)
}

function directoryHistoryLabel(path: string) {
  return path
}

function handleSelectionChange(items: FileItem[], primary: FileItem | null) {
  selectedItems.value = items
  selectedItem.value = primary ?? items[items.length - 1] ?? null
  emit('selection-change', items, primary)
}

function handleContextMenu(item: FileItem, event: MouseEvent) {
  event.preventDefault()
  if (!selectedItems.value.some(selected => selected.path === item.path)) {
    selectedItems.value = [item]
    selectedItem.value = item
    emit('selection-change', selectedItems.value, item)
  }
  contextMenu.value = {
    visible: true,
    x: clamp(event.clientX, 8, window.innerWidth - CONTEXT_MENU_WIDTH - 8),
    y: clamp(event.clientY, 8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8),
    opensLeft: event.clientX > window.innerWidth - 360,
    blank: false,
    item
  }
}

function handleBlankContextMenu(event: MouseEvent) {
  contextMenu.value = {
    visible: true,
    x: clamp(event.clientX, 8, window.innerWidth - CONTEXT_MENU_WIDTH - 8),
    y: clamp(event.clientY, 8, window.innerHeight - CONTEXT_MENU_HEIGHT - 8),
    opensLeft: event.clientX > window.innerWidth - 360,
    blank: true,
    item: null
  }
}

function closeContextMenu() {
  if (!contextMenu.value.visible) return
  contextMenu.value = {
    visible: false,
    x: 0,
    y: 0,
    opensLeft: false,
    blank: false,
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
    ElMessage.success(localizeBackendMessage(response.message) || t('submit.jobSubmitted', { id: response.job_id ?? '' }))
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, 'message.submitFailed'))
  }
}

function canLauncherOpenItem(item: FileItem, mode: 'default' | 'text') {
  if (item.type !== 'file') return false
  const capabilities = props.launcherBridgeCapabilities
  if (!capabilities?.enabled) return false
  const hasFeature = mode === 'default'
    ? Boolean(capabilities.features.open_default && capabilities.endpoints.open)
    : Boolean(capabilities.features.open_text && capabilities.endpoints.open_text)
  if (!hasFeature) return false
  return isPathInsideWorkspace(item.path, props.workspaceRoot || capabilities.workspace_root || '')
}

async function openContextWithLocalApp() {
  const item = contextMenu.value.item
  if (!item || !canLauncherOpenItem(item, 'default')) return
  closeContextMenu()
  try {
    await openWithLocalApp(item.path)
    ElMessage.success(t('message.localOpenStarted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.localOpenFailed'))
  }
}

async function openContextWithNotepad() {
  const item = contextMenu.value.item
  if (!item || !canLauncherOpenItem(item, 'text')) return
  closeContextMenu()
  try {
    await openWithNotepad(item.path)
    ElMessage.success(t('message.localOpenStarted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.localOpenFailed'))
  }
}

function renameContextItem() {
  closeContextMenu()
  void promptRename()
}

function deleteContextItems() {
  closeContextMenu()
  void confirmDelete()
}

function copyContextItems() {
  closeContextMenu()
  if (selectedItems.value.length === 0) return
  setFileClipboard(selectedItems.value)
  ElMessage.success(t('message.copiedToClipboard', { count: selectedItems.value.length }))
}

const archiveTools = ref<ArchiveTools | null>(null)
const archiveFormats = computed<ArchiveFormat[]>(() => archiveTools.value?.formats ?? [])
const canExtractSelection = computed(() => {
  const items = selectedItems.value
  if (items.length !== 1 || items[0].type !== 'file') return false
  return canExtractName(items[0].name, archiveTools.value)
})

async function loadArchiveTools() {
  archiveTools.value = await getArchiveTools().catch(() => null)
}

async function compressSelection(format: ArchiveFormat) {
  closeContextMenu()
  const paths = selectedItems.value.map(item => item.path)
  const target = currentPath.value
  if (paths.length === 0 || !target) return
  try {
    const response = await compressPaths(paths, target, format)
    await loadDirectory(target, { refresh: true })
    emit('directories-change', [target])
    ElMessage.success(t('message.compressed', { name: response.path?.split(/[\\/]/).pop() ?? format }))
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, 'message.archiveFailed'))
  }
}

async function extractSelection() {
  closeContextMenu()
  const item = selectedItems.value[0]
  const target = currentPath.value
  if (!item || !target) return
  try {
    await extractArchive(item.path, target)
    await loadDirectory(target, { refresh: true })
    emit('directories-change', [target])
    ElMessage.success(t('message.extracted'))
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, 'message.archiveFailed'))
  }
}

function selectAllFromMenu() {
  closeContextMenu()
  handleSelectionChange([...visibleItems.value], visibleItems.value[0] ?? null)
}

function refreshFromMenu() {
  closeContextMenu()
  void loadDirectory(currentPath.value, { refresh: true })
}

async function copyFolderPathFromMenu() {
  const path = currentPath.value
  closeContextMenu()
  if (!path) return
  try {
    await copyTextToClipboard(path)
    ElMessage.success(t('message.pathCopied'))
  } catch {
    ElMessage.error(t('message.clipboardFailed'))
  }
}

function newFolderFromMenu() {
  closeContextMenu()
  void promptMkdir()
}

function newFileFromMenu() {
  closeContextMenu()
  void promptCreateFile()
}

function pasteFromMenu() {
  closeContextMenu()
  if (!currentPath.value) return
  void handleCopyItems(fileClipboardItems.value, currentDirectoryItem.value)
}

async function copyContextPath() {
  const path = selectedItems.value[0]?.path ?? contextMenu.value.item?.path
  if (!path) return
  closeContextMenu()
  try {
    await copyTextToClipboard(path)
    ElMessage.success(t('message.pathCopied'))
  } catch {
    ElMessage.error(t('message.clipboardFailed'))
  }
}

async function copyTextToClipboard(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    if (!document.execCommand('copy')) throw new Error('copy failed')
  } finally {
    textarea.remove()
  }
}

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

async function promptCreateFile() {
  let result: { value: string }
  try {
    result = await ElMessageBox.prompt(t('prompt.fileName'), t('prompt.newFile'), {
      inputPattern: SAFE_UPLOAD_SEGMENT_RE,
      inputErrorMessage: t('message.namePattern'),
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }
  const name = result.value
  if ((listing.value?.items ?? []).some(item => item.name === name)) {
    ElMessage.error(t('message.pathExists'))
    return
  }
  try {
    await writeFile(joinDisplayPath(currentPath.value, name), '')
    await loadDirectory(currentPath.value, { refresh: true })
    ElMessage.success(t('message.fileCreated'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.createFailed'))
  }
}

async function promptMkdir() {
  let result: { value: string }
  try {
    result = await ElMessageBox.prompt(t('prompt.folderName'), t('prompt.newFolder'), {
      inputPattern: SAFE_UPLOAD_SEGMENT_RE,
      inputErrorMessage: t('message.namePattern'),
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }
  try {
    await makeDirectory(currentPath.value, result.value)
    await loadDirectory(currentPath.value, { refresh: true })
    ElMessage.success(t('message.folderCreated'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.createFailed'))
  }
}

async function handleUpload(files: File[]) {
  await handleUploadEntries(filesToUploadEntries(files), currentPath.value)
}

async function handleUploadEntries(entries: UploadEntry[], targetPath = currentPath.value) {
  if (entries.length === 0) return
  const preparedResult = await prepareUploadEntries(entries, {
    targetPath,
    promptConflict: promptUploadConflict
  })
  if (preparedResult.invalidCount > 0) ElMessage.error(t('message.uploadInvalidPath', { count: preparedResult.invalidCount }))
  if (preparedResult.renamedCount > 0) ElMessage.info(t('message.uploadPathRenamed', { count: preparedResult.renamedCount }))
  const prepared = preparedResult.entries
  if (prepared.length === 0) {
    return
  }
  const proceed = await confirmOversizedUpload(systemStore.systemInfo, prepared)
  if (!proceed) return

  let uploaded = 0
  let firstError: unknown = null
  for (const entry of prepared) {
    try {
      await uploadFile(targetPath, entry.file, { relativePath: entry.relativePath })
      uploaded += 1
    } catch (error) {
      firstError ??= error
    }
  }

  await loadDirectory(currentPath.value, { refresh: true })
  const failed = prepared.length - uploaded + preparedResult.invalidCount
  if (failed === 0) {
    ElMessage.success(prepared.length === 1 ? t('message.uploadComplete') : t('message.uploadCompleteMany', { count: prepared.length }))
    return
  }

  const message = firstError instanceof Error
    ? firstError.message
    : preparedResult.invalidCount > 0
      ? t('message.uploadInvalidPath', { count: preparedResult.invalidCount })
      : t('message.uploadFailed')
  ElMessage.error(t('message.uploadPartial', { message, uploaded, failed }))
}

function promptUploadConflict(name: string) {
  return new Promise<UploadConflictResolution>(resolve => {
    uploadConflictDialog.value = {
      visible: true,
      mode: 'upload',
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
    mode: 'upload',
    name: '',
    applyAll: false,
    resolve: null
  }
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
    triggerBlobDownload(response.blob, response.filename ?? 'chemssh-selection.zip')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.downloadFailed'))
  }
}

function promptMoveConflict(name: string) {
  return new Promise<UploadConflictResolution>(resolve => {
    uploadConflictDialog.value = {
      visible: true,
      mode: 'move',
      name,
      applyAll: false,
      resolve
    }
  })
}

function promptCopyConflict(name: string) {
  return new Promise<UploadConflictResolution>(resolve => {
    uploadConflictDialog.value = {
      visible: true,
      mode: 'copy',
      name,
      applyAll: false,
      resolve
    }
  })
}

async function handleMoveItems(items: FileItem[], targetDirectory: FileItem) {
  if (items.length === 0) return
  const changedDirectories = moveChangedDirectories(items, targetDirectory.path)
  try {
    const prepared = await prepareMoveEntries(items, {
      targetPath: targetDirectory.path,
      promptConflict: promptMoveConflict
    })
    if (prepared.cancelled) return
    if (prepared.entries.length === 0) {
      ElMessage.info(t('message.moveSkipped'))
      return
    }
    await movePaths(prepared.entries.map(entry => entry.path), targetDirectory.path, prepared.entries)
    await loadDirectory(currentPath.value, { refresh: true })
    emit('directories-change', changedDirectories)
    ElMessage.success(t('message.moved'))
  } catch (error) {
    ElMessage.error(moveApiErrorMessage(error))
  }
}

async function handleCopyItems(
  items: Pick<FileItem, 'name' | 'path' | 'type'>[],
  targetDirectory: FileItem
) {
  if (items.length === 0) return
  const changedDirectories = copyChangedDirectories(targetDirectory.path)
  try {
    const prepared = await prepareMoveEntries(items, {
      targetPath: targetDirectory.path,
      promptConflict: promptCopyConflict
    })
    if (prepared.cancelled) return
    if (prepared.entries.length === 0) {
      ElMessage.info(t('message.copySkipped'))
      return
    }
    await copyPaths(prepared.entries.map(entry => entry.path), targetDirectory.path, prepared.entries)
    await loadDirectory(currentPath.value, { refresh: true })
    emit('directories-change', changedDirectories)
    ElMessage.success(t('message.copied'))
  } catch (error) {
    ElMessage.error(copyApiErrorMessage(error))
  }
}

async function promptRename() {
  if (selectedItems.value.length !== 1 || !selectedItem.value) return
  const oldPath = selectedItem.value.path
  let result: { value: string }
  try {
    result = await ElMessageBox.prompt(t('prompt.newName'), t('prompt.rename'), {
      inputValue: selectedItem.value.name,
      inputPattern: SAFE_UPLOAD_SEGMENT_RE,
      inputErrorMessage: t('message.namePattern'),
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }
  const separator = oldPath.includes('\\') ? '\\' : '/'
  const parent = oldPath.split(/[\\/]/).slice(0, -1).join(separator)
  try {
    await renamePath(oldPath, `${parent}${separator}${result.value}`)
    await loadDirectory(currentPath.value, { refresh: true })
    ElMessage.success(t('message.renamed'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.renameFailed'))
  }
}

async function confirmDelete() {
  const targets = selectedItems.value.length > 0 ? selectedItems.value : selectedItem.value ? [selectedItem.value] : []
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(t('prompt.deleteItems', { count: targets.length }), t('prompt.confirmDelete'), {
      type: 'warning',
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }
  try {
    for (const item of targets) {
      await deletePath(item.path)
    }
    selectedItems.value = []
    selectedItem.value = null
    await loadDirectory(currentPath.value, { refresh: true })
    ElMessage.success(t('message.deleted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.deleteFailed'))
  }
}

function handleDragEnter(event: DragEvent) {
  if (hasChemSSHFileDrag(event)) {
    currentDirectoryDragDepth.value = 1
    return
  }
  if (!hasFileDrag(event)) return
  event.preventDefault()
  externalDropTargetPath.value = null
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleDragOver(event: DragEvent) {
  if (hasChemSSHFileDrag(event)) {
    currentDirectoryDragDepth.value = 1
    if (isDirectoryRowDropTarget(event)) return
    const payload = fileDragPayloadForEvent(event)
    if (!payload || !isValidCurrentDirectoryMove(payload)) {
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'
      return
    }
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
    return
  }
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleDragLeave(event: DragEvent) {
  if (!hasFileDrag(event) && !hasChemSSHFileDrag(event)) return
  if (hasFileDrag(event)) event.preventDefault()
  const root = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const related = event.relatedTarget instanceof Node ? event.relatedTarget : null
  if (root && related && root.contains(related)) return
  dragUploadDepth.value = 0
  currentDirectoryDragDepth.value = 0
  externalDropTargetPath.value = null
}

function handleDrop(event: DragEvent) {
  if (hasChemSSHFileDrag(event)) {
    const payload = fileDragPayloadForEvent(event)
    dragUploadDepth.value = 0
    currentDirectoryDragDepth.value = 0
    if (!payload || isDirectoryRowDropTarget(event) || !isValidCurrentDirectoryMove(payload)) return
    event.preventDefault()
    void handleMoveItems(payload.items as FileItem[], currentDirectoryItem.value)
    return
  }
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 0
  externalDropTargetPath.value = null
  void collectDropUploadEntries(event).then(entries => {
    if (entries.length > 0) void handleUploadEntries(entries)
  })
}

// Dropping on a directory row uploads into that folder instead of the listing
// directory; the row already decided the target, so only the files are read here.
async function handleExternalUploadDrop(target: FileItem, event: DragEvent) {
  dragUploadDepth.value = 0
  currentDirectoryDragDepth.value = 0
  externalDropTargetPath.value = null
  const entries = await collectDropUploadEntries(event)
  if (entries.length > 0) await handleUploadEntries(entries, target.path)
}

function handleCurrentDirectoryActionDragOver(action: 'move' | 'copy', event: DragEvent) {
  if (!hasChemSSHFileDrag(event)) return
  currentDirectoryDragDepth.value = 1
  const payload = fileDragPayloadForEvent(event)
  const isValid = action === 'move'
    ? payload && isValidCurrentDirectoryMove(payload)
    : payload && isValidCurrentDirectoryCopy(payload)
  if (!isValid) {
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'
    return
  }
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = action
}

function handleCurrentDirectoryDropDragLeave(event: DragEvent) {
  const target = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const related = event.relatedTarget instanceof Node ? event.relatedTarget : null
  if (target && related && target.contains(related)) return
  if (!hasFileDrag(event)) currentDirectoryDragDepth.value = Math.max(0, currentDirectoryDragDepth.value - 1)
}

function handleCurrentDirectoryActionDrop(action: 'move' | 'copy', event: DragEvent) {
  const payload = fileDragPayloadForEvent(event)
  dragUploadDepth.value = 0
  currentDirectoryDragDepth.value = 0
  const isValid = action === 'move'
    ? payload && isValidCurrentDirectoryMove(payload)
    : payload && isValidCurrentDirectoryCopy(payload)
  if (!payload || !isValid) return
  event.preventDefault()
  if (action === 'copy') {
    void handleCopyItems(payload.items as FileItem[], currentDirectoryItem.value)
    return
  }
  void handleMoveItems(payload.items as FileItem[], currentDirectoryItem.value)
}

function fileDragPayloadForEvent(event: DragEvent) {
  return readChemSSHFileDrag(event.dataTransfer) ?? getActiveChemSSHFileDragPayload()
}

function isDirectoryRowDropTarget(event: DragEvent) {
  const target = event.target instanceof Element ? event.target : null
  return Boolean(target?.closest('.file-row.is-directory'))
}

function isValidCurrentDirectoryMove(payload: ChemSSHFileDragPayload) {
  if (!currentPath.value || payload.paths.length === 0) return false
  const targetPath = normalizePath(currentPath.value)
  return payload.items.every(item => {
    const sourcePath = normalizePath(item.path)
    if (sourcePath === targetPath) return false
    if (parentDirectoryPath(sourcePath) === targetPath) return false
    if (item.type === 'directory' && isPathInside(targetPath, sourcePath)) return false
    return true
  })
}

function isValidCurrentDirectoryCopy(payload: ChemSSHFileDragPayload) {
  if (!currentPath.value || payload.paths.length === 0) return false
  const targetPath = normalizePath(currentPath.value)
  return payload.items.every(item => {
    const sourcePath = normalizePath(item.path)
    if (sourcePath === targetPath) return false
    if (item.type === 'directory' && isPathInside(targetPath, sourcePath)) return false
    return true
  })
}

function moveChangedDirectories(items: FileItem[], targetPath: string) {
  const paths = new Set<string>([currentPath.value, targetPath])
  for (const item of items) {
    const parent = parentDirectoryPath(item.path)
    if (parent) paths.add(parent)
  }
  return Array.from(paths).filter(Boolean)
}

function copyChangedDirectories(targetPath: string) {
  return Array.from(new Set([currentPath.value, targetPath])).filter(Boolean)
}



function normalizePath(path: string) {
  return path.replace(/\\/g, '/').replace(/\/+$/, '')
}

function isPathInside(path: string, parent: string) {
  return path === parent || path.startsWith(`${parent}/`)
}

onBeforeUnmount(() => {
  if (uploadConflictDialog.value.resolve) chooseUploadConflict('cancel')
  window.removeEventListener('click', closeContextMenu)
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('scroll', closeContextMenu, true)
})
</script>

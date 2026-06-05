<template>
  <div
    class="canvas-file-manager"
    :class="{ 'is-drag-upload': dragUploadActive }"
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
          <el-tooltip :content="t('toolbar.go')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false">
            <el-button :icon="ArrowRight" @click="openPath(pathInput)" />
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
      @create-file="promptCreateFile"
      @mkdir="promptMkdir"
      @upload="handleUpload"
      @download="downloadSelected"
      @rename="promptRename"
      @delete="confirmDelete"
      @update:show-hidden-files="value => showHiddenFiles = value"
    />

    <div class="canvas-file-tree-shell" v-loading="loading">
      <FileTree
        :items="visibleItems"
        :selected-items="selectedItems"
        @selection-change="handleSelectionChange"
        @context-menu="handleContextMenu"
        @open="openItem"
      />
    </div>

    <div v-if="dragUploadActive" class="canvas-file-drop-overlay" aria-live="polite">
      <el-icon><UploadFilled /></el-icon>
      <span>{{ t('file.dropUpload') }}</span>
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
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight, UploadFilled } from '@element-plus/icons-vue'
import { downloadUrl } from '../../api/http'
import {
  deletePath,
  downloadArchive,
  listFiles,
  makeDirectory,
  renamePath,
  uploadFile,
  writeFile,
  type DirectoryListing,
  type FileItem
} from '../../api/files'
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
import { t } from '../../i18n'
import FileToolbar from '../FileToolbar.vue'
import FileTree from '../FileTree.vue'

const props = defineProps<{
  initialPath?: string | null
}>()

const emit = defineEmits<{
  'path-change': [path: string]
  'open-file': [item: FileItem]
  'selection-change': [items: FileItem[], primary: FileItem | null]
}>()

const listing = ref<DirectoryListing | null>(null)
const currentPath = ref(props.initialPath ?? '')
const pathInput = ref(props.initialPath ?? '')
const selectedItems = ref<FileItem[]>([])
const selectedItem = ref<FileItem | null>(null)
const showHiddenFiles = ref(false)
const loading = ref(false)
const dragUploadDepth = ref(0)
const uploadConflictDialog = ref<UploadConflictDialogState>({
  visible: false,
  name: '',
  applyAll: false,
  resolve: null
})

type UploadConflictDialogState = {
  visible: boolean
  name: string
  applyAll: boolean
  resolve: ((resolution: UploadConflictResolution) => void) | null
}

const visibleItems = computed(() => {
  const items = listing.value?.items ?? []
  return showHiddenFiles.value ? items : items.filter(item => !item.name.startsWith('.'))
})
const dragUploadActive = computed(() => dragUploadDepth.value > 0)

onMounted(() => {
  void loadDirectory(currentPath.value || undefined)
})

watch(
  () => props.initialPath,
  path => {
    if (!path || path === currentPath.value) return
    void loadDirectory(path)
  }
)

async function loadDirectory(path?: string) {
  loading.value = true
  try {
    const response = await listFiles(path || undefined)
    listing.value = response
    currentPath.value = response.path
    pathInput.value = response.path
    selectedItems.value = []
    selectedItem.value = null
    emit('path-change', response.path)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.directoryLoadFailed'))
  } finally {
    loading.value = false
  }
}

function openPath(path: string) {
  void loadDirectory(path.trim() || undefined)
}

function goUp() {
  if (!listing.value?.parent) return
  void loadDirectory(listing.value.parent)
}

function openItem(item: FileItem) {
  if (item.type === 'directory') {
    void loadDirectory(item.path)
    return
  }
  emit('open-file', item)
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
    await loadDirectory(currentPath.value)
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
    await loadDirectory(currentPath.value)
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

  await loadDirectory(currentPath.value)
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
    await loadDirectory(currentPath.value)
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
    await loadDirectory(currentPath.value)
    ElMessage.success(t('message.deleted'))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.deleteFailed'))
  }
}

function handleDragEnter(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleDragOver(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 1
  setUploadDropEffect(event)
}

function handleDragLeave(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  const root = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const related = event.relatedTarget instanceof Node ? event.relatedTarget : null
  if (root && related && root.contains(related)) return
  dragUploadDepth.value = 0
}

function handleDrop(event: DragEvent) {
  if (!hasFileDrag(event)) return
  event.preventDefault()
  dragUploadDepth.value = 0
  void collectDropUploadEntries(event).then(entries => {
    if (entries.length > 0) void handleUploadEntries(entries)
  })
}

onBeforeUnmount(() => {
  if (uploadConflictDialog.value.resolve) chooseUploadConflict('cancel')
})
</script>

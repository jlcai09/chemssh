<template>
  <div class="canvas-preview-window">
    <div class="canvas-preview-pathbar">
      <el-input
        v-model="pathInput"
        size="small"
        clearable
        spellcheck="false"
        :placeholder="t('canvas.previewPath')"
        @keyup.enter="openPath(pathInput)"
      >
        <template #append>
          <el-tooltip :content="t('toolbar.go')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false">
            <el-button :icon="ArrowRight" @click="openPath(pathInput)" />
          </el-tooltip>
        </template>
      </el-input>
    </div>
    <FilePreview
      :file="preview"
      :ase-structure="asePreview"
      :mode="previewMode"
      :loading="loading"
      :structure-candidate="structureCandidate"
      :structure-error="previewError"
      @update:mode="setPreviewMode"
      @refresh="refreshPreview"
      @save="savePreview"
      @dragover="handlePreviewDragOver"
      @drop="handlePreviewDrop"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import { readFile, writeFile, type FileReadResponse, type PreviewType } from '../../api/files'
import { hasChemSSHFileDrag, readChemSSHFileDrag } from '../../api/fileDrag'
import { isStructurePreviewPath } from '../../api/fileTypes'
import {
  confirmLargePreview,
  isLargePreviewError,
  normalizeTextLineEndings,
  previewApiErrorMessage
} from '../../api/previewUtils'
import { ASE_STRUCTURE_SOURCE, readStructurePreview } from '../../api/structures'
import { t } from '../../i18n'
import type { AsePreviewResponse, StructureSource } from '../../types/structure'
import FilePreview from '../FilePreview.vue'

type PreviewMode = 'structure' | 'text'
type PreviewMetadata = {
  previewType?: PreviewType | null
  format?: string | null
}

const props = defineProps<{
  path?: string | null
  previewType?: PreviewType | null
  format?: string | null
}>()

const emit = defineEmits<{
  'path-change': [path: string, metadata?: PreviewMetadata]
}>()

const pathInput = ref(props.path ?? '')
const preview = ref<FileReadResponse | null>(null)
const asePreview = ref<AsePreviewResponse | null>(null)
const previewMode = ref<PreviewMode>('text')
const previewError = ref<string | null>(null)
const loading = ref(false)
const localMetadataPath = ref<string | null>(null)
const localPreviewType = ref<PreviewType | null>(null)
const localFormat = ref<string | null>(null)
const forcedText = new Set<string>()
const forcedStructure = new Set<string>()

const structureCandidate = computed(() => Boolean(pathInput.value && isStructureCandidate(pathInput.value)))

watch(
  () => props.path,
  path => {
    if (!path) return
    if (path === pathInput.value && (preview.value || asePreview.value)) return
    pathInput.value = path
    void openPath(path, { previewType: props.previewType, format: props.format })
  },
  { immediate: true }
)

async function openPath(path: string, metadata?: PreviewMetadata) {
  const nextPath = path.trim()
  if (!nextPath) {
    preview.value = null
    asePreview.value = null
    clearLocalMetadata()
    emit('path-change', '')
    return
  }
  applyLocalMetadata(nextPath, metadata)
  pathInput.value = nextPath
  emit('path-change', nextPath, metadata)
  loading.value = true
  previewError.value = null
  try {
    if (isStructureCandidate(nextPath)) {
      previewMode.value = 'structure'
      try {
        asePreview.value = await readStructureWithConfirmation(nextPath, ASE_STRUCTURE_SOURCE, structureFormat(nextPath))
        preview.value = null
        return
      } catch (error) {
        previewError.value = previewApiErrorMessage(error)
        previewMode.value = 'text'
      }
    }
    preview.value = await readTextWithConfirmation(nextPath)
    asePreview.value = null
    previewMode.value = 'text'
  } catch (error) {
    preview.value = null
    asePreview.value = null
    ElMessage.error(previewApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function refreshPreview() {
  if (!pathInput.value) return
  await openPath(pathInput.value)
}

async function setPreviewMode(mode: PreviewMode) {
  previewMode.value = mode
  if (!pathInput.value) return
  loading.value = true
  try {
    if (mode === 'structure') {
      asePreview.value = await readStructureWithConfirmation(pathInput.value, ASE_STRUCTURE_SOURCE, structureFormat(pathInput.value))
    } else if (!preview.value || preview.value.path !== pathInput.value) {
      preview.value = await readTextWithConfirmation(pathInput.value)
    }
  } catch (error) {
    ElMessage.error(previewApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function savePreview(content: string) {
  if (!preview.value) return
  try {
    await writeFile(preview.value.path, normalizeTextLineEndings(content))
    ElMessage.success(t('message.saved'))
    preview.value = await readTextWithConfirmation(preview.value.path)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('message.saveFailed'))
  }
}

async function readTextWithConfirmation(path: string) {
  try {
    return await readFile(path, forcedText.has(path))
  } catch (error) {
    if (!isLargePreviewError(error, 'FILE_TOO_LARGE')) throw error
    const confirmed = await confirmLargePreview(error, 'text')
    if (!confirmed) return null
    forcedText.add(path)
    return readFile(path, true)
  }
}

async function readStructureWithConfirmation(path: string, source: StructureSource, format?: string | null) {
  const cacheKey = `${source.id}:${path}`
  try {
    return await readStructurePreview(source, path, format, forcedStructure.has(cacheKey))
  } catch (error) {
    if (!isLargePreviewError(error, 'STRUCTURE_FILE_TOO_LARGE')) throw error
    const confirmed = await confirmLargePreview(error, 'structure')
    if (!confirmed) return null
    forcedStructure.add(cacheKey)
    return readStructurePreview(source, path, format, true)
  }
}

function propMetadataApplies(path: string) {
  return Boolean(props.path && path === props.path)
}

function localMetadataApplies(path: string) {
  return localMetadataPath.value === path
}

function metadataPreviewType(path: string) {
  if (localMetadataApplies(path)) return localPreviewType.value
  return propMetadataApplies(path) ? props.previewType : null
}

function structureFormat(path: string) {
  if (localMetadataApplies(path)) return localFormat.value
  return propMetadataApplies(path) ? props.format : null
}

function isStructureCandidate(path: string) {
  return isStructurePreviewPath(path, metadataPreviewType(path))
}

function applyLocalMetadata(path: string, metadata?: PreviewMetadata) {
  if (!metadata) {
    clearLocalMetadata()
    return
  }
  localMetadataPath.value = path
  localPreviewType.value = metadata.previewType ?? null
  localFormat.value = metadata.format ?? null
}

function clearLocalMetadata() {
  localMetadataPath.value = null
  localPreviewType.value = null
  localFormat.value = null
}

function handlePreviewDragOver(event: DragEvent) {
  if (!hasChemSSHFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handlePreviewDrop(event: DragEvent) {
  const payload = readChemSSHFileDrag(event.dataTransfer)
  const item = payload?.items[0]
  const path = item?.path ?? payload?.paths[0]
  if (!path) return
  event.preventDefault()
  void openPath(path, {
    previewType: item?.preview_type ?? null,
    format: item?.format ?? null
  })
}

</script>

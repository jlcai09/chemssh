<template>
  <div class="file-toolbar">
    <el-tooltip :content="t('toolbar.refresh')" placement="bottom">
      <el-button :icon="Refresh" circle @click="$emit('refresh')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.up')" placement="bottom">
      <el-button :icon="Back" circle :disabled="!canGoUp" @click="$emit('go-up')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.newFolder')" placement="bottom">
      <el-button :icon="FolderAdd" circle @click="$emit('mkdir')" />
    </el-tooltip>
    <el-tooltip :content="props.showHiddenFiles ? t('toolbar.hideHidden') : t('toolbar.showHidden')" placement="bottom">
      <el-button
        :icon="props.showHiddenFiles ? View : Hide"
        circle
        :type="props.showHiddenFiles ? 'primary' : 'default'"
        @click="emit('update:showHiddenFiles', !props.showHiddenFiles)"
      />
    </el-tooltip>

    <div class="toolbar-spacer" />

    <el-tooltip :content="t('toolbar.upload')" placement="bottom">
      <el-button :icon="Upload" circle @click="pickFile" />
    </el-tooltip>
    <input ref="fileInput" class="hidden-input" type="file" multiple @change="handleUpload" />
    <el-tooltip :content="t('toolbar.download')" placement="bottom">
      <el-button :icon="Download" circle :disabled="selectedCount === 0" @click="$emit('download')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.rename')" placement="bottom">
      <el-button :icon="Edit" circle :disabled="selectedCount !== 1" @click="$emit('rename')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.delete')" placement="bottom">
      <el-button :icon="Delete" circle :disabled="selectedCount === 0" type="danger" @click="$emit('delete')" />
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Back, Delete, Download, Edit, FolderAdd, Hide, Refresh, Upload, View } from '@element-plus/icons-vue'
import type { FileItem } from '../api/files'
import { t } from '../i18n'

const props = withDefaults(
  defineProps<{
    selectedItems?: FileItem[]
    canGoUp: boolean
    showHiddenFiles?: boolean
  }>(),
  {
    selectedItems: () => [],
    showHiddenFiles: false
  }
)

const emit = defineEmits<{
  refresh: []
  'go-up': []
  mkdir: []
  upload: [files: File[]]
  download: []
  rename: []
  delete: []
  'update:showHiddenFiles': [value: boolean]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedCount = computed(() => props.selectedItems.length)

function pickFile() {
  fileInput.value?.click()
}

function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length > 0) {
    emit('upload', files)
  }
  input.value = ''
}
</script>

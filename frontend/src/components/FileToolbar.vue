<template>
  <div class="file-toolbar">
    <el-tooltip :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
      <el-button :icon="Refresh" circle @click="$emit('refresh')" />
    </el-tooltip>
    <div class="toolbar-history-control">
      <el-tooltip :content="t('toolbar.back')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
        <el-button :icon="Back" circle :disabled="!canGoBack" @click="$emit('go-back')" />
      </el-tooltip>
      <el-dropdown trigger="click" :disabled="historyEntries.length === 0" @command="selectHistoryPath">
        <button
          class="toolbar-history-menu-button"
          type="button"
          :disabled="historyEntries.length === 0"
          :aria-label="t('toolbar.history')"
        >
          <el-icon><CaretBottom /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="entry in historyEntries" :key="entry.path" :command="entry.path">
              <span class="toolbar-history-entry" :title="entry.path">{{ entry.label }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <div class="toolbar-menu">
      <el-button :icon="Plus" circle aria-haspopup="menu" @click.prevent />
      <div class="toolbar-submenu" role="menu">
        <el-tooltip :content="t('toolbar.newFile')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="toolbar-submenu-button" type="button" role="menuitem" :aria-label="t('toolbar.newFile')" @click="emit('create-file')">
            <el-icon><DocumentAdd /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip :content="t('toolbar.newFolder')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="toolbar-submenu-button" type="button" role="menuitem" :aria-label="t('toolbar.newFolder')" @click="emit('mkdir')">
            <el-icon><FolderAdd /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
    <el-tooltip :content="props.showHiddenFiles ? t('toolbar.hideHidden') : t('toolbar.showHidden')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
      <el-button
        :icon="props.showHiddenFiles ? View : Hide"
        circle
        :type="props.showHiddenFiles ? 'primary' : 'default'"
        @click="emit('update:showHiddenFiles', !props.showHiddenFiles)"
      />
    </el-tooltip>

    <div class="toolbar-spacer" />

    <div class="toolbar-menu">
      <el-button :icon="Upload" circle aria-haspopup="menu" @click.prevent />
      <div class="toolbar-submenu" role="menu">
        <el-tooltip :content="t('toolbar.uploadFile')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="toolbar-submenu-button" type="button" role="menuitem" :aria-label="t('toolbar.uploadFile')" @click="pickFile">
            <el-icon><Upload /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip :content="t('toolbar.uploadFolder')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="toolbar-submenu-button" type="button" role="menuitem" :aria-label="t('toolbar.uploadFolder')" @click="pickFolder">
            <el-icon><FolderOpened /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
    <input ref="fileInput" class="hidden-input" type="file" multiple @change="handleUpload" />
    <input
      ref="folderInput"
      class="hidden-input"
      type="file"
      multiple
      webkitdirectory
      directory
      @change="handleUpload"
    />
    <el-tooltip :content="t('toolbar.download')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
      <el-button :icon="Download" circle :disabled="selectedCount === 0" @click="$emit('download')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.rename')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
      <el-button :icon="Edit" circle :disabled="selectedCount !== 1" @click="$emit('rename')" />
    </el-tooltip>
    <el-tooltip :content="t('toolbar.delete')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
      <el-button :icon="Delete" circle :disabled="selectedCount === 0" type="danger" @click="$emit('delete')" />
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Back, CaretBottom, Delete, DocumentAdd, Download, Edit, FolderAdd, FolderOpened, Hide, Plus, Refresh, Upload, View } from '@element-plus/icons-vue'
import type { FileItem } from '../api/files'
import { t } from '../i18n'

export type DirectoryHistoryEntry = {
  path: string
  label: string
}

const props = withDefaults(
  defineProps<{
    selectedItems?: FileItem[]
    canGoBack: boolean
    historyEntries?: DirectoryHistoryEntry[]
    showHiddenFiles?: boolean
  }>(),
  {
    selectedItems: () => [],
    historyEntries: () => [],
    showHiddenFiles: false
  }
)

const emit = defineEmits<{
  refresh: []
  'go-back': []
  'history-select': [path: string]
  'create-file': []
  mkdir: []
  upload: [files: File[]]
  download: []
  rename: []
  delete: []
  'update:showHiddenFiles': [value: boolean]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const selectedCount = computed(() => props.selectedItems.length)

function pickFile() {
  fileInput.value?.click()
}

function pickFolder() {
  folderInput.value?.click()
}

function selectHistoryPath(path: string | number | boolean) {
  emit('history-select', String(path))
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

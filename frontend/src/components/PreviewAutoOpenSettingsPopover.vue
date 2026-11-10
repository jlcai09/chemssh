<template>
  <el-popover
    v-model:visible="open"
    trigger="click"
    placement="bottom-end"
    :width="330"
    :z-index="3400"
    popper-class="preview-auto-open-popper"
    @show="syncDraft"
  >
    <template #reference>
      <el-button
        :icon="Setting"
        circle
        size="small"
        :title="t('preview.autoOpen.settings')"
        :aria-label="t('preview.autoOpen.settings')"
      />
    </template>

    <div class="preview-auto-open-panel">
      <div class="preview-auto-open-header">
        <span class="preview-auto-open-title">{{ t('preview.autoOpen.title') }}</span>
        <el-switch v-model="draft.enabled" size="small" @change="emitChange" />
      </div>
      <p class="preview-auto-open-hint">{{ t('preview.autoOpen.hint') }}</p>

      <div class="preview-auto-open-field">
        <span>{{ t('preview.autoOpen.source') }}</span>
        <el-select v-model="draft.source" size="small" :popper-style="SELECT_POPPER_STYLE" @change="handleSourceChange">
          <el-option value="file-manager" :label="t('preview.autoOpen.source.fileManager')" />
          <el-option value="active-terminal" :label="t('preview.autoOpen.source.activeTerminal')" />
          <el-option value="terminal" :label="t('preview.autoOpen.source.terminal')" />
        </el-select>
      </div>

      <div v-if="draft.source === 'terminal'" class="preview-auto-open-field">
        <span>{{ t('preview.autoOpen.terminal') }}</span>
        <el-select
          v-model="draft.terminalTabId"
          size="small"
          :placeholder="t('preview.autoOpen.noTerminal')"
          :disabled="terminals.length === 0 && !missingTerminal"
          :popper-style="SELECT_POPPER_STYLE"
          @change="emitChange"
        >
          <el-option
            v-if="missingTerminal"
            :value="draft.terminalTabId"
            :label="t('preview.autoOpen.terminalMissing')"
            disabled
          />
          <el-option
            v-for="tab in terminals"
            :key="tab.tabId"
            :value="tab.tabId"
            :label="terminalLabel(tab)"
          />
        </el-select>
      </div>

      <div class="preview-auto-open-field">
        <span>{{ t('preview.autoOpen.files') }}</span>
        <div class="preview-auto-open-list">
          <div v-for="(_, index) in draft.filenames" :key="index" class="preview-auto-open-row">
            <span class="preview-auto-open-priority">{{ index + 1 }}</span>
            <el-input
              v-model="draft.filenames[index]"
              size="small"
              :placeholder="t('preview.autoOpen.filePlaceholder')"
              @input="emitChange"
            />
            <span class="preview-auto-open-row-actions">
              <el-tooltip :content="t('preview.autoOpen.moveUp')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500" :z-index="NESTED_POPPER_Z_INDEX">
                <el-button link size="small" :icon="ArrowUp" :disabled="index === 0" @click="moveFilename(index, -1)" />
              </el-tooltip>
              <el-tooltip :content="t('preview.autoOpen.moveDown')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500" :z-index="NESTED_POPPER_Z_INDEX">
                <el-button
                  link
                  size="small"
                  :icon="ArrowDown"
                  :disabled="index === draft.filenames.length - 1"
                  @click="moveFilename(index, 1)"
                />
              </el-tooltip>
              <el-tooltip :content="t('preview.autoOpen.removeFile')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500" :z-index="NESTED_POPPER_Z_INDEX">
                <el-button
                  link
                  size="small"
                  :icon="Delete"
                  :disabled="draft.filenames.length <= 1"
                  @click="removeFilename(index)"
                />
              </el-tooltip>
            </span>
          </div>
        </div>
      </div>

      <el-button
        class="preview-auto-open-add"
        size="small"
        :icon="Plus"
        :disabled="draft.filenames.length >= PREVIEW_AUTO_OPEN_MAX_FILENAMES"
        @click="addFilename"
      >
        {{ t('preview.autoOpen.addFile') }}
      </el-button>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, Delete, Plus, Setting } from '@element-plus/icons-vue'
import {
  PREVIEW_AUTO_OPEN_MAX_FILENAMES,
  type PreviewAutoOpenSettings,
  type PreviewAutoOpenTerminalOption
} from '../api/previewAutoOpen'
import { pathBaseName } from '../api/fileTypes'
import { t } from '../i18n'

const props = defineProps<{
  settings: PreviewAutoOpenSettings
  terminals: PreviewAutoOpenTerminalOption[]
}>()

const emit = defineEmits<{
  change: [settings: PreviewAutoOpenSettings]
}>()

const open = ref(false)
const draft = ref(cloneSettings(props.settings))
// The settings popover is raised above the fullscreen preview (3200); nested
// tooltips and select dropdowns are teleported to body and must sit above it.
const NESTED_POPPER_Z_INDEX = 3500
const SELECT_POPPER_STYLE = { zIndex: NESTED_POPPER_Z_INDEX }

const missingTerminal = computed(() => {
  const tabId = draft.value.terminalTabId
  return Boolean(tabId) && !props.terminals.some(tab => tab.tabId === tabId)
})

watch(
  () => props.settings,
  value => {
    if (!open.value) draft.value = cloneSettings(value)
  }
)

function cloneSettings(value: PreviewAutoOpenSettings): PreviewAutoOpenSettings {
  return { ...value, filenames: [...value.filenames] }
}

function syncDraft() {
  draft.value = cloneSettings(props.settings)
}

function emitChange() {
  emit('change', cloneSettings(draft.value))
}

function terminalLabel(tab: PreviewAutoOpenTerminalOption) {
  const name = tab.title || pathBaseName(tab.cwd) || tab.tabId
  return tab.active ? `${name} · ${t('preview.autoOpen.activeTerminalTag')}` : name
}

function handleSourceChange() {
  if (draft.value.source === 'terminal' && !draft.value.terminalTabId) {
    const preferred = props.terminals.find(tab => tab.active) ?? props.terminals[0]
    draft.value.terminalTabId = preferred?.tabId ?? ''
  }
  emitChange()
}

function addFilename() {
  if (draft.value.filenames.length >= PREVIEW_AUTO_OPEN_MAX_FILENAMES) return
  draft.value.filenames.push('')
  emitChange()
}

function removeFilename(index: number) {
  if (draft.value.filenames.length <= 1) return
  draft.value.filenames.splice(index, 1)
  emitChange()
}

function moveFilename(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= draft.value.filenames.length) return
  const [name] = draft.value.filenames.splice(index, 1)
  draft.value.filenames.splice(target, 0, name)
  emitChange()
}
</script>

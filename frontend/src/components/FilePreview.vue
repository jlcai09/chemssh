<template>
  <div class="file-preview">
    <div class="preview-header">
      <el-segmented
        v-if="structureCandidate && displayPath"
        :model-value="mode"
        :options="modeOptions"
        size="small"
        @update:model-value="handleModeChange"
      />
      <div class="preview-title">
        <span class="eyebrow">{{ previewTypeLabel }}</span>
        <strong>{{ displayName }}</strong>
        <span v-if="structureError" class="preview-error">{{ structureError }}</span>
      </div>
      <div class="preview-actions">
        <el-tooltip v-if="canEditText" :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button :icon="Refresh" circle size="small" @click="refreshText" />
        </el-tooltip>
        <el-tooltip v-if="canEditText" :content="t('preview.edit')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button
            :icon="EditPen"
            circle
            size="small"
            :type="editingEnabled ? 'success' : 'default'"
            @click="enableEditing"
          />
        </el-tooltip>
        <el-tooltip v-if="canEditText" :content="saveTooltip" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button
            :icon="SaveIcon"
            class="preview-save-button"
            :class="saveButtonClass"
            circle
            :type="saveButtonType"
            size="small"
            :aria-disabled="!canSave"
            @click="handleSaveClick"
          />
        </el-tooltip>
        <el-tooltip v-if="canOpenPopout" :content="t('preview.openExternal')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <el-button :icon="FullScreen" circle size="small" @click="popoutOpen = true" />
        </el-tooltip>
      </div>
    </div>

    <div v-if="loading && !showStructurePane && !showTextPane" class="preview-loading">
      <el-skeleton :rows="7" animated />
    </div>

    <Teleport :disabled="!shouldTeleportToPopout" :to="popoutPaneContainer ?? 'body'">
      <MoleculeViewer
        v-if="structurePaneMounted"
        v-show="showStructurePane"
        :class="shouldTeleportToPopout ? 'preview-popout-pane' : 'preview-pane'"
        :ase-preview="aseStructure"
        :active="showStructurePane"
        @refresh="$emit('refresh')"
        @render-start="handleStructureRenderStart"
        @render-complete="handleStructureRenderComplete"
      />

      <div
        v-if="textPaneMounted"
        v-show="showTextPane"
        :class="[shouldTeleportToPopout ? 'preview-popout-pane' : 'preview-pane', 'text-editor-wrap']"
      >
        <MonacoTextEditor
          v-model="draft"
          class="text-editor"
          :path="file?.path"
          :readonly="!editingEnabled"
        />
        <div class="editor-status-badge" :class="editorStatusClass" aria-live="polite">
          {{ editorStatusLabel }}
        </div>
      </div>
    </Teleport>

    <div v-if="showStructureLoadingOverlay" class="structure-loading-overlay" aria-live="polite" aria-busy="true">
      <el-icon class="structure-loading-spinner"><Loading /></el-icon>
      <span>{{ t('common.loading') }}</span>
    </div>

    <div v-if="showStructureErrorWarning" class="preview-structure-warning" role="status">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ t('viewer.vaspOutcarMdWarning') }}</span>
    </div>

    <div v-if="showEmptyState" class="empty-state">
      <el-empty :description="t('preview.empty')" />
    </div>

    <Teleport to="body">
      <div v-if="popoutOpen" class="preview-popout-panel" role="dialog" aria-modal="true" tabindex="-1">
        <div class="preview-popout-toolbar">
          <el-segmented
            v-if="structureCandidate && displayPath"
            :model-value="mode"
            :options="modeOptions"
            size="small"
            @update:model-value="handleModeChange"
          />
          <div class="preview-title">
            <span class="eyebrow">{{ previewTypeLabel }}</span>
            <strong>{{ displayName }}</strong>
            <span v-if="structureError" class="preview-error">{{ structureError }}</span>
          </div>
          <div class="preview-actions">
            <el-tooltip v-if="canEditText" :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button :icon="Refresh" circle size="small" @click="refreshText" />
            </el-tooltip>
            <el-tooltip v-if="canEditText" :content="t('preview.edit')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button
                :icon="EditPen"
                circle
                size="small"
                :type="editingEnabled ? 'success' : 'default'"
                @click="enableEditing"
              />
            </el-tooltip>
            <el-tooltip v-if="canEditText" :content="saveTooltip" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button
                :icon="SaveIcon"
                class="preview-save-button"
                :class="saveButtonClass"
                circle
                :type="saveButtonType"
                size="small"
                :aria-disabled="!canSave"
                @click="handleSaveClick"
              />
            </el-tooltip>
            <el-tooltip :content="t('preview.exitExternal')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button :icon="ScaleToOriginal" circle size="small" @click="popoutOpen = false" />
            </el-tooltip>
          </div>
        </div>

        <div class="preview-popout-content">
          <div v-if="showPopoutLoadingOverlay" class="preview-popout-loading" aria-live="polite" aria-busy="true">
            <el-icon class="structure-loading-spinner"><Loading /></el-icon>
            <span>{{ t('common.loading') }}</span>
          </div>

          <div ref="popoutPaneContainer" class="preview-popout-pane" />

          <div v-if="showPopoutStructureLoadingOverlay" class="structure-loading-overlay" aria-live="polite" aria-busy="true">
            <el-icon class="structure-loading-spinner"><Loading /></el-icon>
            <span>{{ t('common.loading') }}</span>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, defineComponent, h, ref, watch } from 'vue'
import { EditPen, FullScreen, Loading, Refresh, ScaleToOriginal, WarningFilled } from '@element-plus/icons-vue'
import type { FileReadResponse } from '../api/files'
import { t } from '../i18n'
import type { AsePreviewResponse } from '../types/structure'
// Monaco 体积巨大，异步加载以确保其主包与 CSS 不进入首屏，仅在实际打开文本文件预览时才拉取。
const MonacoTextEditor = defineAsyncComponent(() => import('./MonacoTextEditor.vue'))
import MoleculeViewer from './MoleculeViewer.vue'

type PreviewMode = 'structure' | 'text'
type SaveState = 'readonly' | 'saved' | 'unsaved'

const props = defineProps<{
  file?: FileReadResponse | null
  aseStructure?: AsePreviewResponse | null
  mode?: PreviewMode
  loading?: boolean
  structureCandidate?: boolean
  structureError?: string | null
}>()

const emit = defineEmits<{
  refresh: []
  save: [content: string]
  'update:mode': [mode: PreviewMode]
}>()

const SaveIcon = defineComponent({
  name: 'SaveIcon',
  setup() {
    return () =>
      h('svg', { viewBox: '0 0 1024 1024', xmlns: 'http://www.w3.org/2000/svg' }, [
        h('path', {
          fill: 'currentColor',
          d: 'M192 96h574.6L864 193.4V928H192V96zm64 64v704h80V544h352v320h112V220l-60-60h-36v288H320V160h-64zm128 0v224h256V160H384zm16 448v256h224V608H400z'
        })
      ])
  }
})

const draft = ref('')
const editingEnabled = ref(false)
const currentFilePath = ref<string | null>(null)
const structurePaneMounted = ref(false)
const textPaneMounted = ref(false)
const structureRenderPending = ref(false)
const popoutOpen = ref(false)
const popoutPaneContainer = ref<HTMLElement | null>(null)
const shouldTeleportToPopout = ref(false)

watch(
  () => props.file,
  file => {
    const nextPath = file?.path ?? null
    const pathChanged = nextPath !== currentFilePath.value
    currentFilePath.value = nextPath
    draft.value = file?.content ?? ''
    if (pathChanged) editingEnabled.value = false
  },
  { immediate: true }
)

watch(
  () => props.mode,
  () => {
    editingEnabled.value = false
  }
)

const canEditText = computed(() => props.mode === 'text' && Boolean(props.file))
const dirty = computed(() => props.mode === 'text' && Boolean(props.file) && draft.value !== props.file?.content)
const canSave = computed(() => editingEnabled.value && dirty.value)
const showStructurePane = computed(() => props.mode === 'structure' && Boolean(props.aseStructure))
const showTextPane = computed(() => props.mode === 'text' && Boolean(props.file))
const showPopoutStructurePane = computed(() => popoutOpen.value && showStructurePane.value)
const showEmptyState = computed(() => !props.loading && !showStructurePane.value && !showTextPane.value)
const showStructureLoadingOverlay = computed(() => showStructurePane.value && (props.loading || structureRenderPending.value))
const showPopoutStructureLoadingOverlay = computed(() => showPopoutStructurePane.value && (props.loading || structureRenderPending.value))
const showPopoutLoadingOverlay = computed(() => popoutOpen.value && props.loading && !showStructurePane.value && !showTextPane.value)
const showStructureErrorWarning = computed(() => Boolean(props.structureError && isOutcarPath(displayPath.value)))
const canOpenPopout = computed(() =>
  showStructurePane.value ||
  showTextPane.value ||
  (popoutOpen.value && props.loading && Boolean(props.file || props.aseStructure))
)

watch(
  showStructurePane,
  active => {
    if (active) structurePaneMounted.value = true
  },
  { immediate: true }
)

watch(
  showTextPane,
  active => {
    if (active) textPaneMounted.value = true
  },
  { immediate: true }
)

watch(
  [popoutOpen, popoutPaneContainer],
  ([open, container]) => {
    shouldTeleportToPopout.value = Boolean(open && container)
  },
  { immediate: true }
)

watch(
  () => [props.loading, props.mode, props.aseStructure] as const,
  ([loading, mode, structure]) => {
    if (loading && mode === 'structure' && structure) {
      structureRenderPending.value = true
    } else if (mode !== 'structure' || !structure) {
      structureRenderPending.value = false
    }
  }
)

watch(
  canOpenPopout,
  canOpen => {
    if (!canOpen) popoutOpen.value = false
  }
)
const editorStatusClass = computed(() => {
  return `is-${saveState.value}`
})
const editorStatusLabel = computed(() => {
  return saveStateLabel.value
})
const saveState = computed<SaveState>(() => {
  if (!editingEnabled.value) return 'readonly'
  return dirty.value ? 'unsaved' : 'saved'
})
const saveStateLabel = computed(() => {
  if (saveState.value === 'readonly') return t('preview.readonly')
  return saveState.value === 'unsaved' ? t('preview.statusUnsaved') : t('preview.statusSaved')
})
const saveTooltip = computed(() => saveStateLabel.value)
const saveButtonType = computed(() => {
  if (saveState.value === 'saved') return 'success'
  if (saveState.value === 'unsaved') return 'danger'
  return undefined
})
const saveButtonClass = computed(() => `is-${saveState.value}`)

const modeOptions = computed(() => [
  { label: t('preview.type.structure'), value: 'structure' },
  { label: t('preview.type.text'), value: 'text' }
])

const displayName = computed(() => {
  if (props.mode === 'text') return props.file?.name ?? t('file.noFileSelected')
  if (props.mode === 'structure') return props.aseStructure?.name ?? t('file.noFileSelected')
  return props.file?.name ?? props.aseStructure?.name ?? t('file.noFileSelected')
})
const displayPath = computed(() => {
  if (props.mode === 'text') return props.file?.path ?? ''
  if (props.mode === 'structure') return props.aseStructure?.path ?? ''
  return props.file?.path ?? props.aseStructure?.path ?? ''
})

function isOutcarPath(path: string) {
  const name = path.split(/[\\/]/).pop()?.toUpperCase() ?? ''
  return name.includes('OUTCAR')
}

function enableEditing() {
  editingEnabled.value = true
}

function refreshText() {
  editingEnabled.value = false
  emit('refresh')
}

function handleSaveClick() {
  if (!canSave.value) return
  emit('save', draft.value)
}

function handleStructureRenderStart() {
  if (showStructurePane.value) structureRenderPending.value = true
}

function handleStructureRenderComplete() {
  structureRenderPending.value = false
}

function handleModeChange(value: string | number | boolean) {
  if (value === 'structure' || value === 'text') {
    emit('update:mode', value)
  }
}

const previewTypeLabel = computed(() => {
  if (props.mode === 'structure' && props.aseStructure) return t('preview.type.structure')
  if (!props.file) return t('preview.type.preview')
  if (props.mode === 'text') return t('preview.type.text')
  if (props.mode === 'structure' && props.file.preview_type === 'structure') return t('preview.type.structure')
  if (props.file.preview_type === 'directory') return t('preview.type.directory')
  return t('preview.type.file')
})
</script>

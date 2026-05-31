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
        <el-tooltip v-if="canEditText" :content="t('toolbar.refresh')" placement="bottom">
          <el-button :icon="Refresh" circle size="small" @click="refreshText" />
        </el-tooltip>
        <el-tooltip v-if="canEditText" :content="t('preview.edit')" placement="bottom">
          <el-button
            :icon="EditPen"
            circle
            size="small"
            :type="editingEnabled ? 'success' : 'default'"
            @click="enableEditing"
          />
        </el-tooltip>
        <el-tooltip v-if="canEditText" :content="t('preview.save')" placement="bottom">
          <el-button
            :icon="SaveIcon"
            circle
            type="primary"
            size="small"
            :disabled="!editingEnabled || !dirty"
            @click="$emit('save', draft)"
          />
        </el-tooltip>
      </div>
    </div>

    <div v-if="loading" class="empty-state">
      <el-skeleton :rows="7" animated />
    </div>

    <MoleculeViewer
      v-else-if="mode === 'structure' && aseStructure"
      :ase-preview="aseStructure"
      @refresh="$emit('refresh')"
    />

    <div v-else-if="mode === 'text' && file" class="text-editor-wrap">
      <MonacoTextEditor
        v-model="draft"
        class="text-editor"
        :path="file.path"
        :readonly="!editingEnabled"
      />
      <div class="editor-status-badge" :class="editorStatusClass" aria-live="polite">
        {{ editorStatusLabel }}
      </div>
    </div>

    <div v-else class="empty-state">
      <el-empty :description="t('preview.empty')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { EditPen, Refresh } from '@element-plus/icons-vue'
import type { FileReadResponse } from '../api/files'
import { t } from '../i18n'
import type { AsePreviewResponse } from '../types/structure'
import MonacoTextEditor from './MonacoTextEditor.vue'
import MoleculeViewer from './MoleculeViewer.vue'

type PreviewMode = 'structure' | 'text'

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
const editorStatusClass = computed(() => {
  if (!editingEnabled.value) return 'is-readonly'
  return dirty.value ? 'is-unsaved' : 'is-saved'
})
const editorStatusLabel = computed(() => {
  if (!editingEnabled.value) return t('preview.readonly')
  return dirty.value ? t('preview.statusUnsaved') : t('preview.statusSaved')
})

const modeOptions = computed(() => [
  { label: t('preview.type.structure'), value: 'structure' },
  { label: t('preview.type.text'), value: 'text' }
])

const displayName = computed(() => props.aseStructure?.name ?? props.file?.name ?? t('file.noFileSelected'))
const displayPath = computed(() => props.aseStructure?.path ?? props.file?.path ?? '')

function enableEditing() {
  editingEnabled.value = true
}

function refreshText() {
  editingEnabled.value = false
  emit('refresh')
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

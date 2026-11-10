<template>
  <div class="log-viewer" :class="{ 'is-collapsed': collapsed }">
    <div class="panel-header">
      <div class="log-title">
        <span class="eyebrow">tail</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="header-actions">
        <slot name="header-actions" />
        <template v-if="!collapsed">
          <el-input-number
            v-model="lines"
            class="tail-lines-input"
            size="small"
            :min="1"
            :max="100"
            :step="10"
            controls-position="right"
          />
          <el-switch v-model="autoRefresh" size="small" :active-text="t('log.auto')" />
          <el-tooltip :content="t('toolbar.refresh')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
            <el-button :icon="Refresh" circle size="small" :disabled="!path" :loading="loading" @click="refresh" />
          </el-tooltip>
        </template>
        <el-tooltip
          v-if="collapsible"
          :content="collapsed ? t('log.expand') : t('log.collapse')"
          placement="bottom"
          popper-class="chemssh-passive-tooltip"
          :enterable="false"
          :show-after="500"
        >
          <button
            class="log-collapse-toggle"
            type="button"
            :aria-label="collapsed ? t('log.expand') : t('log.collapse')"
            :aria-expanded="!collapsed"
            @click="collapsed = !collapsed"
          >
            <el-icon>
              <CaretTop v-if="collapsed" />
              <CaretBottom v-else />
            </el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
    <pre v-show="!collapsed" ref="contentRef" class="log-content">{{ content || t('log.empty') }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CaretBottom, CaretTop, Refresh } from '@element-plus/icons-vue'
import { tailFile } from '../api/files'
import { t } from '../i18n'

const props = defineProps<{
  path?: string | null
  initialLines?: number
  collapsible?: boolean
}>()

const collapsed = defineModel<boolean>('collapsed', { default: false })

const emit = defineEmits<{
  'lines-change': [lines: number]
}>()

const contentRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const lines = ref(clampLines(props.initialLines ?? 20))
const autoRefresh = ref(false)
const content = ref('')
let timer: number | undefined

const title = computed(() => (props.path ? props.path.split(/[\\/]/).pop() : t('log.title')))

async function scrollToBottom() {
  await nextTick()
  if (contentRef.value) contentRef.value.scrollTop = contentRef.value.scrollHeight
}

async function refresh() {
  if (!props.path) {
    content.value = ''
    return
  }
  loading.value = true
  try {
    const response = await tailFile(props.path, lines.value)
    content.value = response.content
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('log.readFailed'))
  } finally {
    loading.value = false
  }
}

function schedule() {
  if (timer) window.clearInterval(timer)
  if (!autoRefresh.value || !props.path || collapsed.value) return
  timer = window.setInterval(refresh, 5000)
}

function clampLines(value: number) {
  if (!Number.isFinite(value)) return 20
  return Math.min(100, Math.max(1, Math.round(value)))
}

watch(
  () => props.path,
  () => {
    refresh()
    schedule()
  },
  { immediate: true }
)

watch([autoRefresh, lines], () => {
  emit('lines-change', lines.value)
  schedule()
  refresh()
})

watch(
  () => props.initialLines,
  value => {
    if (value === undefined) return
    const next = clampLines(value)
    if (next !== lines.value) lines.value = next
  }
)

watch(content, scrollToBottom)

watch(collapsed, value => {
  if (!value) refresh()
  schedule()
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="log-viewer">
    <div class="panel-header">
      <div class="log-title">
        <span class="eyebrow">tail</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="header-actions">
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
        <el-tooltip :content="t('toolbar.refresh')" placement="bottom">
          <el-button :icon="Refresh" circle size="small" :disabled="!path" :loading="loading" @click="refresh" />
        </el-tooltip>
      </div>
    </div>
    <pre ref="contentRef" class="log-content">{{ content || t('log.empty') }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { tailFile } from '../api/files'
import { t } from '../i18n'

const props = defineProps<{
  path?: string | null
}>()

const contentRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const lines = ref(20)
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
  if (!autoRefresh.value || !props.path) return
  timer = window.setInterval(refresh, 5000)
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
  schedule()
  refresh()
})

watch(content, scrollToBottom)

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="queue-status">
    <div class="panel-header">
      <div>
        <span class="eyebrow">{{ response?.scheduler ?? 'scheduler' }}</span>
        <strong>{{ t('queue.title') }}</strong>
      </div>
      <div class="header-actions">
        <el-input
          v-model="search"
          class="queue-search"
          size="small"
          :placeholder="t('queue.search')"
          :prefix-icon="Search"
          clearable
        />
        <el-select v-model="stateFilter" size="small" class="state-filter">
          <el-option :label="t('queue.all')" value="" />
          <el-option label="RUNNING" value="RUNNING" />
          <el-option label="PENDING" value="PENDING" />
          <el-option label="HELD" value="HELD" />
          <el-option label="FAILED" value="FAILED" />
        </el-select>
        <el-tooltip :content="t('toolbar.refresh')" placement="bottom">
          <el-button :icon="Refresh" circle size="small" :loading="loading" @click="refresh" />
        </el-tooltip>
      </div>
    </div>

    <div class="queue-controls">
      <el-switch v-model="autoRefresh" size="small" :active-text="t('queue.autoRefresh')" />
      <el-switch
        v-if="workspaceRoot"
        v-model="workspaceFilterEnabled"
        size="small"
        :active-text="t('queue.workspaceOnly')"
      />
      <el-select v-model="refreshSeconds" size="small" class="interval-select">
        <el-option :value="5" label="5s" />
        <el-option :value="10" label="10s" />
        <el-option :value="30" label="30s" />
        <el-option :value="60" label="60s" />
      </el-select>
    </div>

    <el-alert
      v-if="response && !response.available"
      class="queue-alert"
      type="warning"
      :closable="false"
      :title="response.message"
    />

    <div class="queue-table-wrap">
      <JobTable
        :jobs="filteredJobs"
        :loading="loading"
        :selected-jobs="selectedJobs"
        @selection-change="handleSelectionChange"
        @context-menu="openQueueContextMenu"
        @open-workdir="openJobWorkdir"
        @cancel="job => confirmQueueAction('cancel', [job])"
        @detail="openDetail"
      />
    </div>

    <el-drawer v-model="detailOpen" size="420px" :title="t('queue.detail')">
      <pre class="detail-pre">{{ detailText }}</pre>
    </el-drawer>

    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="queue-context-menu"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
        role="menu"
        @click.stop
        @contextmenu.prevent
      >
        <button class="context-menu-item" type="button" role="menuitem" @click="confirmQueueAction('hold')">
          <span>{{ actionLabels.hold }}</span>
        </button>
        <button class="context-menu-item" type="button" role="menuitem" @click="confirmQueueAction('release')">
          <span>{{ actionLabels.release }}</span>
        </button>
        <button class="context-menu-item is-danger" type="button" role="menuitem" @click="confirmQueueAction('cancel')">
          <span>{{ actionLabels.cancel }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import {
  getJobDetail,
  listQueue,
  runQueueAction,
  type QueueItem,
  type QueueJobAction,
  type QueueResponse
} from '../api/queue'
import { t } from '../i18n'
import JobTable from './JobTable.vue'

const props = withDefaults(
  defineProps<{
    compact?: boolean
    initialInterval?: number
    workspaceRoot?: string | null
  }>(),
  {
    compact: false,
    initialInterval: 10,
    workspaceRoot: null
  }
)

const emit = defineEmits<{
  'open-workdir': [path: string, job: QueueItem]
}>()

type QueueContextMenuState = {
  visible: boolean
  x: number
  y: number
  jobs: QueueItem[]
}

const response = ref<QueueResponse | null>(null)
const loading = ref(false)
const search = ref('')
const stateFilter = ref('')
const autoRefresh = ref(true)
const workspaceFilterEnabled = ref(true)
const refreshSeconds = ref(props.initialInterval)
const detailOpen = ref(false)
const detailText = ref('')
const selectedJobs = ref<QueueItem[]>([])
const selectedJob = ref<QueueItem | null>(null)
const contextMenu = ref<QueueContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  jobs: []
})
let timer: number | undefined

const actionLabels = computed(() => {
  const scheduler = (response.value?.scheduler ?? '').toLowerCase()
  if (scheduler.includes('pbs')) {
    return { hold: 'qhold', release: 'qrls', cancel: 'qdel' }
  }
  return { hold: 'hold', release: 'release', cancel: 'scancel' }
})

const filteredJobs = computed(() => {
  const query = search.value.trim().toLowerCase()
  const state = stateFilter.value
  return (response.value?.items ?? []).filter(job => {
    const matchesWorkspace =
      !workspaceFilterEnabled.value || !props.workspaceRoot || isPathInsideWorkspace(job.workdir, props.workspaceRoot)
    const matchesQuery =
      !query ||
      [job.job_id, job.name, job.user, job.partition, job.reason, job.workdir].some(value =>
        String(value ?? '').toLowerCase().includes(query)
      )
    const matchesState = !state || job.state.toUpperCase().includes(state)
    return matchesWorkspace && matchesQuery && matchesState
  })
})

async function refresh() {
  loading.value = true
  try {
    response.value = await listQueue()
    syncSelectionWithVisibleJobs()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('queue.refreshFailed'))
  } finally {
    loading.value = false
  }
}

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function normalizePath(path: string) {
  return path.replace(/\\/g, '/').replace(/\/+$/, '')
}

function isWindowsPath(path: string) {
  return /^[A-Za-z]:\//.test(path)
}

function isPathInsideWorkspace(path: string | null | undefined, root: string) {
  if (!path) return false
  const normalizedPath = normalizePath(path)
  const normalizedRoot = normalizePath(root)
  if (!normalizedPath || !normalizedRoot) return false

  const comparePath = isWindowsPath(normalizedPath) ? normalizedPath.toLowerCase() : normalizedPath
  const compareRoot = isWindowsPath(normalizedRoot) ? normalizedRoot.toLowerCase() : normalizedRoot
  return comparePath === compareRoot || comparePath.startsWith(`${compareRoot}/`)
}

function handleSelectionChange(jobs: QueueItem[], primary: QueueItem | null) {
  selectedJobs.value = jobs
  selectedJob.value = primary ?? jobs[jobs.length - 1] ?? null
}

function syncSelectionWithVisibleJobs() {
  if (selectedJobs.value.length === 0) return
  const selectedIds = new Set(selectedJobs.value.map(job => job.job_id))
  const nextSelected = filteredJobs.value.filter(job => selectedIds.has(job.job_id))
  selectedJobs.value = nextSelected
  selectedJob.value =
    (selectedJob.value ? nextSelected.find(job => job.job_id === selectedJob.value?.job_id) : null) ??
    nextSelected[nextSelected.length - 1] ??
    null
}

function openQueueContextMenu(job: QueueItem, event: MouseEvent) {
  event.stopPropagation()
  const selectedIds = new Set(selectedJobs.value.map(item => item.job_id))
  const targets = selectedIds.has(job.job_id) ? selectedJobs.value : [job]
  contextMenu.value = {
    visible: true,
    x: clamp(event.clientX, 8, window.innerWidth - 190 - 8),
    y: clamp(event.clientY, 8, window.innerHeight - 126 - 8),
    jobs: targets
  }
}

function closeContextMenu() {
  if (!contextMenu.value.visible) return
  contextMenu.value = {
    visible: false,
    x: 0,
    y: 0,
    jobs: []
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') closeContextMenu()
}

async function confirmQueueAction(action: QueueJobAction, explicitJobs?: QueueItem[]) {
  const targets = explicitJobs ?? contextMenu.value.jobs
  const safeTargets = targets.length > 0 ? targets : selectedJobs.value
  if (safeTargets.length === 0) return

  closeContextMenu()
  const label = actionLabels.value[action]
  try {
    await ElMessageBox.confirm(
      t('queue.actionConfirm', { action: label, count: safeTargets.length }),
      t('queue.actionConfirmTitle', { action: label }),
      {
        type: action === 'cancel' ? 'warning' : 'info',
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel')
      }
    )
  } catch {
    return
  }

  const results = await Promise.allSettled(safeTargets.map(job => runQueueAction(job.job_id, action)))
  const failed = results.filter(result => result.status === 'rejected')
  if (failed.length === 0) {
    ElMessage.success(t('queue.actionRequested', { action: label, count: safeTargets.length }))
  } else {
    const firstError = failed[0]
    const message =
      firstError.status === 'rejected' && firstError.reason instanceof Error
        ? firstError.reason.message
        : t('queue.actionFailed')
    ElMessage.error(t('queue.actionPartialFailed', { action: label, failed: failed.length, message }))
  }
  await refresh()
}

async function openDetail(job: QueueItem) {
  detailOpen.value = true
  detailText.value = t('common.loading')
  try {
    const detail = await getJobDetail(job.job_id)
    detailText.value = JSON.stringify(detail.detail, null, 2)
  } catch (error) {
    detailText.value = error instanceof Error ? error.message : t('queue.detailReadFailed')
  }
}

function openJobWorkdir(job: QueueItem) {
  if (!job.workdir) {
    ElMessage.warning(t('queue.workdirMissing'))
    return
  }
  emit('open-workdir', job.workdir, job)
}

function schedule() {
  if (timer) window.clearInterval(timer)
  if (!autoRefresh.value) return
  timer = window.setInterval(refresh, refreshSeconds.value * 1000)
}

onMounted(() => {
  refresh()
  schedule()
  window.addEventListener('click', closeContextMenu)
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('resize', closeContextMenu)
  window.addEventListener('scroll', closeContextMenu, true)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
  window.removeEventListener('click', closeContextMenu)
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('scroll', closeContextMenu, true)
})

watch([autoRefresh, refreshSeconds], schedule)
watch(() => filteredJobs.value.map(job => job.job_id).join('\u0000'), syncSelectionWithVisibleJobs)
</script>

<template>
  <div class="job-table" role="grid" aria-multiselectable="true" v-loading="loading" @dragstart.prevent>
    <div ref="scrollRef" class="job-table-scroll" @scroll="handleScroll" @mousedown.left="beginBlankSelect">
      <div class="job-list-header" role="row">
        <span role="columnheader">{{ t('job.id') }}</span>
        <span role="columnheader">{{ t('job.name') }}</span>
        <span role="columnheader">{{ t('job.state') }}</span>
        <span role="columnheader">{{ t('job.partition') }}</span>
        <span role="columnheader">{{ t('job.timeUsed') }}</span>
        <span class="job-cell-right" role="columnheader">{{ t('job.nodes') }}</span>
        <span role="columnheader">{{ t('job.reason') }}</span>
        <span role="columnheader">{{ t('job.actions') }}</span>
      </div>

      <div v-if="jobs.length === 0 && !loading" class="job-empty-state">{{ t('queue.empty') }}</div>

      <div
        v-else
        class="job-virtual-list"
        :class="{ 'is-virtual': shouldVirtualize }"
        :style="virtualListStyle"
      >
        <div
          v-for="{ job, index } in renderedJobs"
          :key="job.job_id"
          :ref="el => setRowRef(el, index)"
          class="job-row"
          :class="{
            'is-selected': selectedJobIdSet.has(job.job_id),
            'is-drag-range': isInDragRange(index),
            'is-focused': focusedIndex === index,
            'is-anchor': anchorIndex === index
          }"
          :style="rowStyle(index)"
          role="row"
          tabindex="0"
          :aria-selected="selectedJobIdSet.has(job.job_id)"
          @focus="focusedIndex = index"
          @mousedown.left="beginSelect(index, $event)"
          @contextmenu.prevent="openContextMenu(index, $event)"
          @mouseenter="extendSelection(index)"
          @dblclick="handleOpenWorkdir(index)"
          @keydown="handleKeydown(index, $event)"
        >
          <span class="job-cell job-id-cell" role="gridcell" :title="job.job_id">{{ job.job_id }}</span>
          <span class="job-cell" role="gridcell" :title="job.name">{{ job.name }}</span>
          <span class="job-cell" role="gridcell">
            <el-tag :type="tagType(job.state)" effect="plain">{{ job.state || 'UNKNOWN' }}</el-tag>
          </span>
          <span class="job-cell" role="gridcell" :title="job.partition">{{ job.partition }}</span>
          <span class="job-cell" role="gridcell">{{ job.time_used }}</span>
          <span class="job-cell job-cell-right" role="gridcell">{{ job.nodes ?? '' }}</span>
          <span class="job-cell" role="gridcell" :title="job.reason || job.workdir || ''">
            {{ job.reason || job.workdir || '' }}
          </span>
          <span class="job-cell job-action-cell" role="gridcell">
            <el-tooltip :content="t('job.detail')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button :icon="InfoFilled" circle size="small" @mousedown.stop @click.stop="$emit('detail', job)" />
            </el-tooltip>
            <el-tooltip :content="t('job.cancel')" placement="bottom" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
              <el-button
                :icon="Close"
                circle
                size="small"
                type="danger"
                @mousedown.stop
                @click.stop="$emit('cancel', job)"
              />
            </el-tooltip>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Close, InfoFilled } from '@element-plus/icons-vue'
import type { QueueItem } from '../api/queue'
import { t } from '../i18n'

const props = withDefaults(
  defineProps<{
    jobs: QueueItem[]
    loading?: boolean
    selectedJobs?: QueueItem[]
  }>(),
  {
    selectedJobs: () => []
  }
)

const emit = defineEmits<{
  cancel: [job: QueueItem]
  detail: [job: QueueItem]
  'selection-change': [jobs: QueueItem[], primary: QueueItem | null]
  'context-menu': [job: QueueItem, event: MouseEvent]
  'open-workdir': [job: QueueItem]
}>()

const ROW_HEIGHT = 40
const HEADER_HEIGHT = 36
const VIRTUALIZE_THRESHOLD = 120
const VIRTUAL_OVERSCAN = 8

const selectedJobIdSet = computed(() => new Set(props.selectedJobs.map(job => job.job_id)))
const scrollRef = ref<HTMLElement | null>(null)
const rowRefs = ref<(HTMLElement | null)[]>([])
const viewportHeight = ref(0)
const scrollTop = ref(0)
const focusedIndex = ref<number | null>(null)
const anchorIndex = ref<number | null>(null)
const dragActive = ref(false)
const dragAnchor = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)
const blankDragActive = ref(false)
const blankDragJobIdSet = ref(new Set<string>())
let blankDragStartX = 0
let blankDragStartY = 0
let blankDragCurrentX = 0
let blankDragCurrentY = 0
let resizeObserver: ResizeObserver | null = null

const shouldVirtualize = computed(() => props.jobs.length > VIRTUALIZE_THRESHOLD)
const visibleStart = computed(() => {
  if (!shouldVirtualize.value) return 0
  return Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT) - VIRTUAL_OVERSCAN)
})
const visibleEnd = computed(() => {
  if (!shouldVirtualize.value) return props.jobs.length
  const visibleCount = Math.ceil(viewportHeight.value / ROW_HEIGHT) + VIRTUAL_OVERSCAN * 2
  return Math.min(props.jobs.length, visibleStart.value + visibleCount)
})
const renderedJobs = computed(() => props.jobs.slice(visibleStart.value, visibleEnd.value).map((job, offset) => ({
  job,
  index: visibleStart.value + offset
})))
const virtualListStyle = computed(() => shouldVirtualize.value ? { height: `${props.jobs.length * ROW_HEIGHT}px` } : undefined)

function setRowRef(el: unknown, index: number) {
  rowRefs.value[index] = el instanceof HTMLElement ? el : null
}

function rowStyle(index: number) {
  return shouldVirtualize.value ? { transform: `translateY(${index * ROW_HEIGHT}px)` } : undefined
}

function updateVirtualViewport() {
  const scroller = scrollRef.value
  if (!scroller) return
  viewportHeight.value = Math.max(0, scroller.clientHeight - HEADER_HEIGHT)
  scrollTop.value = Math.max(0, scroller.scrollTop - HEADER_HEIGHT)
}

function handleScroll() {
  updateVirtualViewport()
}

function scrollIndexIntoView(index: number) {
  const scroller = scrollRef.value
  if (!scroller) return
  const rowTop = HEADER_HEIGHT + index * ROW_HEIGHT
  const rowBottom = rowTop + ROW_HEIGHT
  const visibleTop = scroller.scrollTop + HEADER_HEIGHT
  const visibleBottom = scroller.scrollTop + scroller.clientHeight

  if (rowTop < visibleTop) {
    scroller.scrollTop = Math.max(0, rowTop - HEADER_HEIGHT)
  } else if (rowBottom > visibleBottom) {
    scroller.scrollTop = rowBottom - scroller.clientHeight
  }
  updateVirtualViewport()
}

function isScrollbarEvent(element: HTMLElement, event: MouseEvent) {
  const rect = element.getBoundingClientRect()
  const verticalScrollbar = element.offsetWidth - element.clientWidth
  const horizontalScrollbar = element.offsetHeight - element.clientHeight
  const onVerticalScrollbar = verticalScrollbar > 0 && event.clientX >= rect.right - verticalScrollbar
  const onHorizontalScrollbar = horizontalScrollbar > 0 && event.clientY >= rect.bottom - horizontalScrollbar
  return onVerticalScrollbar || onHorizontalScrollbar
}

function clampIndex(index: number) {
  if (props.jobs.length === 0) return -1
  return Math.min(Math.max(index, 0), props.jobs.length - 1)
}

async function focusRow(index: number) {
  const next = clampIndex(index)
  if (next < 0) return
  focusedIndex.value = next
  if (shouldVirtualize.value) {
    scrollIndexIntoView(next)
  }
  await nextTick()
  const row = rowRefs.value[next]
  row?.focus()
  if (!shouldVirtualize.value) {
    row?.scrollIntoView({ block: 'nearest' })
  }
}

function emitSelection(ids: Set<string>, primary: QueueItem | null) {
  const selected = props.jobs.filter(job => ids.has(job.job_id))
  const safePrimary = primary && ids.has(primary.job_id) ? primary : (selected[selected.length - 1] ?? null)
  emit('selection-change', selected, safePrimary)
}

function selectSingle(index: number) {
  const job = props.jobs[index]
  if (!job) return
  anchorIndex.value = index
  focusedIndex.value = index
  emitSelection(new Set([job.job_id]), job)
}

function toggleSelection(index: number) {
  const job = props.jobs[index]
  if (!job) return
  const next = new Set(selectedJobIdSet.value)
  if (next.has(job.job_id)) next.delete(job.job_id)
  else next.add(job.job_id)
  anchorIndex.value = index
  focusedIndex.value = index
  emitSelection(next, job)
}

function selectRange(start: number, end: number) {
  const next = new Set<string>()
  const from = Math.min(start, end)
  const to = Math.max(start, end)
  for (let index = from; index <= to; index += 1) {
    const job = props.jobs[index]
    if (job) next.add(job.job_id)
  }
  focusedIndex.value = end
  emitSelection(next, props.jobs[end] ?? null)
}

function selectAll() {
  const next = new Set(props.jobs.map(job => job.job_id))
  const primary = focusedIndex.value === null ? props.jobs[0] : props.jobs[focusedIndex.value]
  anchorIndex.value = 0
  emitSelection(next, primary ?? null)
}

function clearSelection() {
  anchorIndex.value = null
  emitSelection(new Set(), null)
}

function beginSelect(index: number, event: MouseEvent) {
  event.stopPropagation()
  event.preventDefault()
  focusRow(index)

  if (event.ctrlKey || event.metaKey) {
    toggleSelection(index)
    return
  }

  if (event.shiftKey) {
    const start = anchorIndex.value ?? focusedIndex.value ?? index
    selectRange(start, index)
    return
  }

  dragActive.value = true
  dragAnchor.value = index
  dragOverIndex.value = index
  selectSingle(index)
}

function beginBlankSelect(event: MouseEvent) {
  const scroller = scrollRef.value
  if (!scroller || isScrollbarEvent(scroller, event)) return
  const target = event.target
  if (target instanceof Element && target.closest('.job-row, .job-list-header')) return

  event.preventDefault()
  dragActive.value = false
  dragAnchor.value = null
  dragOverIndex.value = null
  blankDragActive.value = true
  blankDragStartX = event.clientX
  blankDragStartY = event.clientY
  blankDragCurrentX = event.clientX
  blankDragCurrentY = event.clientY
  updateBlankDragSelection()
  window.addEventListener('mousemove', handleBlankDragMove)
}

function handleBlankDragMove(event: MouseEvent) {
  if (!blankDragActive.value) return
  event.preventDefault()
  blankDragCurrentX = event.clientX
  blankDragCurrentY = event.clientY
  updateBlankDragSelection()
}

function updateBlankDragSelection() {
  const left = Math.min(blankDragStartX, blankDragCurrentX)
  const right = Math.max(blankDragStartX, blankDragCurrentX)
  const top = Math.min(blankDragStartY, blankDragCurrentY)
  const bottom = Math.max(blankDragStartY, blankDragCurrentY)
  const next = new Set<string>()
  const selectedIndices: number[] = []

  if (shouldVirtualize.value) {
    const scroller = scrollRef.value
    if (scroller) {
      const rect = scroller.getBoundingClientRect()
      const intersectsX = rect.right >= left && rect.left <= right
      const rowAreaTop = rect.top + HEADER_HEIGHT
      const intersectsY = rect.bottom >= top && rowAreaTop <= bottom
      if (intersectsX && intersectsY) {
        const contentTop = Math.max(0, scroller.scrollTop + Math.max(top, rowAreaTop) - rect.top - HEADER_HEIGHT)
        const contentBottom = Math.max(0, scroller.scrollTop + Math.min(bottom, rect.bottom) - rect.top - HEADER_HEIGHT)
        const from = clampIndex(Math.floor(contentTop / ROW_HEIGHT))
        const to = clampIndex(Math.floor(contentBottom / ROW_HEIGHT))
        if (from >= 0 && to >= 0) {
          for (let index = Math.min(from, to); index <= Math.max(from, to); index += 1) {
            const job = props.jobs[index]
            if (!job) continue
            next.add(job.job_id)
            selectedIndices.push(index)
          }
        }
      }
    }
  } else {
    rowRefs.value.forEach((row, index) => {
      const job = props.jobs[index]
      if (!row || !job) return
      const rect = row.getBoundingClientRect()
      const intersects = rect.right >= left && rect.left <= right && rect.bottom >= top && rect.top <= bottom
      if (!intersects) return
      next.add(job.job_id)
      selectedIndices.push(index)
    })
  }

  blankDragJobIdSet.value = next
  const primaryIndex = selectedIndices.length === 0
    ? null
    : blankDragCurrentY >= blankDragStartY
      ? selectedIndices[selectedIndices.length - 1]
      : selectedIndices[0]
  anchorIndex.value = selectedIndices[0] ?? null
  focusedIndex.value = primaryIndex
  emitSelection(next, primaryIndex === null ? null : (props.jobs[primaryIndex] ?? null))
}

function extendSelection(index: number) {
  if (!dragActive.value || dragAnchor.value === null) return
  dragOverIndex.value = index
  selectRange(dragAnchor.value, index)
}

function finishSelection() {
  if (blankDragActive.value) {
    window.removeEventListener('mousemove', handleBlankDragMove)
  }
  dragActive.value = false
  dragAnchor.value = null
  dragOverIndex.value = null
  blankDragActive.value = false
  blankDragJobIdSet.value = new Set()
}

function isInDragRange(index: number) {
  const job = props.jobs[index]
  if (job && blankDragJobIdSet.value.has(job.job_id)) return true
  if (!dragActive.value || dragAnchor.value === null || dragOverIndex.value === null) return false
  const from = Math.min(dragAnchor.value, dragOverIndex.value)
  const to = Math.max(dragAnchor.value, dragOverIndex.value)
  return index >= from && index <= to
}

function moveFocus(index: number, event: KeyboardEvent) {
  event.preventDefault()
  const next = clampIndex(index)
  if (next < 0) return
  const current = focusedIndex.value ?? next
  focusRow(next)

  if (event.shiftKey) {
    const start = anchorIndex.value ?? current
    anchorIndex.value = start
    selectRange(start, next)
    return
  }

  if (event.ctrlKey || event.metaKey) return
  selectSingle(next)
}

function handleKeydown(index: number, event: KeyboardEvent) {
  const key = event.key

  if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === 'a') {
    event.preventDefault()
    selectAll()
    return
  }

  if (key === 'ArrowDown') {
    moveFocus(index + 1, event)
  } else if (key === 'ArrowUp') {
    moveFocus(index - 1, event)
  } else if (key === 'Home') {
    moveFocus(0, event)
  } else if (key === 'End') {
    moveFocus(props.jobs.length - 1, event)
  } else if (key === 'PageDown') {
    moveFocus(index + 10, event)
  } else if (key === 'PageUp') {
    moveFocus(index - 10, event)
  } else if (key === ' ') {
    event.preventDefault()
    toggleSelection(index)
  } else if (key === 'Escape') {
    event.preventDefault()
    clearSelection()
  } else if (key === 'Enter') {
    event.preventDefault()
    handleOpenWorkdir(index)
  }
}

function handleOpenWorkdir(index: number) {
  const job = props.jobs[index]
  if (job) emit('open-workdir', job)
}

function openContextMenu(index: number, event: MouseEvent) {
  const job = props.jobs[index]
  if (!job) return
  event.stopPropagation()
  focusedIndex.value = index
  if (!selectedJobIdSet.value.has(job.job_id)) {
    selectSingle(index)
  }
  emit('context-menu', job, event)
}

function tagType(state: string) {
  const normalized = state.toUpperCase()
  if (normalized.includes('RUN')) return 'success'
  if (normalized.includes('PEND') || normalized.includes('QUEUE') || normalized === 'Q') return 'warning'
  if (normalized.includes('FAIL') || normalized.includes('CANCEL') || normalized.includes('EXIT')) return 'danger'
  if (normalized.includes('HELD') || normalized === 'H') return 'info'
  return 'info'
}

function syncFocusedSelection() {
  if (props.selectedJobs.length === 0) {
    anchorIndex.value = null
    return
  }

  const primary = props.selectedJobs[props.selectedJobs.length - 1]
  const index = props.jobs.findIndex(job => job.job_id === primary.job_id)
  if (index >= 0 && !dragActive.value && !blankDragActive.value) {
    focusedIndex.value = index
    anchorIndex.value ??= index
  }
}

watch(
  () => props.selectedJobs.map(job => job.job_id).join('\u0000'),
  syncFocusedSelection,
  { immediate: true }
)

watch(
  () => props.jobs.map(job => job.job_id).join('\u0000'),
  () => {
    rowRefs.value = []
    nextTick(updateVirtualViewport)
    syncFocusedSelection()
  }
)

watch([visibleStart, visibleEnd], () => {
  rowRefs.value = []
})

onMounted(() => {
  window.addEventListener('mouseup', finishSelection)
  nextTick(updateVirtualViewport)
  if (scrollRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateVirtualViewport)
    resizeObserver.observe(scrollRef.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('mouseup', finishSelection)
  window.removeEventListener('mousemove', handleBlankDragMove)
  resizeObserver?.disconnect()
})
</script>

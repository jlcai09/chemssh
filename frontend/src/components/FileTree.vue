<template>
  <div
    ref="treeRef"
    class="file-tree"
    :class="{ 'is-column-resizing': Boolean(activeColumnResize) }"
    :style="columnStyle"
    role="grid"
    aria-multiselectable="true"
  >
    <div class="file-list-header" role="row">
      <span role="columnheader" />
      <span class="file-header-cell" role="columnheader" :aria-sort="sortAria('name')">
        <button
          class="file-sort-button"
          :class="{ 'is-active': sortKey === 'name' }"
          type="button"
          :title="sortTitle('name')"
          @click="toggleSort('name')"
        >
          <span>{{ t('file.name') }}</span>
          <span class="sort-icon-wrap">
            <el-icon v-if="sortKey === 'name'">
              <CaretTop v-if="sortDirection === 'asc'" />
              <CaretBottom v-else />
            </el-icon>
          </span>
        </button>
      </span>
      <button
        class="file-column-resizer file-column-resizer-name-size"
        type="button"
        role="separator"
        :aria-label="t('resize.fileColumnNameSize')"
        tabindex="0"
        @pointerdown="startColumnResize('name-size', $event)"
        @dblclick="resetColumnWidths"
      />
      <span class="file-header-cell file-header-size" role="columnheader" :aria-sort="sortAria('size')">
        <button
          class="file-sort-button is-size"
          :class="{ 'is-active': sortKey === 'size' }"
          type="button"
          :title="sortTitle('size')"
          @click="toggleSort('size')"
        >
          <span>{{ t('file.size') }}</span>
          <span class="sort-icon-wrap">
            <el-icon v-if="sortKey === 'size'">
              <CaretTop v-if="sortDirection === 'asc'" />
              <CaretBottom v-else />
            </el-icon>
          </span>
        </button>
      </span>
      <button
        class="file-column-resizer file-column-resizer-size-time"
        type="button"
        role="separator"
        :aria-label="t('resize.fileColumnSizeTime')"
        tabindex="0"
        @pointerdown="startColumnResize('size-time', $event)"
        @dblclick="resetColumnWidths"
      />
      <span class="file-header-cell" role="columnheader" :aria-sort="sortAria('mtime')">
        <button
          class="file-sort-button"
          :class="{ 'is-active': sortKey === 'mtime' }"
          type="button"
          :title="sortTitle('mtime')"
          @click="toggleSort('mtime')"
        >
          <span>{{ t('file.modified') }}</span>
          <span class="sort-icon-wrap">
            <el-icon v-if="sortKey === 'mtime'">
              <CaretTop v-if="sortDirection === 'asc'" />
              <CaretBottom v-else />
            </el-icon>
          </span>
        </button>
      </span>
    </div>
    <div ref="bodyRef" class="file-list-body" role="rowgroup" @mousedown.left="beginBlankSelect">
      <div
        v-for="(item, index) in sortedItems"
        :key="item.path"
        :ref="el => setRowRef(el, index)"
        class="file-row"
        :class="{
          'is-directory': item.type === 'directory',
          'is-selected': selectedPathSet.has(item.path),
          'is-drag-range': isInDragRange(index),
          'is-drag-export': exportDragPathSet.has(item.path),
          'is-focused': focusedIndex === index,
          'is-anchor': anchorIndex === index
        }"
        role="row"
        tabindex="0"
        draggable="true"
        :aria-selected="selectedPathSet.has(item.path)"
        @focus="focusedIndex = index"
        @mousedown.left="beginSelect(index, $event)"
        @contextmenu.prevent="openContextMenu(index, $event)"
        @mouseenter="extendSelection(index)"
        @dragstart="handleFileDragStart(index, $event)"
        @dragend="finishFileDrag"
        @dblclick="handleOpen(index)"
        @keydown="handleKeydown(index, $event)"
      >
        <span class="file-cell file-icon-cell" role="gridcell">
          <el-icon class="file-kind-icon">
            <Folder v-if="item.type === 'directory'" />
            <View v-else-if="isPreviewableItem(item)" />
            <Document v-else />
          </el-icon>
        </span>
        <span class="file-cell file-name-cell" role="gridcell" :title="item.name">{{ item.name }}</span>
        <span class="file-column-divider file-column-divider-name-size" aria-hidden="true" />
        <span class="file-cell file-size-cell" role="gridcell">{{ formatSize(item.size) }}</span>
        <span class="file-column-divider file-column-divider-size-time" aria-hidden="true" />
        <span class="file-cell file-time-cell" role="gridcell">{{ formatDate(item.mtime) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CaretBottom, CaretTop, Document, Folder, View } from '@element-plus/icons-vue'
import { writeChemwebFileDrag } from '../api/fileDrag'
import { hasActivePreviewProvider, type FilePreviewProvider } from '../api/filePreviewProviders'
import type { FileItem } from '../api/files'
import { locale, t } from '../i18n'

const props = withDefaults(
  defineProps<{
    items: FileItem[]
    selectedItems?: FileItem[]
    previewProviders?: FilePreviewProvider[]
  }>(),
  {
    selectedItems: () => [],
    previewProviders: () => []
  }
)

const emit = defineEmits<{
  'selection-change': [items: FileItem[], primary: FileItem | null]
  'context-menu': [item: FileItem, event: MouseEvent]
  open: [item: FileItem]
}>()

type SortKey = 'name' | 'size' | 'mtime'
type SortDirection = 'asc' | 'desc'
type ColumnResizeTarget = 'name-size' | 'size-time'

const sortKey = ref<SortKey>('name')
const sortDirection = ref<SortDirection>('asc')
const selectedPathSet = computed(() => new Set(props.selectedItems.map(item => item.path)))
const treeRef = ref<HTMLElement | null>(null)
const bodyRef = ref<HTMLElement | null>(null)
const rowRefs = ref<(HTMLElement | null)[]>([])
const focusedIndex = ref<number | null>(null)
const anchorIndex = ref<number | null>(null)
const dragActive = ref(false)
const dragAnchor = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)
const blankDragActive = ref(false)
const blankDragPathSet = ref(new Set<string>())
const exportDragPathSet = ref(new Set<string>())
const exportDragArmed = ref(false)
const exportDragActive = ref(false)
let blankDragStartX = 0
let blankDragStartY = 0
let blankDragCurrentX = 0
let blankDragCurrentY = 0
let longPressTimer: number | null = null
let pressIndex: number | null = null
let pressStartX = 0
let pressStartY = 0
let columnResizeStartX = 0
let columnResizeStartSize = 0
let columnResizeStartTime = 0
let previousBodyCursor = ''
let previousBodyUserSelect = ''

const LONG_PRESS_MS = 430
const SELECT_DRAG_THRESHOLD = 4
const DEFAULT_SIZE_COLUMN_WIDTH = 88
const DEFAULT_TIME_COLUMN_WIDTH = 152
const MIN_NAME_COLUMN_WIDTH = 160
const MIN_SIZE_COLUMN_WIDTH = 64
const MAX_SIZE_COLUMN_WIDTH = 168
const MIN_TIME_COLUMN_WIDTH = 112
const MAX_TIME_COLUMN_WIDTH = 260
const FILE_ICON_COLUMN_WIDTH = 34
const FILE_COLUMN_RESIZER_WIDTH = 10

const activeColumnResize = ref<ColumnResizeTarget | null>(null)
const sizeColumnWidth = ref(DEFAULT_SIZE_COLUMN_WIDTH)
const timeColumnWidth = ref(DEFAULT_TIME_COLUMN_WIDTH)

const columnStyle = computed<Record<string, string>>(() => ({
  '--file-size-col': `${sizeColumnWidth.value}px`,
  '--file-time-col': `${timeColumnWidth.value}px`
}))

const sortedItems = computed(() => {
  return [...props.items].sort((a, b) => {
    const typeCompare = typeRank(a) - typeRank(b)
    if (typeCompare !== 0) return typeCompare

    const result = compareItems(a, b)
    return sortDirection.value === 'asc' ? result : -result
  })
})

function typeRank(item: FileItem) {
  return item.type === 'directory' ? 0 : 1
}

function isPreviewableItem(item: FileItem) {
  return item.preview_type === 'structure' || hasActivePreviewProvider(item, props.previewProviders)
}

function nameCompare(a: FileItem, b: FileItem) {
  return a.name.localeCompare(b.name, locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    numeric: true,
    sensitivity: 'base'
  })
}

function timestamp(value: string) {
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? 0 : time
}

function compareItems(a: FileItem, b: FileItem) {
  let result = 0
  if (sortKey.value === 'name') {
    result = nameCompare(a, b)
  } else if (sortKey.value === 'size') {
    result = (a.size ?? -1) - (b.size ?? -1)
  } else {
    result = timestamp(a.mtime) - timestamp(b.mtime)
  }

  return result === 0 ? nameCompare(a, b) : result
}

function sortFieldLabel(key: SortKey) {
  if (key === 'name') return t('file.name')
  if (key === 'size') return t('file.size')
  return t('file.modified')
}

function sortAria(key: SortKey) {
  if (sortKey.value !== key) return 'none'
  return sortDirection.value === 'asc' ? 'ascending' : 'descending'
}

function sortTitle(key: SortKey) {
  const direction = sortDirection.value === 'asc' ? t('file.sortAscending') : t('file.sortDescending')
  return sortKey.value === key ? `${t('file.sortBy', { field: sortFieldLabel(key) })}: ${direction}` : t('file.sortBy', { field: sortFieldLabel(key) })
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDirection.value = 'asc'
  }
}

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function maxSizeColumnWidth() {
  const width = treeRef.value?.getBoundingClientRect().width ?? 0
  if (width <= 0) return MAX_SIZE_COLUMN_WIDTH
  const reserved = FILE_ICON_COLUMN_WIDTH + FILE_COLUMN_RESIZER_WIDTH * 2 + MIN_NAME_COLUMN_WIDTH + timeColumnWidth.value
  return Math.min(MAX_SIZE_COLUMN_WIDTH, Math.max(MIN_SIZE_COLUMN_WIDTH, width - reserved))
}

function startColumnResize(target: ColumnResizeTarget, event: PointerEvent) {
  event.preventDefault()
  event.stopPropagation()
  activeColumnResize.value = target
  columnResizeStartX = event.clientX
  columnResizeStartSize = sizeColumnWidth.value
  columnResizeStartTime = timeColumnWidth.value
  previousBodyCursor = document.body.style.cursor
  previousBodyUserSelect = document.body.style.userSelect
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleColumnResizeMove)
  window.addEventListener('pointerup', stopColumnResize, { once: true })
  window.addEventListener('pointercancel', stopColumnResize, { once: true })
}

function handleColumnResizeMove(event: PointerEvent) {
  if (!activeColumnResize.value) return
  const delta = event.clientX - columnResizeStartX

  if (activeColumnResize.value === 'name-size') {
    const maxSize = maxSizeColumnWidth()
    sizeColumnWidth.value = clamp(columnResizeStartSize - delta, MIN_SIZE_COLUMN_WIDTH, maxSize)
    return
  }

  const combinedWidth = columnResizeStartSize + columnResizeStartTime
  const minSize = Math.max(MIN_SIZE_COLUMN_WIDTH, combinedWidth - MAX_TIME_COLUMN_WIDTH)
  const maxSize = Math.min(MAX_SIZE_COLUMN_WIDTH, combinedWidth - MIN_TIME_COLUMN_WIDTH, maxSizeColumnWidth())
  const nextSize = clamp(columnResizeStartSize + delta, minSize, maxSize)
  sizeColumnWidth.value = nextSize
  timeColumnWidth.value = clamp(combinedWidth - nextSize, MIN_TIME_COLUMN_WIDTH, MAX_TIME_COLUMN_WIDTH)
}

function stopColumnResize() {
  if (!activeColumnResize.value) return
  activeColumnResize.value = null
  document.body.style.cursor = previousBodyCursor
  document.body.style.userSelect = previousBodyUserSelect
  window.removeEventListener('pointermove', handleColumnResizeMove)
  window.removeEventListener('pointerup', stopColumnResize)
  window.removeEventListener('pointercancel', stopColumnResize)
}

function resetColumnWidths() {
  sizeColumnWidth.value = DEFAULT_SIZE_COLUMN_WIDTH
  timeColumnWidth.value = DEFAULT_TIME_COLUMN_WIDTH
}

function setRowRef(el: unknown, index: number) {
  rowRefs.value[index] = el instanceof HTMLElement ? el : null
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
  if (sortedItems.value.length === 0) return -1
  return Math.min(Math.max(index, 0), sortedItems.value.length - 1)
}

async function focusRow(index: number) {
  const next = clampIndex(index)
  if (next < 0) return
  focusedIndex.value = next
  await nextTick()
  const row = rowRefs.value[next]
  row?.focus()
  row?.scrollIntoView({ block: 'nearest' })
}

function emitSelection(paths: Set<string>, primary: FileItem | null) {
  const selected = sortedItems.value.filter(item => paths.has(item.path))
  const safePrimary = primary && paths.has(primary.path) ? primary : (selected[selected.length - 1] ?? null)
  emit('selection-change', selected, safePrimary)
}

function selectSingle(index: number) {
  const item = sortedItems.value[index]
  if (!item) return
  anchorIndex.value = index
  focusedIndex.value = index
  emitSelection(new Set([item.path]), item)
}

function toggleSelection(index: number) {
  const item = sortedItems.value[index]
  if (!item) return
  const next = new Set(selectedPathSet.value)
  if (next.has(item.path)) next.delete(item.path)
  else next.add(item.path)
  anchorIndex.value = index
  focusedIndex.value = index
  emitSelection(next, item)
}

function selectRange(start: number, end: number) {
  const next = new Set<string>()
  const from = Math.min(start, end)
  const to = Math.max(start, end)
  for (let index = from; index <= to; index += 1) {
    const item = sortedItems.value[index]
    if (item) next.add(item.path)
  }
  focusedIndex.value = end
  emitSelection(next, sortedItems.value[end] ?? null)
}

function selectAll() {
  const next = new Set(sortedItems.value.map(item => item.path))
  const primary = focusedIndex.value === null ? sortedItems.value[0] : sortedItems.value[focusedIndex.value]
  anchorIndex.value = 0
  emitSelection(next, primary ?? null)
}

function clearSelection() {
  anchorIndex.value = null
  emitSelection(new Set(), null)
}

function beginSelect(index: number, event: MouseEvent) {
  event.stopPropagation()
  focusRow(index)
  finishFileDrag()

  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    toggleSelection(index)
    return
  }

  if (event.shiftKey) {
    event.preventDefault()
    const start = anchorIndex.value ?? focusedIndex.value ?? index
    selectRange(start, index)
    return
  }

  const item = sortedItems.value[index]
  if (!item) return

  if (selectedPathSet.value.has(item.path)) {
    anchorIndex.value = index
    focusedIndex.value = index
    emitSelection(new Set(selectedPathSet.value), item)
  } else {
    selectSingle(index)
  }

  startLongPress(index, event)
}

function startLongPress(index: number, event: MouseEvent) {
  cancelLongPress()
  pressIndex = index
  pressStartX = event.clientX
  pressStartY = event.clientY
  longPressTimer = window.setTimeout(() => armFileDrag(index), LONG_PRESS_MS)
  window.addEventListener('mousemove', handlePressMove)
}

function cancelLongPress() {
  if (longPressTimer !== null) {
    window.clearTimeout(longPressTimer)
    longPressTimer = null
  }
}

function resetPressState() {
  cancelLongPress()
  pressIndex = null
  window.removeEventListener('mousemove', handlePressMove)
}

function handlePressMove(event: MouseEvent) {
  if (pressIndex === null || exportDragArmed.value) return
  if (Math.abs(event.clientX - pressStartX) < SELECT_DRAG_THRESHOLD && Math.abs(event.clientY - pressStartY) < SELECT_DRAG_THRESHOLD) return
  cancelLongPress()
  dragActive.value = true
  dragAnchor.value = pressIndex
  dragOverIndex.value = pressIndex
}

function armFileDrag(index: number) {
  const items = dragItemsForIndex(index)
  exportDragPathSet.value = new Set(items.map(item => item.path))
  exportDragArmed.value = items.length > 0
  dragActive.value = false
  dragAnchor.value = null
  dragOverIndex.value = null
}

function dragItemsForIndex(index: number) {
  const item = sortedItems.value[index]
  if (!item) return []
  if (selectedPathSet.value.has(item.path) && props.selectedItems.length > 0) {
    return sortedItems.value.filter(candidate => selectedPathSet.value.has(candidate.path))
  }
  return [item]
}

function beginBlankSelect(event: MouseEvent) {
  const body = bodyRef.value
  if (!body || isScrollbarEvent(body, event)) return
  const target = event.target
  if (target instanceof Element && target.closest('.file-row')) return

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

  rowRefs.value.forEach((row, index) => {
    const item = sortedItems.value[index]
    if (!row || !item) return
    const rect = row.getBoundingClientRect()
    const intersects = rect.right >= left && rect.left <= right && rect.bottom >= top && rect.top <= bottom
    if (!intersects) return
    next.add(item.path)
    selectedIndices.push(index)
  })

  blankDragPathSet.value = next
  const primaryIndex = selectedIndices.length === 0
    ? null
    : blankDragCurrentY >= blankDragStartY
      ? selectedIndices[selectedIndices.length - 1]
      : selectedIndices[0]
  anchorIndex.value = selectedIndices[0] ?? null
  focusedIndex.value = primaryIndex
  emitSelection(next, primaryIndex === null ? null : (sortedItems.value[primaryIndex] ?? null))
}

function extendSelection(index: number) {
  if (pressIndex !== null && !exportDragArmed.value && !dragActive.value && index !== pressIndex) {
    cancelLongPress()
    dragActive.value = true
    dragAnchor.value = pressIndex
    dragOverIndex.value = pressIndex
  }
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
  blankDragPathSet.value = new Set()
  if (!exportDragActive.value) finishFileDrag()
  resetPressState()
}

function handleFileDragStart(index: number, event: DragEvent) {
  const item = sortedItems.value[index]
  if (!item || !exportDragArmed.value || !exportDragPathSet.value.has(item.path) || !event.dataTransfer) {
    event.preventDefault()
    finishFileDrag()
    return
  }

  const items = dragItemsForIndex(index)
  if (items.length === 0) {
    event.preventDefault()
    finishFileDrag()
    return
  }

  exportDragActive.value = true
  resetPressState()
  writeChemwebFileDrag(event.dataTransfer, items)
  setDragImage(event, items)
}

function setDragImage(event: DragEvent, items: FileItem[]) {
  if (!event.dataTransfer) return
  const image = document.createElement('div')
  image.className = 'file-drag-image'
  image.textContent = items.length === 1 ? items[0].name : `${items.length} files`
  document.body.appendChild(image)
  event.dataTransfer.setDragImage(image, 12, 12)
  window.setTimeout(() => image.remove(), 0)
}

function finishFileDrag() {
  cancelLongPress()
  exportDragActive.value = false
  exportDragArmed.value = false
  exportDragPathSet.value = new Set()
}

function isInDragRange(index: number) {
  const item = sortedItems.value[index]
  if (item && blankDragPathSet.value.has(item.path)) return true
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
    moveFocus(sortedItems.value.length - 1, event)
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
    handleOpen(index)
  }
}

function handleOpen(index: number) {
  const item = sortedItems.value[index]
  if (item) emit('open', item)
}

function openContextMenu(index: number, event: MouseEvent) {
  const item = sortedItems.value[index]
  if (!item) return
  event.stopPropagation()
  focusedIndex.value = index
  if (!selectedPathSet.value.has(item.path)) {
    selectSingle(index)
  }
  emit('context-menu', item, event)
}

function formatSize(value: number | null) {
  if (value === null || value === undefined) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value === 'zh' ? 'zh-CN' : 'en-US')
}

function syncFocusedSelection() {
  if (props.selectedItems.length === 0) {
    anchorIndex.value = null
    return
  }

  const primary = props.selectedItems[props.selectedItems.length - 1]
  const index = sortedItems.value.findIndex(item => item.path === primary.path)
  if (index >= 0 && !dragActive.value && !blankDragActive.value) {
    focusedIndex.value = index
    anchorIndex.value ??= index
  }
}

watch(
  () => props.selectedItems.map(item => item.path).join('\u0000'),
  syncFocusedSelection,
  { immediate: true }
)

watch(
  sortedItems,
  () => {
    rowRefs.value = []
    syncFocusedSelection()
  }
)

onMounted(() => {
  window.addEventListener('mouseup', finishSelection)
})

onBeforeUnmount(() => {
  stopColumnResize()
  window.removeEventListener('mouseup', finishSelection)
  window.removeEventListener('mousemove', handleBlankDragMove)
  window.removeEventListener('mousemove', handlePressMove)
  cancelLongPress()
})
</script>

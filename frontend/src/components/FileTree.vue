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
    <div ref="bodyRef" class="file-list-body" role="rowgroup" @scroll="handleBodyScroll" @mousedown.left="beginBlankSelect">
      <div
        v-if="parentItem"
        class="file-row file-parent-row is-directory"
        :class="{ 'is-move-drop-target': moveDropTargetPath === parentItem.path }"
        role="row"
        tabindex="0"
        draggable="false"
        aria-selected="false"
        @mousedown.left.stop
        @dragenter="handleMoveDragOverItem(parentItem, $event)"
        @dragover="handleMoveDragOverItem(parentItem, $event)"
        @dragleave="handleMoveDragLeaveItem(parentItem, $event)"
        @drop="handleMoveDropItem(parentItem, $event)"
        @dblclick="emit('open', parentItem)"
        @keydown.enter.prevent="emit('open', parentItem)"
      >
        <span class="file-cell file-icon-cell" role="gridcell">
          <img
            v-if="systemIconUrl(parentItem)"
            class="file-system-icon"
            :src="systemIconUrl(parentItem) ?? undefined"
            alt=""
            aria-hidden="true"
            @error="handleSystemIconError(parentItem)"
          />
          <el-icon v-else class="file-kind-icon">
            <Folder />
          </el-icon>
        </span>
        <span class="file-cell file-name-cell" role="gridcell" title="..">..</span>
        <span class="file-column-divider file-column-divider-name-size" aria-hidden="true" />
        <span class="file-cell file-size-cell" role="gridcell" />
        <span class="file-column-divider file-column-divider-size-time" aria-hidden="true" />
        <span class="file-cell file-time-cell" role="gridcell" />
      </div>
      <div class="file-list-virtual-spacer" :style="{ height: `${topSpacerHeight}px` }" aria-hidden="true" />
      <div
        v-for="{ item, index } in virtualRows"
        :key="item.path"
        :ref="el => setRowRef(el, index)"
        class="file-row"
        :class="{
          'is-directory': item.type === 'directory',
          'is-selected': selectedPathSet.has(item.path),
          'is-drag-range': isInDragRange(index),
          'is-drag-export': exportDragPathSet.has(item.path),
          'is-move-drop-target': moveDropTargetPath === item.path,
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
        @dragenter="handleMoveDragOver(index, $event)"
        @dragover="handleMoveDragOver(index, $event)"
        @dragleave="handleMoveDragLeave(index, $event)"
        @drop="handleMoveDrop(index, $event)"
        @dragend="finishFileDrag"
        @dblclick="handleOpen(index)"
        @keydown="handleKeydown(index, $event)"
      >
        <span class="file-cell file-icon-cell" role="gridcell">
          <img
            v-if="systemIconUrl(item)"
            class="file-system-icon"
            :src="systemIconUrl(item) ?? undefined"
            alt=""
            aria-hidden="true"
            @error="handleSystemIconError(item)"
          />
          <el-icon v-else class="file-kind-icon">
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
      <div class="file-list-virtual-spacer" :style="{ height: `${bottomSpacerHeight}px` }" aria-hidden="true" />
    </div>
    <div
      v-if="scrollState.showVertical"
      class="file-floating-scrollbar is-vertical"
      aria-hidden="true"
      @pointerdown="handleScrollbarTrackPointerDown('vertical', $event)"
    >
      <div
        class="file-floating-scrollbar-thumb"
        :style="{ height: `${scrollState.verticalThumbSize}px`, transform: `translateY(${scrollState.verticalThumbOffset}px)` }"
        @pointerdown.stop="startScrollbarThumbDrag('vertical', $event)"
      />
    </div>
    <div
      v-if="scrollState.showHorizontal"
      class="file-floating-scrollbar is-horizontal"
      aria-hidden="true"
      @pointerdown="handleScrollbarTrackPointerDown('horizontal', $event)"
    >
      <div
        class="file-floating-scrollbar-thumb"
        :style="{ width: `${scrollState.horizontalThumbSize}px`, transform: `translateX(${scrollState.horizontalThumbOffset}px)` }"
        @pointerdown.stop="startScrollbarThumbDrag('horizontal', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CaretBottom, CaretTop, Document, Folder, View } from '@element-plus/icons-vue'
import {
  clearActiveChemSSHFileDragPayload,
  getActiveChemSSHFileDragPayload,
  hasChemSSHFileDrag,
  readChemSSHFileDrag,
  writeChemSSHFileDrag,
  type ChemSSHFileDragPayload
} from '../api/fileDrag'
import { hasActivePreviewProvider, type FilePreviewProvider } from '../api/filePreviewProviders'
import type { FileItem } from '../api/files'
import { launcherBridgeIconFailureKey } from '../api/launcherBridge'
import { locale, t } from '../i18n'

const props = withDefaults(
  defineProps<{
    items: FileItem[]
    parentPath?: string | null
    selectedItems?: FileItem[]
    previewProviders?: FilePreviewProvider[]
    systemIconProvider?: {
      enabled: boolean
      iconUrl: (item: FileItem) => string | null
    }
  }>(),
  {
    selectedItems: () => [],
    previewProviders: () => [],
    systemIconProvider: undefined
  }
)

const emit = defineEmits<{
  'selection-change': [items: FileItem[], primary: FileItem | null]
  'context-menu': [item: FileItem, event: MouseEvent]
  'move-items': [items: FileItem[], targetDirectory: FileItem]
  open: [item: FileItem]
}>()

type SortKey = 'name' | 'size' | 'mtime'
type SortDirection = 'asc' | 'desc'
type ColumnResizeTarget = 'name-size' | 'size-time'

const sortKey = ref<SortKey>('name')
const sortDirection = ref<SortDirection>('asc')
const selectedPathSet = computed(() => new Set(props.selectedItems.map(item => item.path)))
const failedSystemIconKeys = ref(new Set<string>())
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
const moveDropTargetPath = ref<string | null>(null)
const bodyScrollTop = ref(0)
const bodyViewportHeight = ref(0)
const scrollState = ref({
  showVertical: false,
  showHorizontal: false,
  verticalThumbSize: 28,
  verticalThumbOffset: 0,
  horizontalThumbSize: 28,
  horizontalThumbOffset: 0
})
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
let scrollResizeObserver: ResizeObserver | null = null
let activeScrollbarDrag: {
  axis: 'vertical' | 'horizontal'
  pointerId: number
  startClient: number
  startScroll: number
  maxScroll: number
  maxThumbOffset: number
} | null = null

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
const FLOATING_SCROLLBAR_MIN_THUMB = 28
const FILE_ROW_SLOT_HEIGHT = 40
const FILE_BODY_VERTICAL_PADDING = 4
const VIRTUAL_ROW_OVERSCAN = 8

const activeColumnResize = ref<ColumnResizeTarget | null>(null)
const sizeColumnWidth = ref(DEFAULT_SIZE_COLUMN_WIDTH)
const timeColumnWidth = ref(DEFAULT_TIME_COLUMN_WIDTH)

const columnStyle = computed<Record<string, string>>(() => ({
  '--file-size-col': `${sizeColumnWidth.value}px`,
  '--file-time-col': `${timeColumnWidth.value}px`
}))

const nameCollator = computed(() => new Intl.Collator(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
  numeric: true,
  sensitivity: 'base'
}))

const sortedItems = computed(() => {
  return [...props.items].sort((a, b) => {
    const typeCompare = typeRank(a) - typeRank(b)
    if (typeCompare !== 0) return typeCompare

    const result = compareItems(a, b)
    return sortDirection.value === 'asc' ? result : -result
  })
})

const parentItem = computed<FileItem | null>(() => {
  if (!props.parentPath) return null
  return {
    name: '..',
    path: props.parentPath,
    type: 'directory',
    size: null,
    mtime: '',
    extension: '',
    preview_type: 'directory',
    format: null
  }
})

const parentSlotHeight = computed(() => parentItem.value ? FILE_ROW_SLOT_HEIGHT : 0)

const virtualRange = computed(() => {
  const count = sortedItems.value.length
  if (count === 0) return { start: 0, end: 0 }

  const viewportHeight = bodyViewportHeight.value || 0
  const itemScrollTop = Math.max(0, bodyScrollTop.value - parentSlotHeight.value)
  const visibleSlots = Math.ceil(viewportHeight / FILE_ROW_SLOT_HEIGHT)
  const firstVisible = clamp(Math.floor(itemScrollTop / FILE_ROW_SLOT_HEIGHT), 0, Math.max(0, count - 1))
  const lastVisible = Math.min(count, firstVisible + visibleSlots)

  return {
    start: clamp(firstVisible - VIRTUAL_ROW_OVERSCAN, 0, count),
    end: clamp(lastVisible + VIRTUAL_ROW_OVERSCAN, 0, count)
  }
})

const virtualRows = computed(() => {
  const { start, end } = virtualRange.value
  return sortedItems.value.slice(start, end).map((item, offset) => ({
    item,
    index: start + offset
  }))
})

const topSpacerHeight = computed(() => virtualRange.value.start * FILE_ROW_SLOT_HEIGHT)
const bottomSpacerHeight = computed(() => Math.max(0, (sortedItems.value.length - virtualRange.value.end) * FILE_ROW_SLOT_HEIGHT))

function typeRank(item: FileItem) {
  return item.type === 'directory' ? 0 : 1
}

function isPreviewableItem(item: FileItem) {
  return item.preview_type === 'structure' || hasActivePreviewProvider(item, props.previewProviders)
}

function systemIconUrl(item: FileItem | null) {
  if (!item || !props.systemIconProvider?.enabled) return null
  if (failedSystemIconKeys.value.has(launcherBridgeIconFailureKey(item))) return null
  return props.systemIconProvider.iconUrl(item)
}

function handleSystemIconError(item: FileItem) {
  const next = new Set(failedSystemIconKeys.value)
  next.add(launcherBridgeIconFailureKey(item))
  failedSystemIconKeys.value = next
}

function nameCompare(a: FileItem, b: FileItem) {
  return nameCollator.value.compare(a.name, b.name)
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

function updateVirtualMetrics() {
  const body = bodyRef.value
  if (!body) return
  bodyScrollTop.value = body.scrollTop
  bodyViewportHeight.value = body.clientHeight
  updateScrollbars()
}

function handleBodyScroll() {
  updateVirtualMetrics()
}

function updateScrollbars() {
  const body = bodyRef.value
  if (!body) return

  const showVertical = body.scrollHeight > body.clientHeight + 1
  const showHorizontal = body.scrollWidth > body.clientWidth + 1
  const verticalTrack = Math.max(0, body.clientHeight - (showHorizontal ? 12 : 0))
  const horizontalTrack = Math.max(0, body.clientWidth - (showVertical ? 12 : 0))
  const maxScrollTop = Math.max(0, body.scrollHeight - body.clientHeight)
  const maxScrollLeft = Math.max(0, body.scrollWidth - body.clientWidth)
  const verticalThumbSize = showVertical
    ? clamp((body.clientHeight / body.scrollHeight) * verticalTrack, FLOATING_SCROLLBAR_MIN_THUMB, verticalTrack)
    : FLOATING_SCROLLBAR_MIN_THUMB
  const horizontalThumbSize = showHorizontal
    ? clamp((body.clientWidth / body.scrollWidth) * horizontalTrack, FLOATING_SCROLLBAR_MIN_THUMB, horizontalTrack)
    : FLOATING_SCROLLBAR_MIN_THUMB
  const verticalMaxOffset = Math.max(0, verticalTrack - verticalThumbSize)
  const horizontalMaxOffset = Math.max(0, horizontalTrack - horizontalThumbSize)

  scrollState.value = {
    showVertical,
    showHorizontal,
    verticalThumbSize,
    verticalThumbOffset: maxScrollTop <= 0 ? 0 : (body.scrollTop / maxScrollTop) * verticalMaxOffset,
    horizontalThumbSize,
    horizontalThumbOffset: maxScrollLeft <= 0 ? 0 : (body.scrollLeft / maxScrollLeft) * horizontalMaxOffset
  }
}

function startScrollbarThumbDrag(axis: 'vertical' | 'horizontal', event: PointerEvent) {
  const body = bodyRef.value
  if (!body) return
  event.preventDefault()
  const trackLength = axis === 'vertical'
    ? Math.max(0, body.clientHeight - (scrollState.value.showHorizontal ? 12 : 0))
    : Math.max(0, body.clientWidth - (scrollState.value.showVertical ? 12 : 0))
  const thumbSize = axis === 'vertical' ? scrollState.value.verticalThumbSize : scrollState.value.horizontalThumbSize
  activeScrollbarDrag = {
    axis,
    pointerId: event.pointerId,
    startClient: axis === 'vertical' ? event.clientY : event.clientX,
    startScroll: axis === 'vertical' ? body.scrollTop : body.scrollLeft,
    maxScroll: axis === 'vertical' ? Math.max(0, body.scrollHeight - body.clientHeight) : Math.max(0, body.scrollWidth - body.clientWidth),
    maxThumbOffset: Math.max(0, trackLength - thumbSize)
  }
  const target = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  target?.setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', handleScrollbarThumbMove)
  window.addEventListener('pointerup', stopScrollbarThumbDrag, { once: true })
  window.addEventListener('pointercancel', stopScrollbarThumbDrag, { once: true })
}

function handleScrollbarThumbMove(event: PointerEvent) {
  const drag = activeScrollbarDrag
  const body = bodyRef.value
  if (!drag || !body || event.pointerId !== drag.pointerId) return
  event.preventDefault()
  const client = drag.axis === 'vertical' ? event.clientY : event.clientX
  const delta = client - drag.startClient
  const scrollDelta = drag.maxThumbOffset <= 0 ? 0 : (delta / drag.maxThumbOffset) * drag.maxScroll
  if (drag.axis === 'vertical') body.scrollTop = drag.startScroll + scrollDelta
  else body.scrollLeft = drag.startScroll + scrollDelta
  updateVirtualMetrics()
}

function stopScrollbarThumbDrag() {
  activeScrollbarDrag = null
  window.removeEventListener('pointermove', handleScrollbarThumbMove)
  window.removeEventListener('pointerup', stopScrollbarThumbDrag)
  window.removeEventListener('pointercancel', stopScrollbarThumbDrag)
}

function handleScrollbarTrackPointerDown(axis: 'vertical' | 'horizontal', event: PointerEvent) {
  const body = bodyRef.value
  if (!body || !(event.target instanceof HTMLElement) || event.target.classList.contains('file-floating-scrollbar-thumb')) return
  event.preventDefault()
  const rect = event.currentTarget instanceof HTMLElement ? event.currentTarget.getBoundingClientRect() : null
  if (!rect) return
  if (axis === 'vertical') {
    const targetRatio = clamp((event.clientY - rect.top) / rect.height, 0, 1)
    body.scrollTop = targetRatio * Math.max(0, body.scrollHeight - body.clientHeight)
  } else {
    const targetRatio = clamp((event.clientX - rect.left) / rect.width, 0, 1)
    body.scrollLeft = targetRatio * Math.max(0, body.scrollWidth - body.clientWidth)
  }
  updateVirtualMetrics()
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
  scrollIndexIntoView(next)
  await nextTick()
  const row = rowRefs.value[next]
  row?.focus()
}

function scrollIndexIntoView(index: number) {
  const body = bodyRef.value
  if (!body) return

  const stickyOffset = parentSlotHeight.value
  const rowTop = stickyOffset + index * FILE_ROW_SLOT_HEIGHT
  const rowBottom = rowTop + FILE_ROW_SLOT_HEIGHT
  const visibleTop = body.scrollTop + stickyOffset
  const visibleBottom = body.scrollTop + body.clientHeight

  if (rowTop < visibleTop) {
    body.scrollTop = Math.max(0, rowTop - stickyOffset)
  } else if (rowBottom > visibleBottom) {
    body.scrollTop = rowBottom - body.clientHeight
  }

  updateVirtualMetrics()
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
  const body = bodyRef.value
  const left = Math.min(blankDragStartX, blankDragCurrentX)
  const right = Math.max(blankDragStartX, blankDragCurrentX)
  const top = Math.min(blankDragStartY, blankDragCurrentY)
  const bottom = Math.max(blankDragStartY, blankDragCurrentY)
  const next = new Set<string>()
  const selectedIndices: number[] = []

  if (body && sortedItems.value.length > 0) {
    const bodyRect = body.getBoundingClientRect()
    const contentTop = bodyRect.top + FILE_BODY_VERTICAL_PADDING + parentSlotHeight.value - body.scrollTop
    const contentBottom = contentTop + sortedItems.value.length * FILE_ROW_SLOT_HEIGHT
    const intersectsHorizontally = right >= bodyRect.left && left <= bodyRect.right

    if (intersectsHorizontally && bottom >= contentTop && top <= contentBottom) {
      const firstIndex = clamp(Math.floor((top - contentTop) / FILE_ROW_SLOT_HEIGHT), 0, sortedItems.value.length - 1)
      const lastIndex = clamp(Math.floor((bottom - contentTop) / FILE_ROW_SLOT_HEIGHT), 0, sortedItems.value.length - 1)

      for (let index = firstIndex; index <= lastIndex; index += 1) {
        const item = sortedItems.value[index]
        if (!item) continue
        next.add(item.path)
        selectedIndices.push(index)
      }
    }
  }

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
  writeChemSSHFileDrag(event.dataTransfer, items)
  setDragImage(event, items)
}

function handleMoveDragOver(index: number, event: DragEvent) {
  const item = sortedItems.value[index]
  handleMoveDragOverItem(item, event)
}

function handleMoveDragOverItem(item: FileItem | undefined | null, event: DragEvent) {
  if (!item || !hasChemSSHFileDrag(event)) return
  const payload = fileDragPayloadForEvent(event)
  if (!payload || !isValidMoveTarget(item, payload)) {
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'
    if (moveDropTargetPath.value === item.path) moveDropTargetPath.value = null
    return
  }

  event.preventDefault()
  event.stopPropagation()
  moveDropTargetPath.value = item.path
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleMoveDragLeave(index: number, event: DragEvent) {
  const item = sortedItems.value[index]
  handleMoveDragLeaveItem(item, event)
}

function handleMoveDragLeaveItem(item: FileItem | undefined | null, event: DragEvent) {
  if (!item || moveDropTargetPath.value !== item.path) return
  const row = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const related = event.relatedTarget instanceof Node ? event.relatedTarget : null
  if (row && related && row.contains(related)) return
  moveDropTargetPath.value = null
}

function handleMoveDrop(index: number, event: DragEvent) {
  const item = sortedItems.value[index]
  handleMoveDropItem(item, event)
}

function handleMoveDropItem(item: FileItem | undefined | null, event: DragEvent) {
  const payload = fileDragPayloadForEvent(event)
  moveDropTargetPath.value = null
  if (!item || !payload || !isValidMoveTarget(item, payload)) return

  event.preventDefault()
  event.stopPropagation()
  emit('move-items', payload.items, item)
  finishFileDrag()
}

function fileDragPayloadForEvent(event: DragEvent) {
  return readChemSSHFileDrag(event.dataTransfer) ?? getActiveChemSSHFileDragPayload()
}

function isValidMoveTarget(target: FileItem, payload: ChemSSHFileDragPayload) {
  if (target.type !== 'directory' || payload.paths.length === 0) return false
  const targetPath = normalizePath(target.path)
  return payload.items.every(item => {
    const sourcePath = normalizePath(item.path)
    if (sourcePath === targetPath) return false
    if (item.type === 'directory' && isPathInside(targetPath, sourcePath)) return false
    return true
  })
}

function normalizePath(path: string) {
  return path.replace(/\\/g, '/').replace(/\/+$/, '')
}

function isPathInside(path: string, parent: string) {
  return path === parent || path.startsWith(`${parent}/`)
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
  moveDropTargetPath.value = null
  clearActiveChemSSHFileDragPayload()
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
    void nextTick(updateVirtualMetrics)
  }
)

onMounted(() => {
  window.addEventListener('mouseup', finishSelection)
  void nextTick(() => {
    updateVirtualMetrics()
    scrollResizeObserver = new ResizeObserver(updateVirtualMetrics)
    if (bodyRef.value) scrollResizeObserver.observe(bodyRef.value)
    if (treeRef.value) scrollResizeObserver.observe(treeRef.value)
  })
})

onBeforeUnmount(() => {
  stopColumnResize()
  stopScrollbarThumbDrag()
  scrollResizeObserver?.disconnect()
  scrollResizeObserver = null
  window.removeEventListener('mouseup', finishSelection)
  window.removeEventListener('mousemove', handleBlankDragMove)
  window.removeEventListener('mousemove', handlePressMove)
  cancelLongPress()
})
</script>

import { computed, onBeforeUnmount, ref, type Ref } from 'vue'

export type ColumnResizeTarget = 'name-size' | 'size-time'

const DEFAULT_SIZE_COLUMN_WIDTH = 88
const DEFAULT_TIME_COLUMN_WIDTH = 152
const MIN_NAME_COLUMN_WIDTH = 160
const MIN_SIZE_COLUMN_WIDTH = 64
const MAX_SIZE_COLUMN_WIDTH = 168
const MIN_TIME_COLUMN_WIDTH = 112
const MAX_TIME_COLUMN_WIDTH = 260
const FILE_ICON_COLUMN_WIDTH = 34
const FILE_COLUMN_RESIZER_WIDTH = 10

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

export function useFileTreeColumns(treeRef: Ref<HTMLElement | null>) {
  const activeColumnResize = ref<ColumnResizeTarget | null>(null)
  const sizeColumnWidth = ref(DEFAULT_SIZE_COLUMN_WIDTH)
  const timeColumnWidth = ref(DEFAULT_TIME_COLUMN_WIDTH)

  let columnResizeStartX = 0
  let columnResizeStartSize = 0
  let columnResizeStartTime = 0
  let previousBodyCursor = ''
  let previousBodyUserSelect = ''

  const columnStyle = computed<Record<string, string>>(() => ({
    '--file-size-col': `${sizeColumnWidth.value}px`,
    '--file-time-col': `${timeColumnWidth.value}px`
  }))

  function maxSizeColumnWidth() {
    const width = treeRef.value?.getBoundingClientRect().width ?? 0
    if (width <= 0) return MAX_SIZE_COLUMN_WIDTH
    const reserved =
      FILE_ICON_COLUMN_WIDTH +
      FILE_COLUMN_RESIZER_WIDTH * 2 +
      MIN_NAME_COLUMN_WIDTH +
      timeColumnWidth.value
    return Math.min(MAX_SIZE_COLUMN_WIDTH, Math.max(MIN_SIZE_COLUMN_WIDTH, width - reserved))
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
    const maxSize = Math.min(
      MAX_SIZE_COLUMN_WIDTH,
      combinedWidth - MIN_TIME_COLUMN_WIDTH,
      maxSizeColumnWidth()
    )
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

  function resetColumnWidths() {
    sizeColumnWidth.value = DEFAULT_SIZE_COLUMN_WIDTH
    timeColumnWidth.value = DEFAULT_TIME_COLUMN_WIDTH
  }

  onBeforeUnmount(() => {
    stopColumnResize()
  })

  return {
    activeColumnResize,
    columnStyle,
    startColumnResize,
    resetColumnWidths,
    stopColumnResize
  }
}

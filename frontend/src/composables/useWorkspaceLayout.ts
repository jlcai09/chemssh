import { computed, onBeforeUnmount, ref, type Ref } from 'vue'

const WORKSPACE_SPLITTER_SIZE = 12
const MIN_LEFT_WIDTH = 260
const MIN_MAIN_WIDTH = 320
const MIN_SIDE_WIDTH = 300
const MIN_QUEUE_HEIGHT = 180
const MIN_LOG_HEIGHT = 120

type ResizeTarget = 'left' | 'right' | 'side'
type ResizeState = {
  target: ResizeTarget
  startClientX: number
  startClientY: number
  startLeftWidth: number
  startSideWidth: number
  startQueueHeight: number
}

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

export function useWorkspaceLayout(
  workspaceRef: Ref<HTMLElement | null>,
  leftPaneRef: Ref<HTMLElement | null>,
  sidePaneRef: Ref<HTMLElement | null>,
  onResizeEnd: () => void,
  onCloseContextMenu: () => void
) {
  const activeResize = ref<ResizeState | null>(null)
  const leftPaneWidth = ref<number | null>(null)
  const sidePaneWidth = ref<number | null>(null)
  const sideQueueHeight = ref<number | null>(null)
  const terminalLayoutVersion = ref(0)

  let previousBodyCursor = ''
  let previousBodyUserSelect = ''

  const workspaceStyle = computed<Record<string, string | undefined>>(() => ({
    '--workspace-left': leftPaneWidth.value === null ? undefined : `${leftPaneWidth.value}px`,
    '--workspace-side': sidePaneWidth.value === null ? undefined : `${sidePaneWidth.value}px`,
    '--workspace-splitter-size': `${WORKSPACE_SPLITTER_SIZE}px`
  }))

  const sideStyle = computed<Record<string, string | undefined>>(() => ({
    '--workspace-queue': sideQueueHeight.value === null ? undefined : `${sideQueueHeight.value}px`
  }))

  function isSideVisible() {
    if (!sidePaneRef.value) return false
    return window.getComputedStyle(sidePaneRef.value).display !== 'none'
  }

  function measuredWidth(element: HTMLElement | null, fallback: number) {
    const width = element?.getBoundingClientRect().width
    return width && width > 0 ? width : fallback
  }

  function measuredHeight(element: HTMLElement | null, fallback: number) {
    const height = element?.getBoundingClientRect().height
    return height && height > 0 ? height : fallback
  }

  function currentLeftWidth() {
    return leftPaneWidth.value ?? measuredWidth(leftPaneRef.value, 360)
  }

  function currentSideWidth() {
    return sidePaneWidth.value ?? measuredWidth(sidePaneRef.value, 360)
  }

  function currentQueueHeight() {
    const panel = sidePaneRef.value?.querySelector('.side-work-panel') as HTMLElement | null
    return sideQueueHeight.value ?? measuredHeight(panel, 260)
  }

  function beginResize(cursor: string) {
    previousBodyCursor = document.body.style.cursor
    previousBodyUserSelect = document.body.style.userSelect
    document.body.style.cursor = cursor
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResize, { once: true })
    window.addEventListener('pointercancel', stopResize, { once: true })
  }

  function startColumnResize(target: 'left' | 'right', event: PointerEvent) {
    if (!workspaceRef.value) return
    event.preventDefault()
    onCloseContextMenu()
    const startLeftWidth = currentLeftWidth()
    const startSideWidth = isSideVisible() ? currentSideWidth() : 0
    activeResize.value = {
      target,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLeftWidth,
      startSideWidth,
      startQueueHeight: currentQueueHeight()
    }
    leftPaneWidth.value = startLeftWidth
    if (isSideVisible()) sidePaneWidth.value = startSideWidth
    beginResize('col-resize')
  }

  function startSideResize(event: PointerEvent) {
    if (!sidePaneRef.value) return
    event.preventDefault()
    onCloseContextMenu()
    const startQueueHeight = currentQueueHeight()
    activeResize.value = {
      target: 'side',
      startClientX: event.clientX,
      startClientY: event.clientY,
      startLeftWidth: currentLeftWidth(),
      startSideWidth: currentSideWidth(),
      startQueueHeight
    }
    sideQueueHeight.value = startQueueHeight
    beginResize('row-resize')
  }

  function handlePointerMove(event: PointerEvent) {
    const resizeState = activeResize.value
    if (!resizeState) return
    if (resizeState.target === 'side') {
      resizeSide(resizeState, event.clientY)
      return
    }
    resizeColumns(resizeState, event.clientX)
  }

  function resizeColumns(resizeState: ResizeState, clientX: number) {
    if (!workspaceRef.value) return
    const rect = workspaceRef.value.getBoundingClientRect()
    const totalWidth = rect.width
    const sideVisible = isSideVisible()
    const splitterTotal = sideVisible ? WORKSPACE_SPLITTER_SIZE * 2 : WORKSPACE_SPLITTER_SIZE
    const deltaX = clientX - resizeState.startClientX

    if (resizeState.target === 'left') {
      const reservedSide = sideVisible ? resizeState.startSideWidth : 0
      const maxLeft = totalWidth - reservedSide - MIN_MAIN_WIDTH - splitterTotal
      leftPaneWidth.value = clamp(resizeState.startLeftWidth + deltaX, MIN_LEFT_WIDTH, maxLeft)
      notifyTerminalLayoutChanged()
      return
    }

    if (!sideVisible) return
    const reservedLeft = resizeState.startLeftWidth
    const maxSide = totalWidth - reservedLeft - MIN_MAIN_WIDTH - splitterTotal
    sidePaneWidth.value = clamp(resizeState.startSideWidth - deltaX, MIN_SIDE_WIDTH, maxSide)
    notifyTerminalLayoutChanged()
  }

  function resizeSide(resizeState: ResizeState, clientY: number) {
    if (!sidePaneRef.value) return
    const rect = sidePaneRef.value.getBoundingClientRect()
    const maxQueue = rect.height - MIN_LOG_HEIGHT - WORKSPACE_SPLITTER_SIZE
    const deltaY = clientY - resizeState.startClientY
    sideQueueHeight.value = clamp(resizeState.startQueueHeight + deltaY, MIN_QUEUE_HEIGHT, maxQueue)
  }

  function stopResize() {
    const resizeState = activeResize.value
    if (!resizeState) return
    const target = resizeState.target
    activeResize.value = null
    document.body.style.cursor = previousBodyCursor
    document.body.style.userSelect = previousBodyUserSelect
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', stopResize)
    window.removeEventListener('pointercancel', stopResize)
    if (target === 'left' || target === 'right') notifyTerminalLayoutChanged()
    onResizeEnd()
  }

  function resetColumnLayout() {
    leftPaneWidth.value = null
    sidePaneWidth.value = null
    onResizeEnd()
    notifyTerminalLayoutChanged()
  }

  function resetSideLayout() {
    sideQueueHeight.value = null
    onResizeEnd()
  }

  function notifyTerminalLayoutChanged() {
    terminalLayoutVersion.value += 1
    window.requestAnimationFrame(() => window.dispatchEvent(new Event('chemssh:terminal-fit')))
  }

  onBeforeUnmount(() => {
    stopResize()
  })

  return {
    WORKSPACE_SPLITTER_SIZE,
    activeResize,
    leftPaneWidth,
    sidePaneWidth,
    sideQueueHeight,
    terminalLayoutVersion,
    workspaceStyle,
    sideStyle,
    startColumnResize,
    startSideResize,
    resetColumnLayout,
    resetSideLayout,
    notifyTerminalLayoutChanged,
    stopResize
  }
}

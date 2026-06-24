import { onBeforeUnmount, ref, type Ref } from 'vue'

const FLOATING_SCROLLBAR_MIN_THUMB = 28

function clamp(value: number, min: number, max: number) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

interface ScrollbarState {
  showVertical: boolean
  showHorizontal: boolean
  verticalThumbSize: number
  verticalThumbOffset: number
  horizontalThumbSize: number
  horizontalThumbOffset: number
}

interface ActiveScrollbarDrag {
  axis: 'vertical' | 'horizontal'
  pointerId: number
  startClient: number
  startScroll: number
  maxScroll: number
  maxThumbOffset: number
}

export function useFileTreeScrollbars(
  bodyRef: Ref<HTMLElement | null>,
  onScrollChange: () => void
) {
  const scrollState = ref<ScrollbarState>({
    showVertical: false,
    showHorizontal: false,
    verticalThumbSize: FLOATING_SCROLLBAR_MIN_THUMB,
    verticalThumbOffset: 0,
    horizontalThumbSize: FLOATING_SCROLLBAR_MIN_THUMB,
    horizontalThumbOffset: 0
  })

  let activeScrollbarDrag: ActiveScrollbarDrag | null = null

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
    const trackLength =
      axis === 'vertical'
        ? Math.max(0, body.clientHeight - (scrollState.value.showHorizontal ? 12 : 0))
        : Math.max(0, body.clientWidth - (scrollState.value.showVertical ? 12 : 0))
    const thumbSize =
      axis === 'vertical' ? scrollState.value.verticalThumbSize : scrollState.value.horizontalThumbSize
    activeScrollbarDrag = {
      axis,
      pointerId: event.pointerId,
      startClient: axis === 'vertical' ? event.clientY : event.clientX,
      startScroll: axis === 'vertical' ? body.scrollTop : body.scrollLeft,
      maxScroll:
        axis === 'vertical'
          ? Math.max(0, body.scrollHeight - body.clientHeight)
          : Math.max(0, body.scrollWidth - body.clientWidth),
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
    onScrollChange()
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
    onScrollChange()
  }

  function isScrollbarEvent(element: HTMLElement, event: MouseEvent) {
    const rect = element.getBoundingClientRect()
    const verticalScrollbar = element.offsetWidth - element.clientWidth
    const horizontalScrollbar = element.offsetHeight - element.clientHeight
    const onVerticalScrollbar = verticalScrollbar > 0 && event.clientX >= rect.right - verticalScrollbar
    const onHorizontalScrollbar = horizontalScrollbar > 0 && event.clientY >= rect.bottom - horizontalScrollbar
    return onVerticalScrollbar || onHorizontalScrollbar
  }

  onBeforeUnmount(() => {
    stopScrollbarThumbDrag()
  })

  return {
    scrollState,
    updateScrollbars,
    startScrollbarThumbDrag,
    stopScrollbarThumbDrag,
    handleScrollbarTrackPointerDown,
    isScrollbarEvent
  }
}

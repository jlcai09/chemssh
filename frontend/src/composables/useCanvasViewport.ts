import { ref, type Ref } from 'vue'
import {
  DEFAULT_CANVAS_VIEWPORT,
  type CanvasBoard
} from '../types/canvasBoard'

const MIN_ZOOM = 0.25
const MAX_ZOOM = 2.5

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function useCanvasViewport(
  surfaceRef: Ref<HTMLElement | null>,
  activeBoard: Ref<CanvasBoard | null>,
  onViewportChange: () => void
) {
  function resetView() {
    const board = activeBoard.value
    if (!board) return
    board.viewport = { ...DEFAULT_CANVAS_VIEWPORT }
    onViewportChange()
  }

  function zoomBy(multiplier: number) {
    const board = activeBoard.value
    const surface = surfaceRef.value
    if (!board || !surface) return
    const rect = surface.getBoundingClientRect()
    zoomAt(rect.width / 2, rect.height / 2, multiplier)
  }

  function handleWheel(event: WheelEvent) {
    if (!event.ctrlKey) return
    event.preventDefault()
    const rect = surfaceRef.value?.getBoundingClientRect()
    if (!rect) return
    const multiplier = event.deltaY > 0 ? 0.92 : 1.08
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, multiplier)
  }

  function zoomAt(screenX: number, screenY: number, multiplier: number) {
    const board = activeBoard.value
    if (!board) return
    const oldZoom = board.viewport.zoom
    const nextZoom = clamp(oldZoom * multiplier, MIN_ZOOM, MAX_ZOOM)
    const worldX = (screenX - board.viewport.x) / oldZoom
    const worldY = (screenY - board.viewport.y) / oldZoom
    board.viewport.zoom = nextZoom
    board.viewport.x = screenX - worldX * nextZoom
    board.viewport.y = screenY - worldY * nextZoom
    onViewportChange()
  }

  function startPan(event: PointerEvent) {
    if (event.button !== 0) return
    const board = activeBoard.value
    if (!board) return
    const target = event.currentTarget as HTMLElement
    const startX = event.clientX
    const startY = event.clientY
    const originX = board.viewport.x
    const originY = board.viewport.y
    target.setPointerCapture(event.pointerId)

    const move = (moveEvent: PointerEvent) => {
      board.viewport.x = originX + moveEvent.clientX - startX
      board.viewport.y = originY + moveEvent.clientY - startY
    }
    const done = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', done)
      target.removeEventListener('pointercancel', done)
    }

    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', done)
    target.addEventListener('pointercancel', done)
  }

  return { MIN_ZOOM, MAX_ZOOM, resetView, zoomBy, handleWheel, zoomAt, startPan }
}

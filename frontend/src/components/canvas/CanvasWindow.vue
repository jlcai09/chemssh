<template>
  <section
    ref="windowRef"
    class="canvas-window"
    :class="{ 'is-active': active, 'is-minimized': window.minimized, 'is-dragging': isDragging }"
    :style="windowStyle"
    @pointerdown="$emit('activate', window.id)"
  >
    <header class="canvas-window-titlebar" @pointerdown.stop="startDrag">
      <div class="canvas-window-title">
        <span class="canvas-window-kind" :style="kindChipStyle">{{ displayKindLabel }}</span>
        <strong>{{ window.title }}</strong>
        <span
          v-if="bindingLabel"
          class="canvas-window-binding-chip"
          :style="bindingChipStyle"
          :title="bindingLabel"
        >
          {{ bindingLabel }}
        </span>
      </div>
      <div class="canvas-window-actions" @pointerdown.stop>
        <el-tooltip :content="window.minimized ? t('canvas.restoreWindow') : t('canvas.minimizeWindow')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="canvas-window-icon" type="button" @click="$emit('toggle-minimize', window.id)">
            <el-icon><SemiSelect /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip :content="t('canvas.closeWindow')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
          <button class="canvas-window-icon is-danger" type="button" @click="$emit('close', window.id)">
            <el-icon><Close /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </header>
    <div v-show="!window.minimized" class="canvas-window-body">
      <slot />
    </div>
    <button
      v-show="!window.minimized"
      class="canvas-window-resize"
      type="button"
      :aria-label="t('canvas.resizeWindow')"
      @pointerdown.stop="startResize"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Close, SemiSelect } from '@element-plus/icons-vue'
import { t } from '../../i18n'
import { CANVAS_WINDOW_MINIMIZED_HEIGHT, type CanvasWindowState } from '../../types/canvasBoard'

const props = defineProps<{
  window: CanvasWindowState
  active?: boolean
  zoom?: number
  kindLabel?: string
  bindingLabel?: string
  bindingColor?: string
}>()

const emit = defineEmits<{
  activate: [id: string]
  close: [id: string]
  move: [id: string, x: number, y: number]
  resize: [id: string, width: number, height: number]
  'toggle-minimize': [id: string]
}>()

const windowRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)

const windowStyle = computed(() => ({
  left: `${props.window.x}px`,
  top: `${props.window.y}px`,
  width: `${props.window.width}px`,
  height: `${props.window.minimized ? CANVAS_WINDOW_MINIMIZED_HEIGHT : props.window.height}px`,
  zIndex: String(props.window.zIndex)
}))

const kindLabel = computed(() => {
  const labels = {
    'file-manager': t('canvas.window.fileManager'),
    queue: t('canvas.window.queue'),
    tail: t('canvas.window.tail'),
    preview: t('canvas.window.preview'),
    terminal: t('canvas.window.terminal'),
    plugin: t('canvas.window.plugin')
  }
  return labels[props.window.type]
})

const displayKindLabel = computed(() => props.kindLabel || kindLabel.value)

const kindChipStyle = computed(() => ({
  '--kind-color': props.bindingColor || '#176b87'
}))

const bindingChipStyle = computed(() => ({
  '--binding-color': props.bindingColor || '#176b87'
}))

function startDrag(event: PointerEvent) {
  if (event.button !== 0) return
  const startX = event.clientX
  const startY = event.clientY
  const originX = props.window.x
  const originY = props.window.y
  const zoom = props.zoom || 1
  const target = event.currentTarget as HTMLElement
  const element = windowRef.value

  target.setPointerCapture(event.pointerId)
  emit('activate', props.window.id)
  isDragging.value = true

  let rafId: number | null = null
  let pendingX = originX
  let pendingY = originY

  const move = (moveEvent: PointerEvent) => {
    // 计算新位置，但不立即发送事件
    pendingX = originX + (moveEvent.clientX - startX) / zoom
    pendingY = originY + (moveEvent.clientY - startY) / zoom

    // 使用 transform 实现即时视觉反馈，避免等待状态更新
    if (element) {
      element.style.transform = `translate(${pendingX - originX}px, ${pendingY - originY}px)`
    }

    // 使用 RAF 批量更新状态，降低 Vue 更新频率
    if (rafId === null) {
      rafId = requestAnimationFrame(() => {
        emit('move', props.window.id, pendingX, pendingY)
        rafId = null
      })
    }
  }

  const done = () => {
    isDragging.value = false

    // 取消待处理的 RAF
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }

    // 发送最终位置并清除 transform
    emit('move', props.window.id, pendingX, pendingY)
    if (element) {
      element.style.transform = ''
    }

    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', done)
    target.removeEventListener('pointercancel', done)
  }

  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', done)
  target.addEventListener('pointercancel', done)
}

function startResize(event: PointerEvent) {
  if (event.button !== 0) return
  const startX = event.clientX
  const startY = event.clientY
  const originWidth = props.window.width
  const originHeight = props.window.height
  const zoom = props.zoom || 1
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  emit('activate', props.window.id)

  const move = (moveEvent: PointerEvent) => {
    emit(
      'resize',
      props.window.id,
      Math.max(280, originWidth + (moveEvent.clientX - startX) / zoom),
      Math.max(180, originHeight + (moveEvent.clientY - startY) / zoom)
    )
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
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="menuRef"
      class="structure-context-menu"
      :style="menuPositionStyle"
      role="menu"
      @contextmenu.prevent
    >
      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection }"
        :disabled="!hasSelection"
        role="menuitem"
        @click="emitAction('select-connected')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.selectConnectedFragment') }}</span>
      </button>

      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection }"
        :disabled="!hasSelection"
        role="menuitem"
        @click="emitAction('select-same')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.selectSameFragment') }}</span>
      </button>

      <div
        class="ctx-submenu-wrapper"
        @mouseenter="openSubmenu('select')"
        @mouseleave="scheduleCloseSubmenu"
      >
        <button type="button" class="ctx-item" role="menuitem" aria-haspopup="true">
          <span class="ctx-label">{{ t('viewer.contextMenu.selectMenu') }}</span>
          <span class="ctx-arrow">▸</span>
        </button>
        <div
          v-if="activeSubmenu === 'select'"
          class="structure-context-submenu"
          :class="{ 'is-left': flipSubmenuLeft }"
          role="menu"
          @mouseenter="cancelCloseSubmenu"
          @mouseleave="scheduleCloseSubmenu"
        >
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('select-same-element')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.selectSameElement') }}</span>
          </button>
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('select-within-radius')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.selectWithinRadius') }}</span>
          </button>
          <div class="ctx-divider" />
          <button type="button" class="ctx-item" role="menuitem" @click="emitAction('invert-selection')">
            <span class="ctx-label">{{ t('viewer.contextMenu.invertSelection') }}</span>
            <span class="ctx-shortcut">Ctrl+I</span>
          </button>
          <button type="button" class="ctx-item" role="menuitem" @click="emitAction('select-all')">
            <span class="ctx-label">{{ t('viewer.contextMenu.selectAll') }}</span>
            <span class="ctx-shortcut">Ctrl+A</span>
          </button>
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('clear-selection')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.clearSelection') }}</span>
            <span class="ctx-shortcut">Esc</span>
          </button>
        </div>
      </div>

      <div class="ctx-divider" />

      <div
        class="ctx-submenu-wrapper"
        @mouseenter="openSubmenu('display')"
        @mouseleave="scheduleCloseSubmenu"
      >
        <button
          type="button"
          class="ctx-item"
          :class="{ 'is-disabled': !hasSelection }"
          :disabled="!hasSelection"
          role="menuitem"
          aria-haspopup="true"
        >
          <span class="ctx-label">{{ t('viewer.contextMenu.display') }}</span>
          <span class="ctx-arrow">▸</span>
        </button>
        <div
          v-if="activeSubmenu === 'display' && hasSelection"
          class="structure-context-submenu"
          :class="{ 'is-left': flipSubmenuLeft }"
          role="menu"
          @mouseenter="cancelCloseSubmenu"
          @mouseleave="scheduleCloseSubmenu"
        >
          <button type="button" class="ctx-item" role="menuitem" @click="emitDisplay('stick')">
            <span class="ctx-label">{{ t('viewer.styleStick') }}</span>
          </button>
          <button type="button" class="ctx-item" role="menuitem" @click="emitDisplay('sphere')">
            <span class="ctx-label">{{ t('viewer.styleSphere') }}</span>
          </button>
          <button type="button" class="ctx-item" role="menuitem" @click="emitDisplay('line')">
            <span class="ctx-label">{{ t('viewer.styleLine') }}</span>
          </button>
          <div class="ctx-divider" />
          <button type="button" class="ctx-item" role="menuitem" @click="emitDisplay('dim')">
            <span class="ctx-label">{{ t('viewer.styleDim') }}</span>
          </button>
          <button type="button" class="ctx-item" role="menuitem" @click="emitDisplay('hidden')">
            <span class="ctx-label">{{ t('viewer.styleHide') }}</span>
          </button>
        </div>
      </div>

      <div
        class="ctx-submenu-wrapper"
        @mouseenter="openSubmenu('dynamic')"
        @mouseleave="scheduleCloseSubmenu"
      >
        <button
          type="button"
          class="ctx-item"
          role="menuitem"
          aria-haspopup="true"
        >
          <span class="ctx-label">{{ t('viewer.contextMenu.dynamicDisplay') }}</span>
          <span class="ctx-arrow">▸</span>
        </button>
        <div
          v-if="activeSubmenu === 'dynamic'"
          class="structure-context-submenu"
          :class="{ 'is-left': flipSubmenuLeft }"
          role="menu"
          @mouseenter="cancelCloseSubmenu"
          @mouseleave="scheduleCloseSubmenu"
        >
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('dynamic-hide-same-formula')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.dynamicHideSameFormula') }}</span>
          </button>
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('dynamic-dim-same-formula')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.dynamicDimSameFormula') }}</span>
          </button>
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('dynamic-line-same-formula')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.dynamicLineSameFormula') }}</span>
          </button>
          <div class="ctx-divider" />
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('dynamic-show-only-shell')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.dynamicShowOnlyShell') }}</span>
          </button>
          <button
            type="button"
            class="ctx-item"
            :class="{ 'is-disabled': !hasSelection }"
            :disabled="!hasSelection"
            role="menuitem"
            @click="emitAction('dynamic-dim-outside-shell')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.dynamicDimOutsideShell') }}</span>
          </button>
          <div class="ctx-divider" />
          <button
            type="button"
            class="ctx-item"
            role="menuitem"
            @click="emitAction('manage-dynamic-rules')"
          >
            <span class="ctx-label">{{ t('viewer.contextMenu.manageDynamicRules') }}</span>
          </button>
        </div>
      </div>

      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection }"
        :disabled="!hasSelection"
        role="menuitem"
        @click="emitAction('show-only-selected')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.showOnlySelected') }}</span>
      </button>

      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasHidden }"
        :disabled="!hasHidden"
        role="menuitem"
        @click="emitAction('show-all')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.showAll') }}</span>
      </button>

      <div class="ctx-divider" />

      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection }"
        :disabled="!hasSelection"
        role="menuitem"
        @click="emitAction('focus-selection')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.focusSelection') }}</span>
      </button>

      <button
        v-if="isTrajectory"
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection && !followSelection }"
        :disabled="!hasSelection && !followSelection"
        role="menuitemcheckbox"
        :aria-checked="followSelection"
        @click="emitAction('toggle-follow-selection')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.followSelection') }}</span>
        <span v-if="followSelection" class="ctx-check">✓</span>
      </button>

      <div class="ctx-divider" />

      <button
        type="button"
        class="ctx-item"
        :class="{ 'is-disabled': !hasSelection }"
        :disabled="!hasSelection"
        role="menuitem"
        @click="emitAction('export-selected-xyz')"
      >
        <span class="ctx-label">{{ t('viewer.contextMenu.exportSelectedXyz') }}</span>
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '../i18n'
import type { AtomDisplayMode } from '../viewer'

export type StructureContextAction =
  | 'select-connected'
  | 'select-same'
  | 'select-same-element'
  | 'select-within-radius'
  | 'invert-selection'
  | 'select-all'
  | 'clear-selection'
  | 'show-only-selected'
  | 'show-all'
  | 'focus-selection'
  | 'toggle-follow-selection'
  | 'export-selected-xyz'
  | 'dynamic-hide-same-formula'
  | 'dynamic-dim-same-formula'
  | 'dynamic-line-same-formula'
  | 'dynamic-show-only-shell'
  | 'dynamic-dim-outside-shell'
  | 'manage-dynamic-rules'

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  hasSelection: boolean
  hasHidden: boolean
  isTrajectory: boolean
  followSelection: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'action', action: StructureContextAction): void
  (event: 'display', mode: AtomDisplayMode): void
}>()

const menuRef = ref<HTMLElement | null>(null)
const activeSubmenu = ref<'select' | 'display' | 'dynamic' | null>(null)
const adjustedX = ref(0)
const adjustedY = ref(0)
const flipSubmenuLeft = ref(false)
let closeTimer: number | null = null

const menuPositionStyle = computed(() => ({
  left: `${adjustedX.value}px`,
  top: `${adjustedY.value}px`
}))

function openSubmenu(name: 'select' | 'display' | 'dynamic') {
  cancelCloseSubmenu()
  activeSubmenu.value = name
}

function scheduleCloseSubmenu() {
  cancelCloseSubmenu()
  closeTimer = window.setTimeout(() => {
    activeSubmenu.value = null
  }, 110)
}

function cancelCloseSubmenu() {
  if (closeTimer !== null) {
    window.clearTimeout(closeTimer)
    closeTimer = null
  }
}

function emitAction(action: StructureContextAction) {
  emit('action', action)
  emit('close')
}

function emitDisplay(mode: AtomDisplayMode) {
  emit('display', mode)
  emit('close')
}

async function clampMenuPosition() {
  adjustedX.value = props.x
  adjustedY.value = props.y
  await nextTick()
  const el = menuRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const margin = 8
  let nextX = props.x
  let nextY = props.y
  if (nextX + rect.width + margin > vw) {
    nextX = Math.max(margin, vw - rect.width - margin)
  }
  if (nextY + rect.height + margin > vh) {
    nextY = Math.max(margin, vh - rect.height - margin)
  }
  adjustedX.value = nextX
  adjustedY.value = nextY
  flipSubmenuLeft.value = nextX + rect.width + 188 > vw
}

function handleGlobalPointerDown(event: PointerEvent) {
  if (!props.visible) return
  const target = event.target as Node | null
  if (target && menuRef.value?.contains(target)) return
  emit('close')
}

function handleGlobalKeyDown(event: KeyboardEvent) {
  if (!props.visible) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
}

watch(
  () => [props.visible, props.x, props.y],
  ([visible]) => {
    activeSubmenu.value = null
    if (visible) void clampMenuPosition()
  }
)

onMounted(() => {
  window.addEventListener('pointerdown', handleGlobalPointerDown, true)
  window.addEventListener('keydown', handleGlobalKeyDown)
})

onBeforeUnmount(() => {
  cancelCloseSubmenu()
  window.removeEventListener('pointerdown', handleGlobalPointerDown, true)
  window.removeEventListener('keydown', handleGlobalKeyDown)
})
</script>

<style scoped>
.structure-context-menu,
.structure-context-submenu {
  position: fixed;
  z-index: 3500;
  min-width: 196px;
  padding: 5px;
  border-radius: 10px;
  background: var(--el-bg-color-overlay, rgba(255, 255, 255, 0.96));
  border: 1px solid var(--el-border-color-light, rgba(148, 163, 184, 0.35));
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.16), 0 2px 6px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(12px);
  user-select: none;
  font-size: 12.5px;
}

.ctx-submenu-wrapper {
  position: relative;
}

.structure-context-submenu {
  position: absolute;
  top: -5px;
  left: calc(100% + 4px);
  min-width: 176px;
}

.structure-context-submenu.is-left {
  left: auto;
  right: calc(100% + 4px);
}

.ctx-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--el-text-color-primary, #1f2937);
  font-size: inherit;
  line-height: 1.35;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease, color 0.12s ease;
}

.ctx-item:hover:not(:disabled) {
  background: var(--el-fill-color-light, rgba(59, 130, 246, 0.1));
  color: var(--el-color-primary, #2563eb);
}

.ctx-item.is-disabled,
.ctx-item:disabled {
  color: var(--el-text-color-disabled, #9ca3af);
  cursor: not-allowed;
}

.ctx-label {
  flex: 1;
  white-space: nowrap;
}

.ctx-arrow,
.ctx-shortcut,
.ctx-check {
  font-size: 11px;
  color: var(--el-text-color-secondary, #6b7280);
  flex-shrink: 0;
}

.ctx-check {
  color: var(--el-color-primary, #2563eb);
  font-weight: 700;
}

.ctx-divider {
  height: 1px;
  margin: 4px 6px;
  background: var(--el-border-color-lighter, rgba(148, 163, 184, 0.28));
}
</style>

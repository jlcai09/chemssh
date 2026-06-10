<template>
  <Teleport to="body" :disabled="!largeOpen">
    <div class="terminal-panel" :class="{ 'is-large': largeOpen }">
      <div
        ref="tabsRef"
        class="terminal-tabs"
        :class="{ 'is-overflowing': tabsOverflowing }"
        role="tablist"
        :aria-label="t('terminal.title')"
      >
      <div
        v-for="tab in tabs"
        :key="tab.localId"
        class="terminal-tab"
        :class="{ 'is-active': tab.localId === activeTabId, 'is-connected': tab.connected }"
        role="tab"
        tabindex="0"
        draggable="true"
        :aria-selected="tab.localId === activeTabId"
        :title="tab.cwd || tab.sessionId || ''"
        @click="activateTab(tab.localId)"
        @keydown.enter.prevent="activateTab(tab.localId)"
        @keydown.space.prevent="activateTab(tab.localId)"
        @dragstart="handleTabDragStart(tab.localId, $event)"
        @dragover="handleTabDragOver($event)"
        @drop="handleTabDrop(tab.localId, $event)"
      >
        <span class="terminal-tab-label">{{ tabTitle(tab) }}</span>
        <span
          v-if="boundFileManagerLabel(tab)"
          class="terminal-tab-binding-label"
          :style="{ '--binding-color': boundFileManagerColor(tab) }"
        >
          {{ boundFileManagerLabel(tab) }}
        </span>
        <span class="terminal-tab-actions" @click.stop>
          <el-dropdown
            v-if="fileManagerOptions.length > 0"
            trigger="click"
            placement="bottom"
            @command="handleTabBindCommand(tab, $event)"
          >
            <button
              class="terminal-tab-icon terminal-tab-bind"
              :class="{ 'is-bound': Boolean(tab.boundFileManagerId) }"
              type="button"
              :aria-label="t('terminal.bindFileManager')"
            >
              <el-icon><Link /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="">{{ t('terminal.bindNone') }}</el-dropdown-item>
                <el-dropdown-item
                  v-for="manager in fileManagerOptions"
                  :key="manager.id"
                  :command="manager.id"
                >
                  <span class="terminal-bind-option">
                    <span class="terminal-bind-dot" :style="{ background: manager.color }" />
                    <span>{{ manager.title }}</span>
                  </span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip :content="syncModeLabel(tab.syncMode)" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
            <button
              class="terminal-tab-icon terminal-tab-sync"
              :class="`is-${tab.syncMode}`"
              type="button"
              :aria-pressed="tab.syncMode !== 'off'"
              :aria-label="syncModeLabel(tab.syncMode)"
              @click="toggleTabSync(tab)"
            >
              <svg class="terminal-sync-icon" viewBox="0 0 24 24" aria-hidden="true">
                <path class="sync-device sync-device-files" d="M3.5 8.5h4.4l1.2 1.7h3.4v5.9h-9z" />
                <path class="sync-device sync-device-terminal" d="M16 7h4.5v10H16z" />
                <path class="sync-arrow sync-arrow-forward" d="M10.4 10.2h4.3m-1.6-1.7 1.8 1.7-1.8 1.7" />
                <path class="sync-arrow sync-arrow-back" d="M13.6 14.8H9.3m1.6-1.7-1.8 1.7 1.8 1.7" />
                <path class="sync-slash" d="M4.8 19.2 19.2 4.8" />
              </svg>
            </button>
          </el-tooltip>
          <el-tooltip :content="t('terminal.close')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
            <button
              class="terminal-tab-icon terminal-tab-close"
              type="button"
              :aria-label="t('terminal.close')"
              @click="closeTab(tab.localId)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </el-tooltip>
        </span>
      </div>

      <button class="terminal-tab-new" type="button" :aria-label="t('terminal.newTab')" @click="createTab()">
        <el-icon><Plus /></el-icon>
      </button>
      <el-popover trigger="click" placement="top-end" :width="280" popper-class="terminal-settings-popper">
        <template #reference>
          <button class="terminal-tab-settings" type="button" :aria-label="t('terminal.settings')">
            <el-icon><Setting /></el-icon>
          </button>
        </template>
        <div class="terminal-settings-panel">
          <div class="terminal-settings-title">{{ t('terminal.settings') }}</div>
          <label class="terminal-settings-toggle">
            <span>{{ t('terminal.vimCompatibility') }}</span>
            <el-switch v-model="vimCompatibilityMode" size="small" />
          </label>
          <div class="terminal-settings-node">
            <span>{{ t('terminal.font') }}</span>
            <el-icon><ArrowRight /></el-icon>
          </div>
          <div class="terminal-settings-submenu">
            <div class="terminal-font-size-header">
              <span>{{ t('terminal.fontSize') }}</span>
              <strong>{{ terminalFontSize }}px</strong>
            </div>
            <div class="terminal-font-size-controls">
              <el-slider
                v-model="terminalFontSizeModel"
                class="terminal-font-size-slider"
                :min="TERMINAL_FONT_SIZE_MIN"
                :max="TERMINAL_FONT_SIZE_MAX"
                :step="1"
                :show-tooltip="false"
                size="small"
              />
              <el-input-number
                v-model="terminalFontSizeModel"
                class="terminal-font-size-input"
                :min="TERMINAL_FONT_SIZE_MIN"
                :max="TERMINAL_FONT_SIZE_MAX"
                :step="1"
                controls-position="right"
                size="small"
              />
            </div>
          </div>
        </div>
      </el-popover>
      <el-tooltip :content="largeOpen ? t('terminal.exitLarge') : t('terminal.openLarge')" placement="top" popper-class="chemssh-passive-tooltip" :enterable="false" :show-after="500">
        <button class="terminal-tab-settings terminal-tab-large" type="button" :aria-label="largeOpen ? t('terminal.exitLarge') : t('terminal.openLarge')" @click="toggleLargeOpen">
          <el-icon><FullScreen /></el-icon>
        </button>
      </el-tooltip>
      </div>

      <div class="terminal-shell" @dragover="handleFileDragOver" @drop="handleFileDrop">
        <div
          v-for="tab in tabs"
          :key="tab.localId"
          :ref="el => setTerminalHost(tab.localId, el)"
          class="terminal-host"
          :class="{ 'is-active': tab.localId === activeTabId }"
        />
        <div v-if="activeTab?.awaitingVisibleShellOutput" class="terminal-overlay">{{ t('terminal.starting') }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowRight, Close, FullScreen, Link, Plus, Setting } from '@element-plus/icons-vue'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal, type IDisposable } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import {
  closeTerminalSession,
  createTerminalSession,
  listTerminalSessions,
  terminalWebSocketUrl,
  type TerminalSession
} from '../../api/terminal'
import { uploadFile } from '../../api/files'
import { requestBlob } from '../../api/http'
import { formatFileDragTerminalInput, hasChemSSHFileDrag, readChemSSHFileDrag } from '../../api/fileDrag'
import { isPathInsideWorkspace, workspacePathOrRoot } from '../../api/workspaceScope'
import { t } from '../../i18n'
import type { CanvasFileManagerBindingTarget, CanvasTerminalTabBinding } from '../../types/canvasBoard'

type TerminalMessage =
  | { type: 'output'; data: string }
  | { type: 'cwd'; path: string }
  | {
      type: 'transfer_request'
      transfer_id: string
      direction: 'upload' | 'download'
      cwd: string
      argv: string[]
      paths?: string[]
      error?: string
    }
  | { type: 'error'; code?: string; message?: string }
  | { type: 'exit'; code?: number | null }

type TerminalSyncMode = 'off' | 'follow' | 'bidirectional'

type TerminalTab = {
  localId: string
  sessionId: string | null
  cwd: string
  syncMode: TerminalSyncMode
  connected: boolean
  interactiveReady: boolean
  awaitingVisibleShellOutput: boolean
  starting: boolean
  terminal: Terminal | null
  fitAddon: FitAddon | null
  socket: WebSocket | null
  inputDisposable: IDisposable | null
  selectionDisposable: IDisposable | null
  middleClickCleanup: (() => void) | null
  latestSelection: string
  preservingMiddleClickSelection: boolean
  resizeObserver: ResizeObserver | null
  fitFrame: number
  boundFileManagerId: string | null
}

const TERMINAL_FONT_SIZE_STORAGE_KEY = 'chemssh.terminal.fontSize'
const TERMINAL_VIM_COMPATIBILITY_STORAGE_KEY = 'chemssh.terminal.vimCompatibility'
const DEFAULT_TERMINAL_FONT_SIZE = 13
const TERMINAL_FONT_SIZE_MIN = 10
const TERMINAL_FONT_SIZE_MAX = 24

const props = defineProps<{
  initialCwd?: string | null
  workspaceRoot?: string | null
  currentFileManagerPath?: string | null
  fileManagers?: CanvasFileManagerBindingTarget[]
  initialBindings?: CanvasTerminalTabBinding[]
  layoutVersion?: number
  transferUploadHandler?: (path: string, files: File[]) => Promise<void>
  deferInit?: boolean
}>()

const emit = defineEmits<{
  'cwd-change': [path: string]
  'bound-cwd-change': [managerId: string, path: string]
  'binding-summary-change': [summary: CanvasTerminalTabBinding[]]
}>()

const tabs = ref<TerminalTab[]>([])
const activeTabId = ref<string | null>(null)
const tabsRef = ref<HTMLElement | null>(null)
const tabsOverflowing = ref(false)
const terminalFontSize = ref(readStoredTerminalFontSize())
const vimCompatibilityMode = ref(readStoredVimCompatibilityMode())
const largeOpen = ref(false)
const terminalFontSizeModel = computed({
  get: () => terminalFontSize.value,
  set: (value: number | undefined) => setTerminalFontSize(value)
})
const terminalHosts = new Map<string, HTMLElement>()
let tabsResizeObserver: ResizeObserver | null = null
let tabSerial = 0
const TERMINAL_TAB_DRAG_MIME = 'application/x-chemssh-terminal-tab'

const preferredCwd = computed(() => usableWorkspacePath(props.currentFileManagerPath || props.initialCwd || props.workspaceRoot))
const fileManagerOptions = computed(() => props.fileManagers ?? [])
const activeTab = computed(() => tabs.value.find(tab => tab.localId === activeTabId.value) ?? null)

onMounted(async () => {
  window.addEventListener('resize', handleLayoutChange)
  window.addEventListener('chemssh:terminal-fit', handleLayoutChange)
  await nextTick()
  await document.fonts?.ready
  if (tabsRef.value && typeof ResizeObserver !== 'undefined') {
    tabsResizeObserver = new ResizeObserver(measureTabsOverflow)
    tabsResizeObserver.observe(tabsRef.value)
  }
  if (!props.deferInit) {
    await ensureInitialTab()
  }
  measureTabsOverflow()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleLayoutChange)
  window.removeEventListener('chemssh:terminal-fit', handleLayoutChange)
  tabsResizeObserver?.disconnect()
  tabsResizeObserver = null
  for (const tab of [...tabs.value]) {
    void disposeTab(tab, true)
  }
  tabs.value = []
  activeTabId.value = null
})

watch(
  () => props.currentFileManagerPath,
  path => {
    if (!path) return
    for (const tab of tabs.value) {
      if (!tab.boundFileManagerId && isTabFollowingFileManager(tab) && tab.cwd !== path) sendTabSyncCwd(tab, path)
    }
  }
)

watch(
  () => fileManagerOptions.value.map(item => `${item.id}\u0000${item.path}`).join('\u0001'),
  () => {
    syncTabsWithBoundFileManagers()
  }
)

watch(preferredCwd, cwd => {
  if (!cwd || tabs.value.length > 0) return
  void ensureInitialTab(cwd)
})

watch(
  () => props.deferInit,
  deferred => {
    if (!deferred && tabs.value.length === 0) {
      void ensureInitialTab()
    }
  }
)

watch(
  () => props.layoutVersion,
  () => {
    requestActiveTabFit()
  },
  { flush: 'post' }
)

watch(activeTabId, () => {
  requestActiveTabFit()
  emitTerminalBindingSummary()
})

watch(largeOpen, () => {
  window.setTimeout(handleLayoutChange, 0)
  window.setTimeout(handleLayoutChange, 120)
})

watch(
  () => tabs.value.length,
  () => {
    void nextTick(() => measureTabsOverflow())
  }
)

watch(terminalFontSize, size => {
  storeTerminalFontSize(size)
  for (const tab of tabs.value) {
    if (!tab.terminal) continue
    tab.terminal.options.fontSize = size
    void requestTabFit(tab)
  }
})

watch(vimCompatibilityMode, value => {
  storeVimCompatibilityMode(value)
})

function createEmptyTab(cwd?: string): TerminalTab {
  tabSerial += 1
  return {
    localId: `terminal_tab_${tabSerial}`,
    sessionId: null,
    cwd: usableWorkspacePath(cwd ?? preferredCwd.value),
    syncMode: 'off',
    connected: false,
    interactiveReady: false,
    awaitingVisibleShellOutput: false,
    starting: false,
    terminal: null,
    fitAddon: null,
    socket: null,
    inputDisposable: null,
    selectionDisposable: null,
    middleClickCleanup: null,
    latestSelection: '',
    preservingMiddleClickSelection: false,
    resizeObserver: null,
    fitFrame: 0,
    boundFileManagerId: null
  }
}

function normalizeInitialBindings() {
  const bindings = props.initialBindings ?? []
  return bindings.flatMap(binding => {
    if (!binding || typeof binding.tabId !== 'string') return []
    const rawCwd = typeof binding.cwd === 'string' ? binding.cwd : ''
    if (rawCwd && !isUsableWorkspacePath(rawCwd)) return []
    const cwd = usableWorkspacePath(rawCwd || props.workspaceRoot)
    if (!cwd) return []
    const syncMode: TerminalSyncMode = binding.syncMode === 'follow' || binding.syncMode === 'bidirectional'
      ? binding.syncMode
      : 'off'
    return [{
      ...binding,
      title: typeof binding.title === 'string' ? binding.title : '',
      cwd,
      syncMode,
      boundFileManagerId: typeof binding.boundFileManagerId === 'string' ? binding.boundFileManagerId : null,
      active: binding.active === true
    }]
  })
}

async function createTab(cwd?: string, binding?: CanvasTerminalTabBinding) {
  const tab = createEmptyTab(cwd)
  if (binding) {
    tab.syncMode = binding.syncMode
    tab.boundFileManagerId = binding.boundFileManagerId
    if (binding.cwd) tab.cwd = usableWorkspacePath(binding.cwd)
  }
  tabs.value.push(tab)
  activeTabId.value = tab.localId
  emitTerminalBindingSummary()
  await nextTick()
  await initializeTabTerminal(tab)
  await requestTabFit(tab)
  measureTabsOverflow()
  emitTerminalBindingSummary()
}

async function ensureInitialTab(cwd?: string) {
  if (tabs.value.length > 0) return
  const initialBindings = normalizeInitialBindings()
  if (initialBindings.length === 0) {
    await createTab(cwd)
    return
  }

  for (const binding of initialBindings) {
    await createTab(binding.cwd || cwd, binding)
  }
  const activeBinding = initialBindings.find(binding => binding.active) ?? initialBindings[0]
  const activeIndex = initialBindings.indexOf(activeBinding)
  activeTabId.value = tabs.value[Math.max(0, activeIndex)]?.localId ?? tabs.value[0]?.localId ?? null
  emitTerminalBindingSummary()
}

function activateTab(tabId: string) {
  activeTabId.value = tabId
  emitTerminalBindingSummary()
}

function handleTabDragStart(tabId: string, event: DragEvent) {
  if (!event.dataTransfer) return
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData(TERMINAL_TAB_DRAG_MIME, tabId)
}

function handleTabDragOver(event: DragEvent) {
  const types = Array.from(event.dataTransfer?.types ?? [])
  if (!types.includes(TERMINAL_TAB_DRAG_MIME)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function handleTabDrop(targetTabId: string, event: DragEvent) {
  const sourceTabId = event.dataTransfer?.getData(TERMINAL_TAB_DRAG_MIME)
  if (!sourceTabId || sourceTabId === targetTabId) return
  event.preventDefault()
  const fromIndex = tabs.value.findIndex(tab => tab.localId === sourceTabId)
  const toIndex = tabs.value.findIndex(tab => tab.localId === targetTabId)
  if (fromIndex < 0 || toIndex < 0) return
  const next = [...tabs.value]
  const [moved] = next.splice(fromIndex, 1)
  next.splice(toIndex, 0, moved)
  tabs.value = next
  void nextTick(() => {
    measureTabsOverflow()
    requestActiveTabFit()
  })
}

function setTerminalHost(tabId: string, el: unknown) {
  if (el instanceof HTMLElement) {
    terminalHosts.set(tabId, el)
    const tab = tabs.value.find(item => item.localId === tabId)
    if (tab && !tab.terminal) void initializeTabTerminal(tab)
    return
  }
  terminalHosts.delete(tabId)
}

async function initializeTabTerminal(tab: TerminalTab) {
  if (tab.terminal) return
  const host = terminalHosts.get(tab.localId)
  if (!host) return

  const terminal = new Terminal({
    cursorBlink: true,
    fontFamily: '"JetBrains Mono", Consolas, "Liberation Mono", monospace',
    fontSize: terminalFontSize.value,
    lineHeight: 1.15,
    scrollback: 3000,
    theme: {
      background: '#151b22',
      foreground: '#d7e1ea',
      cursor: '#f7c46c',
      selectionBackground: '#36546a'
    }
  })
  const fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(host)
  terminal.attachCustomKeyEventHandler(event => {
    if (event.type === 'keydown' && event.key === 'Backspace') {
      sendTabSocketMessage(tab, { type: 'input', data: '\x7f' })
      return false
    }
    return true
  })
  tab.middleClickCleanup = bindTerminalMiddleClickPaste(tab, host)

  tab.terminal = terminal
  tab.fitAddon = fitAddon
  tab.inputDisposable = terminal.onData(data => {
    sendTabSocketMessage(tab, { type: 'input', data })
  })
  tab.selectionDisposable = terminal.onSelectionChange(() => {
    const selection = terminal.getSelection()
    if (selection || !tab.preservingMiddleClickSelection) tab.latestSelection = selection
  })
  tab.resizeObserver = new ResizeObserver(() => scheduleTabFit(tab))
  tab.resizeObserver.observe(host)

  await requestTabFit(tab)
  await startTabSession(tab)
}

async function startTabSession(tab: TerminalTab) {
  if (!tab.terminal || tab.starting || tab.sessionId) return
  tab.starting = true
  tab.awaitingVisibleShellOutput = true
  tab.interactiveReady = false
  try {
    fitTabTerminal(tab)
    await cleanupDetachedSessions()
    const session = await createTerminalSession({
      cwd: usableWorkspacePath(tab.cwd || preferredCwd.value),
      rows: tab.terminal.rows,
      cols: tab.terminal.cols,
      vim_compatibility: vimCompatibilityMode.value
    })
    attachTabSession(tab, session)
  } catch (error) {
    tab.awaitingVisibleShellOutput = false
    tab.terminal.writeln(`\r\n${t('terminal.startFailed')}: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    tab.starting = false
  }
}

function attachTabSession(tab: TerminalTab, session: TerminalSession) {
  tab.sessionId = session.session_id
  tab.cwd = session.cwd
  connectTabSocket(tab, session.session_id)
}

function connectTabSocket(tab: TerminalTab, id: string) {
  closeTabSocket(tab)
  let ws: WebSocket
  try {
    ws = new WebSocket(terminalWebSocketUrl(id))
  } catch (error) {
    tab.sessionId = null
    tab.cwd = ''
    void closeTerminalSession(id)
    throw error
  }
  tab.socket = ws

  ws.onopen = () => {
    if (tab.socket !== ws) return
    tab.connected = true
    markTabInteractive(tab)
    void requestTabFit(tab)
    const managerPath = fileManagerPathForTab(tab)
    if (isTabFollowingFileManager(tab) && managerPath && tab.cwd !== managerPath) {
      sendTabSyncCwd(tab, managerPath)
    }
  }

  ws.onmessage = event => {
    handleTabSocketMessage(tab, event.data)
  }

  ws.onclose = () => {
    if (tab.socket !== ws) return
    tab.connected = false
    resetTabInteraction(tab)
  }

  ws.onerror = () => {
    if (tab.socket === ws) tab.connected = false
  }
}

function handleTabSocketMessage(tab: TerminalTab, raw: string) {
  if (!tab.terminal) return

  let message: TerminalMessage
  try {
    message = JSON.parse(raw) as TerminalMessage
  } catch {
    return
  }

  if (message.type === 'output') {
    tab.terminal.write(message.data)
    if (!tab.interactiveReady && hasVisibleTerminalContent(message.data)) markTabInteractive(tab)
  } else if (message.type === 'cwd') {
    applyTabCwd(tab, message.path)
  } else if (message.type === 'transfer_request') {
    void handleTransferRequest(tab, message)
  } else if (message.type === 'error') {
    tab.awaitingVisibleShellOutput = false
    tab.terminal.writeln(`\r\n[${message.code ?? 'ERROR'}] ${message.message ?? ''}`)
  } else if (message.type === 'exit') {
    tab.connected = false
    resetTabInteraction(tab)
    tab.terminal.writeln(`\r\n${t('terminal.exited')}`)
  }
}

async function handleTransferRequest(tab: TerminalTab, message: Extract<TerminalMessage, { type: 'transfer_request' }>) {
  if (!tab.terminal) return
  if (message.error) {
    tab.terminal.writeln(`\r\n${t('terminal.transferFailed')}: ${message.error}`)
    sendTabSocketMessage(tab, {
      type: 'transfer_result',
      transfer_id: message.transfer_id,
      success: false,
      message: message.error
    })
    return
  }

  try {
    if (message.direction === 'upload') {
      const files = await chooseTransferFiles()
      if (files.length === 0) {
        sendTabSocketMessage(tab, {
          type: 'transfer_result',
          transfer_id: message.transfer_id,
          success: false,
          message: t('terminal.transferCancelled')
        })
        return
      }

      tab.terminal.writeln(`\r\n${t('terminal.transferUploading', { count: files.length })}`)
      if (props.transferUploadHandler) {
        await props.transferUploadHandler(message.cwd, files)
      } else {
        for (const file of files) {
          await uploadFile(message.cwd, file)
        }
      }
      sendTabSocketMessage(tab, {
        type: 'transfer_result',
        transfer_id: message.transfer_id,
        success: true,
        message: t('terminal.transferUploaded', { count: files.length })
      })
      return
    }

    const paths = message.paths ?? []
    if (paths.length === 0) {
      throw new Error(t('terminal.transferNoFiles'))
    }
    await triggerTransferDownload(paths)
    sendTabSocketMessage(tab, {
      type: 'transfer_result',
      transfer_id: message.transfer_id,
      success: true,
      message: t('terminal.transferDownloadStarted')
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    tab.terminal.writeln(`\r\n${t('terminal.transferFailed')}: ${detail}`)
    sendTabSocketMessage(tab, {
      type: 'transfer_result',
      transfer_id: message.transfer_id,
      success: false,
      message: detail
    })
  }
}

function chooseTransferFiles(): Promise<File[]> {
  return new Promise(resolve => {
    const input = document.createElement('input')
    let settled = false
    input.type = 'file'
    input.multiple = true
    input.style.position = 'fixed'
    input.style.left = '-9999px'
    input.style.top = '-9999px'
    const cleanup = () => {
      input.removeEventListener('change', handleChange)
      input.removeEventListener('cancel', handleCancel)
      window.removeEventListener('focus', handleFocus)
      window.setTimeout(() => input.remove(), 0)
    }
    const settle = (files: File[]) => {
      if (settled) return
      settled = true
      cleanup()
      resolve(files)
    }
    const handleChange = () => {
      settle(Array.from(input.files ?? []))
    }
    const handleCancel = () => {
      settle([])
    }
    const handleFocus = () => {
      window.setTimeout(() => {
        if (!settled && (!input.files || input.files.length === 0)) settle([])
      }, 300)
    }
    input.addEventListener('change', handleChange)
    input.addEventListener('cancel', handleCancel)
    window.addEventListener('focus', handleFocus)
    document.body.appendChild(input)
    input.click()
  })
}

async function triggerTransferDownload(paths: string[]) {
  const query = paths.length === 1
    ? `/api/files/download?path=${encodeURIComponent(paths[0])}`
    : `/api/files/download-selection?${downloadSelectionQuery(paths)}`
  const response = await requestBlob(query)
  const url = URL.createObjectURL(response.blob)
  const link = document.createElement('a')
  link.href = url
  link.download = response.filename ?? (paths.length === 1 ? pathBaseName(paths[0]) : 'chemssh-selection.zip')
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function downloadSelectionQuery(paths: string[]) {
  const query = new URLSearchParams()
  for (const path of paths) query.append('path', path)
  return query.toString()
}

async function closeTab(tabId: string) {
  const index = tabs.value.findIndex(tab => tab.localId === tabId)
  if (index < 0) return
  const tab = tabs.value[index]
  tabs.value.splice(index, 1)
  if (activeTabId.value === tabId) {
    activeTabId.value = tabs.value[Math.min(index, tabs.value.length - 1)]?.localId ?? null
  }
  await disposeTab(tab, true)
  await nextTick()
  measureTabsOverflow()
  requestActiveTabFit()
  emitTerminalBindingSummary()
}

async function disposeTab(tab: TerminalTab, closeSession: boolean) {
  closeTabSocket(tab)
  tab.resizeObserver?.disconnect()
  tab.inputDisposable?.dispose()
  tab.selectionDisposable?.dispose()
  tab.middleClickCleanup?.()
  tab.terminal?.dispose()
  if (tab.fitFrame) window.cancelAnimationFrame(tab.fitFrame)
  terminalHosts.delete(tab.localId)
  const sessionId = tab.sessionId

  tab.sessionId = null
  tab.connected = false
  tab.terminal = null
  tab.fitAddon = null
  tab.inputDisposable = null
  tab.selectionDisposable = null
  tab.middleClickCleanup = null
  tab.latestSelection = ''
  tab.preservingMiddleClickSelection = false
  tab.resizeObserver = null
  tab.fitFrame = 0
  resetTabInteraction(tab)

  if (!closeSession || !sessionId) return
  try {
    await closeTerminalSession(sessionId)
  } catch {
    // The backend may already have closed this session.
  }
}

function closeTabSocket(tab: TerminalTab) {
  const socket = tab.socket
  if (!socket) return
  socket.onopen = null
  socket.onmessage = null
  socket.onclose = null
  socket.onerror = null
  if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
    socket.close()
  }
  tab.socket = null
}

function toggleTabSync(tab: TerminalTab) {
  const nextMode = nextSyncMode(tab.syncMode)
  tab.syncMode = nextMode
  const managerPath = fileManagerPathForTab(tab)
  if (nextMode === 'follow' && managerPath) {
    sendTabSyncCwd(tab, managerPath)
    emitTerminalBindingSummary()
    return
  }
  if (nextMode === 'bidirectional' && tab.cwd && tab.cwd !== managerPath) {
    emitTabCwdChange(tab, tab.cwd)
  }
  emitTerminalBindingSummary()
}

function nextSyncMode(mode: TerminalSyncMode): TerminalSyncMode {
  if (mode === 'off') return 'follow'
  if (mode === 'follow') return 'bidirectional'
  return 'off'
}

function syncModeLabel(mode: TerminalSyncMode) {
  if (mode === 'follow') return t('terminal.syncCwdFollow')
  if (mode === 'bidirectional') return t('terminal.syncCwdBidirectional')
  return t('terminal.syncCwdOff')
}

function handleTabBindCommand(tab: TerminalTab, command: unknown) {
  const managerId = typeof command === 'string' ? command : ''
  tab.boundFileManagerId = managerId || null
  if (tab.boundFileManagerId && tab.syncMode === 'off') tab.syncMode = 'follow'
  const path = fileManagerPathForTab(tab)
  if (path && isTabFollowingFileManager(tab) && tab.cwd !== path) sendTabSyncCwd(tab, path)
  emitTerminalBindingSummary()
}

function boundFileManager(tab: TerminalTab) {
  if (!tab.boundFileManagerId) return null
  return fileManagerOptions.value.find(item => item.id === tab.boundFileManagerId) ?? null
}

function boundFileManagerLabel(tab: TerminalTab) {
  return boundFileManager(tab)?.title ?? ''
}

function boundFileManagerColor(tab: TerminalTab) {
  return boundFileManager(tab)?.color ?? '#176b87'
}

function fileManagerPathForTab(tab: TerminalTab) {
  return boundFileManager(tab)?.path || props.currentFileManagerPath || ''
}

function usableWorkspacePath(path: string | null | undefined) {
  if (!props.workspaceRoot) return path ?? ''
  return workspacePathOrRoot(path, props.workspaceRoot)
}

function isUsableWorkspacePath(path: string | null | undefined) {
  if (!path) return false
  return props.workspaceRoot ? isPathInsideWorkspace(path, props.workspaceRoot) : true
}

function emitTabCwdChange(tab: TerminalTab, path: string) {
  if (!isUsableWorkspacePath(path)) return
  if (tab.boundFileManagerId) {
    emit('bound-cwd-change', tab.boundFileManagerId, path)
    return
  }
  emit('cwd-change', path)
}

function syncTabsWithBoundFileManagers() {
  const managerIds = new Set(fileManagerOptions.value.map(item => item.id))
  for (const tab of tabs.value) {
    if (tab.boundFileManagerId && !managerIds.has(tab.boundFileManagerId)) {
      tab.boundFileManagerId = null
      continue
    }
    const path = fileManagerPathForTab(tab)
    if (tab.boundFileManagerId && path && isTabFollowingFileManager(tab) && tab.cwd !== path) {
      sendTabSyncCwd(tab, path)
    }
  }
  emitTerminalBindingSummary()
}

function emitTerminalBindingSummary() {
  emit('binding-summary-change', tabs.value.map(tab => ({
    tabId: tab.localId,
    title: tabTitle(tab),
    cwd: tab.cwd,
    syncMode: tab.syncMode,
    boundFileManagerId: tab.boundFileManagerId,
    active: tab.localId === activeTabId.value
  })))
}

function isTabFollowingFileManager(tab: TerminalTab) {
  return tab.syncMode === 'follow' || tab.syncMode === 'bidirectional'
}

function applyTabCwd(tab: TerminalTab, path: string) {
  if (!path) return
  tab.cwd = path
  emitTerminalBindingSummary()
  if (tab.syncMode !== 'bidirectional') return
  if (path === fileManagerPathForTab(tab)) return
  emitTabCwdChange(tab, path)
  emitTerminalBindingSummary()
}

function markTabInteractive(tab: TerminalTab) {
  tab.interactiveReady = true
  tab.awaitingVisibleShellOutput = false
}

function resetTabInteraction(tab: TerminalTab) {
  tab.interactiveReady = false
  tab.awaitingVisibleShellOutput = false
}

function hasVisibleTerminalContent(data: string) {
  const withoutAnsi = data.replace(/\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))/g, '')
  const withoutControls = withoutAnsi.replace(/[\u0000-\u001f\u007f]/g, '')
  return withoutControls.trim().length > 0
}

function sendTabSocketMessage(tab: TerminalTab, payload: Record<string, unknown>) {
  if (!tab.socket || tab.socket.readyState !== WebSocket.OPEN) return
  tab.socket.send(JSON.stringify(payload))
}

function sendTabSyncCwd(tab: TerminalTab, path: string) {
  if (!isUsableWorkspacePath(path)) return
  tab.cwd = path
  sendTabSocketMessage(tab, { type: 'sync_cwd', path })
  emitTerminalBindingSummary()
}

function handleFileDragOver(event: DragEvent) {
  if (!hasChemSSHFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleFileDrop(event: DragEvent) {
  const payload = readChemSSHFileDrag(event.dataTransfer)
  if (!payload || payload.paths.length === 0) return
  event.preventDefault()
  const tab = activeTab.value
  if (!tab) return
  sendTabSocketMessage(tab, { type: 'input', data: formatFileDragTerminalInput(payload.paths) })
  tab.terminal?.focus()
}

function bindTerminalMiddleClickPaste(tab: TerminalTab, host: HTMLElement) {
  let pendingText = ''
  let handledCurrentClick = false

  const handleMouseDown = (event: MouseEvent) => {
    if (event.button !== 1) return
    pendingText = tab.terminal?.getSelection() || tab.latestSelection
    tab.preservingMiddleClickSelection = true
    handledCurrentClick = false
    event.preventDefault()
    event.stopPropagation()
  }

  const handleMouseUp = (event: MouseEvent) => {
    if (event.button !== 1) return
    event.preventDefault()
    event.stopPropagation()
    pastePendingMiddleClickSelection(tab, pendingText || tab.terminal?.getSelection() || tab.latestSelection, handledCurrentClick)
    handledCurrentClick = true
    finishMiddleClickSelection(tab, () => {
      pendingText = ''
    })
  }

  const handleAuxClick = (event: MouseEvent) => {
    if (event.button !== 1) return
    event.preventDefault()
    event.stopPropagation()
    pastePendingMiddleClickSelection(tab, pendingText || tab.terminal?.getSelection() || tab.latestSelection, handledCurrentClick)
    handledCurrentClick = true
    finishMiddleClickSelection(tab, () => {
      pendingText = ''
    })
  }

  host.addEventListener('mousedown', handleMouseDown, { capture: true })
  host.addEventListener('mouseup', handleMouseUp, { capture: true })
  host.addEventListener('auxclick', handleAuxClick, { capture: true })

  return () => {
    host.removeEventListener('mousedown', handleMouseDown, { capture: true })
    host.removeEventListener('mouseup', handleMouseUp, { capture: true })
    host.removeEventListener('auxclick', handleAuxClick, { capture: true })
  }
}

function finishMiddleClickSelection(tab: TerminalTab, callback: () => void) {
  window.setTimeout(() => {
    callback()
    tab.preservingMiddleClickSelection = false
  }, 0)
}

function pastePendingMiddleClickSelection(tab: TerminalTab, text: string, alreadyHandled: boolean) {
  if (alreadyHandled) return
  const terminal = tab.terminal
  if (!terminal) return
  if (!text) {
    terminal.focus()
    return
  }
  terminal.paste(text)
  terminal.focus()
}

async function cleanupDetachedSessions() {
  try {
    const sessions = await listTerminalSessions()
    await Promise.all(
      sessions.items
        .filter(item => !item.alive)
        .map(item => closeTerminalSession(item.session_id).catch(() => undefined))
    )
  } catch {
    // Cleanup is best-effort; session creation will report the real error.
  }
}

function handleLayoutChange() {
  measureTabsOverflow()
  requestActiveTabFit()
}

function toggleLargeOpen() {
  largeOpen.value = !largeOpen.value
  requestActiveTabFit()
}

function measureTabsOverflow() {
  const element = tabsRef.value
  if (!element) {
    tabsOverflowing.value = false
    return
  }
  tabsOverflowing.value = element.scrollWidth > element.clientWidth + 1
}

function requestActiveTabFit() {
  const tab = activeTab.value
  if (!tab) return
  void requestTabFit(tab)
}

async function requestTabFit(tab: TerminalTab) {
  await nextTick()
  scheduleTabFit(tab)
  window.setTimeout(() => scheduleTabFit(tab), 30)
  window.setTimeout(() => scheduleTabFit(tab), 120)
  window.setTimeout(() => scheduleTabFit(tab), 300)
  window.setTimeout(() => scheduleTabFit(tab), 600)
}

function scheduleTabFit(tab: TerminalTab) {
  if (tab.fitFrame) window.cancelAnimationFrame(tab.fitFrame)
  tab.fitFrame = window.requestAnimationFrame(() => fitTabTerminal(tab))
}

function fitTabTerminal(tab: TerminalTab) {
  const host = terminalHosts.get(tab.localId)
  if (!tab.terminal || !tab.fitAddon || !host) return
  if (host.clientWidth <= 0 || host.clientHeight <= 0) return

  try {
    tab.fitAddon.fit()
    if (tab.terminal.rows > 0) tab.terminal.refresh(0, tab.terminal.rows - 1)
    sendTabSocketMessage(tab, { type: 'resize', rows: tab.terminal.rows, cols: tab.terminal.cols })
  } catch {
    // Fit can fail while the tab is mounting or temporarily hidden.
  }
}

function setTerminalFontSize(value: number | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  terminalFontSize.value = clampTerminalFontSize(value)
}

function readStoredTerminalFontSize() {
  if (typeof window === 'undefined') return DEFAULT_TERMINAL_FONT_SIZE
  try {
    const stored = window.localStorage.getItem(TERMINAL_FONT_SIZE_STORAGE_KEY)
    if (stored === null) return DEFAULT_TERMINAL_FONT_SIZE
    return clampTerminalFontSize(Number(stored))
  } catch {
    return DEFAULT_TERMINAL_FONT_SIZE
  }
}

function storeTerminalFontSize(value: number) {
  try {
    window.localStorage.setItem(TERMINAL_FONT_SIZE_STORAGE_KEY, String(value))
  } catch {
    // Font size persistence is a convenience; the live terminal still updates.
  }
}

function readStoredVimCompatibilityMode() {
  if (typeof window === 'undefined') return true
  try {
    const stored = window.localStorage.getItem(TERMINAL_VIM_COMPATIBILITY_STORAGE_KEY)
    return stored === null ? true : stored !== 'false'
  } catch {
    return true
  }
}

function storeVimCompatibilityMode(value: boolean) {
  try {
    window.localStorage.setItem(TERMINAL_VIM_COMPATIBILITY_STORAGE_KEY, String(value))
  } catch {
    // Terminal settings persistence is optional; new sessions still use the live value.
  }
}

function clampTerminalFontSize(value: number) {
  if (!Number.isFinite(value)) return DEFAULT_TERMINAL_FONT_SIZE
  return Math.min(TERMINAL_FONT_SIZE_MAX, Math.max(TERMINAL_FONT_SIZE_MIN, Math.round(value)))
}

function tabTitle(tab: TerminalTab) {
  return pathBaseName(tab.cwd) || tab.sessionId || `Term ${tabs.value.findIndex(item => item.localId === tab.localId) + 1}`
}

function pathBaseName(path: string) {
  const normalized = path.trim().replace(/[\\/]+$/, '')
  if (!normalized) return ''
  const parts = normalized.split(/[\\/]/).filter(Boolean)
  if (parts.length > 0) return parts[parts.length - 1]
  return normalized
}
</script>

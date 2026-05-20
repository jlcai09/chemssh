<template>
  <div class="terminal-panel">
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
        :aria-selected="tab.localId === activeTabId"
        :title="tab.cwd || tab.sessionId || ''"
        @click="activateTab(tab.localId)"
        @keydown.enter.prevent="activateTab(tab.localId)"
        @keydown.space.prevent="activateTab(tab.localId)"
      >
        <span class="terminal-tab-label">{{ tabTitle(tab) }}</span>
        <span class="terminal-tab-actions" @click.stop>
          <el-tooltip :content="t('terminal.syncCwd')" placement="top">
            <button
              class="terminal-tab-icon terminal-tab-sync"
              :class="{ 'is-active': tab.syncCwd }"
              type="button"
              :aria-pressed="tab.syncCwd"
              :aria-label="t('terminal.syncCwd')"
              @click="toggleTabSync(tab)"
            >
              <el-icon><Connection /></el-icon>
            </button>
          </el-tooltip>
          <el-tooltip :content="t('terminal.close')" placement="top">
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
    </div>

    <div class="terminal-shell">
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
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Close, Connection, Plus } from '@element-plus/icons-vue'
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
import { t } from '../../i18n'

type TerminalMessage =
  | { type: 'output'; data: string }
  | { type: 'error'; code?: string; message?: string }
  | { type: 'exit'; code?: number | null }

type TerminalTab = {
  localId: string
  sessionId: string | null
  cwd: string
  syncCwd: boolean
  connected: boolean
  interactiveReady: boolean
  awaitingVisibleShellOutput: boolean
  starting: boolean
  terminal: Terminal | null
  fitAddon: FitAddon | null
  socket: WebSocket | null
  inputDisposable: IDisposable | null
  resizeObserver: ResizeObserver | null
  fitFrame: number
}

const props = defineProps<{
  initialCwd?: string | null
  currentFileManagerPath?: string | null
  layoutVersion?: number
}>()

const tabs = ref<TerminalTab[]>([])
const activeTabId = ref<string | null>(null)
const tabsRef = ref<HTMLElement | null>(null)
const tabsOverflowing = ref(false)
const terminalHosts = new Map<string, HTMLElement>()
let tabsResizeObserver: ResizeObserver | null = null
let tabSerial = 0

const preferredCwd = computed(() => props.currentFileManagerPath || props.initialCwd || undefined)
const activeTab = computed(() => tabs.value.find(tab => tab.localId === activeTabId.value) ?? null)

onMounted(async () => {
  window.addEventListener('resize', handleLayoutChange)
  window.addEventListener('chemweb:terminal-fit', handleLayoutChange)
  await nextTick()
  await document.fonts?.ready
  if (tabsRef.value && typeof ResizeObserver !== 'undefined') {
    tabsResizeObserver = new ResizeObserver(measureTabsOverflow)
    tabsResizeObserver.observe(tabsRef.value)
  }
  await ensureInitialTab()
  measureTabsOverflow()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleLayoutChange)
  window.removeEventListener('chemweb:terminal-fit', handleLayoutChange)
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
      if (tab.syncCwd) sendTabSyncCwd(tab, path)
    }
  }
)

watch(preferredCwd, cwd => {
  if (!cwd || tabs.value.length > 0) return
  void ensureInitialTab(cwd)
})

watch(
  () => props.layoutVersion,
  () => {
    requestActiveTabFit()
  },
  { flush: 'post' }
)

watch(activeTabId, () => {
  requestActiveTabFit()
})

watch(
  () => tabs.value.length,
  () => {
    void nextTick(() => measureTabsOverflow())
  }
)

function createEmptyTab(cwd?: string): TerminalTab {
  tabSerial += 1
  return {
    localId: `terminal_tab_${tabSerial}`,
    sessionId: null,
    cwd: cwd ?? preferredCwd.value ?? '',
    syncCwd: false,
    connected: false,
    interactiveReady: false,
    awaitingVisibleShellOutput: false,
    starting: false,
    terminal: null,
    fitAddon: null,
    socket: null,
    inputDisposable: null,
    resizeObserver: null,
    fitFrame: 0
  }
}

async function createTab(cwd?: string) {
  const tab = createEmptyTab(cwd)
  tabs.value.push(tab)
  activeTabId.value = tab.localId
  await nextTick()
  await initializeTabTerminal(tab)
  await requestTabFit(tab)
  measureTabsOverflow()
}

async function ensureInitialTab(cwd?: string) {
  if (tabs.value.length > 0) return
  await createTab(cwd)
}

function activateTab(tabId: string) {
  activeTabId.value = tabId
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
    fontSize: 13,
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

  tab.terminal = terminal
  tab.fitAddon = fitAddon
  tab.inputDisposable = terminal.onData(data => {
    sendTabSocketMessage(tab, { type: 'input', data })
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
      cwd: tab.cwd || preferredCwd.value,
      rows: tab.terminal.rows,
      cols: tab.terminal.cols
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
    if (tab.syncCwd && props.currentFileManagerPath) sendTabSyncCwd(tab, props.currentFileManagerPath)
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
  } else if (message.type === 'error') {
    tab.awaitingVisibleShellOutput = false
    tab.terminal.writeln(`\r\n[${message.code ?? 'ERROR'}] ${message.message ?? ''}`)
  } else if (message.type === 'exit') {
    tab.connected = false
    resetTabInteraction(tab)
    tab.terminal.writeln(`\r\n${t('terminal.exited')}`)
  }
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
}

async function disposeTab(tab: TerminalTab, closeSession: boolean) {
  closeTabSocket(tab)
  tab.resizeObserver?.disconnect()
  tab.inputDisposable?.dispose()
  tab.terminal?.dispose()
  if (tab.fitFrame) window.cancelAnimationFrame(tab.fitFrame)
  terminalHosts.delete(tab.localId)
  const sessionId = tab.sessionId

  tab.sessionId = null
  tab.connected = false
  tab.terminal = null
  tab.fitAddon = null
  tab.inputDisposable = null
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
  tab.syncCwd = !tab.syncCwd
  if (tab.syncCwd && props.currentFileManagerPath) {
    sendTabSyncCwd(tab, props.currentFileManagerPath)
  }
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
  tab.cwd = path
  sendTabSocketMessage(tab, { type: 'sync_cwd', path })
}

async function cleanupDetachedSessions() {
  try {
    const sessions = await listTerminalSessions()
    await Promise.all(
      sessions.items
        .filter(item => !item.alive || (item.clients ?? 0) === 0)
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

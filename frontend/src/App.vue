<template>
  <el-config-provider :locale="elementLocale">
    <div class="app-shell">
      <header class="topbar">
        <div class="brand-block">
          <img class="brand-mark" :src="chemsshIcon" alt="ChemSSH" />
          <div>
            <h1>{{ appTitle }}</h1>
            <p>{{ subtitle }}</p>
          </div>
        </div>
        <div class="topbar-actions">
          <div class="language-toggle" :aria-label="t('language.switch')" role="group">
            <button
              type="button"
              :class="{ 'is-active': locale === 'zh' }"
              @click="setLocale('zh')"
            >
              {{ t('language.zh') }}
            </button>
            <button
              type="button"
              :class="{ 'is-active': locale === 'en' }"
              @click="setLocale('en')"
            >
              EN
            </button>
          </div>
          <el-segmented v-model="activeView" :options="navOptions" />
        </div>
      </header>

      <main class="app-main">
        <component
          :is="WorkspaceView"
          v-if="mountedViews.workspace"
          :key="asyncViewReloadKeys.workspace"
          v-show="activeView === 'workspace'"
          :open-path-request="workspacePathRequest"
        />
        <component
          :is="CanvasBoardView"
          v-if="mountedViews.board"
          :key="asyncViewReloadKeys.board"
          v-show="activeView === 'board'"
          @open-workdir="openWorkspacePath"
        />
        <component
          :is="SettingsView"
          v-if="mountedViews.settings"
          :key="asyncViewReloadKeys.settings"
          v-show="activeView === 'settings'"
        />
      </main>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { getSystemInfo } from './api/system'
import { loadLauncherBridgeCapabilities, pollLauncherOpenSyncEvents, type LauncherBridgeSyncEvent } from './api/launcherBridge'
import { initializeClientSession } from './api/clientSession'
import {
  configureClientPreferencesScope,
  loadClientPreferencesState
} from './api/clientPreferences'
import { createWorkspaceScope } from './api/workspaceScope'
import chemsshIcon from './assets/chemssh-icon.svg'
import { locale, setLocale, t } from './i18n'
import { useSystemStore } from './stores/system'
import { usePreferencesStore } from './stores/preferences'

type ActiveView = 'workspace' | 'board' | 'settings'
type AsyncViewModule = { default: Component }

const ASYNC_VIEW_DELAY_MS = 160
const ASYNC_VIEW_TIMEOUT_MS = 30000

const AsyncViewLoading = defineComponent({
  name: 'AsyncViewLoading',
  setup() {
    return () => h('div', {
      class: 'async-view-state',
      'aria-busy': 'true',
      'aria-live': 'polite'
    }, [
      h('div', { class: 'async-view-card' }, [
        h('div', { class: 'async-view-spinner', 'aria-hidden': 'true' }),
        h('div', { class: 'async-view-copy' }, [
          h('strong', t('app.viewLoading')),
          h('span', t('app.viewLoadingHint'))
        ])
      ])
    ])
  }
})

function createAsyncViewError(view: ActiveView) {
  return defineComponent({
    name: 'AsyncViewError',
    props: {
      error: {
        type: Object,
        required: false
      }
    },
    setup(props) {
      return () => {
        const error = props.error instanceof Error ? props.error : null
        return h('div', {
          class: 'async-view-state',
          role: 'alert'
        }, [
          h('div', { class: 'async-view-card is-error' }, [
            h('div', { class: 'async-view-copy' }, [
              h('strong', t('app.viewLoadFailed')),
              h('span', error?.message || t('app.viewLoadFailedHint'))
            ]),
            h('button', {
              class: 'async-view-retry',
              type: 'button',
              onClick: () => retryAsyncView(view)
            }, t('app.viewLoadRetry'))
          ])
        ])
      }
    }
  })
}

function createAsyncView(view: ActiveView, loader: () => Promise<AsyncViewModule>) {
  return defineAsyncComponent({
    loader,
    loadingComponent: AsyncViewLoading,
    errorComponent: createAsyncViewError(view),
    delay: ASYNC_VIEW_DELAY_MS,
    timeout: ASYNC_VIEW_TIMEOUT_MS,
    onError(error, retry, fail, attempts) {
      if (attempts <= 2) {
        window.setTimeout(() => retry(), attempts * 300)
        return
      }
      fail()
    }
  })
}

const activeView = ref<ActiveView>('workspace')
const mountedViews = ref<Record<ActiveView, boolean>>({
  workspace: true,
  board: false,
  settings: false
})
const asyncViewReloadKeys = ref<Record<ActiveView, number>>({
  workspace: 0,
  board: 0,
  settings: 0
})
const workspacePathRequest = ref<{ path: string; id: number } | null>(null)
let workspacePathRequestId = 0

const WorkspaceView = computed(() => {
  asyncViewReloadKeys.value.workspace
  return createAsyncView('workspace', () => import('./views/Workspace.vue'))
})
const CanvasBoardView = computed(() => {
  asyncViewReloadKeys.value.board
  return createAsyncView('board', () => import('./views/CanvasBoard.vue'))
})
const SettingsView = computed(() => {
  asyncViewReloadKeys.value.settings
  return createAsyncView('settings', () => import('./views/Settings.vue'))
})

function retryAsyncView(view: ActiveView) {
  asyncViewReloadKeys.value = {
    ...asyncViewReloadKeys.value,
    [view]: asyncViewReloadKeys.value[view] + 1
  }
}

const systemStore = useSystemStore()
const preferencesStore = usePreferencesStore()
const { systemInfo } = storeToRefs(systemStore)
const { themePreferences } = storeToRefs(preferencesStore)

let launcherSyncTimer: ReturnType<typeof setInterval> | null = null
let launcherLastSyncSeq = 0
let launcherSyncEventsPrimed = false
let launcherVisibilityHandler: (() => void) | null = null

const elementLocale = computed(() => (locale.value === 'zh' ? zhCn : en))

const navOptions = computed(() => [
  { label: t('nav.workspace'), value: 'workspace' },
  { label: t('nav.board'), value: 'board' },
  { label: t('nav.settings'), value: 'settings' }
])

const appTitle = computed(() => {
  if (!systemInfo.value?.project_version) return 'ChemSSH'
  return `ChemSSH ${systemInfo.value.project_version}`
})

const subtitle = computed(() => {
  if (!systemInfo.value) return t('app.connecting')
  return `${systemInfo.value.username}@${systemInfo.value.hostname} · ${systemInfo.value.scheduler}`
})

onMounted(async () => {
  try {
    const info = await getSystemInfo()
    configureClientPreferencesScope(createWorkspaceScope(info))
    await initializeClientSession()
    systemStore.setSystemInfo(info)
    await loadClientPreferencesState()
    preferencesStore.syncFromClientPreferences()
    await startLauncherSyncPolling()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('app.systemInfoLoadFailed'))
  }
})

onBeforeUnmount(() => {
  stopLauncherSyncTimer()
  if (launcherVisibilityHandler) {
    document.removeEventListener('visibilitychange', launcherVisibilityHandler)
    launcherVisibilityHandler = null
  }
  document.body.classList.remove('chemssh-theme-animated-backdrop', 'chemssh-theme-glass-blur')
})

async function startLauncherSyncPolling() {
  const capabilities = await loadLauncherBridgeCapabilities()
  if (!capabilities?.features.open_sync_events) return

  launcherVisibilityHandler = () => {
    if (document.hidden) {
      stopLauncherSyncTimer()
    } else {
      startLauncherSyncTimer()
      void pollLauncherSyncEvents()
    }
  }
  document.addEventListener('visibilitychange', launcherVisibilityHandler)

  if (!document.hidden) {
    startLauncherSyncTimer()
    void pollLauncherSyncEvents()
  }
}

function startLauncherSyncTimer() {
  if (launcherSyncTimer) return
  launcherSyncTimer = window.setInterval(() => void pollLauncherSyncEvents(), 1000)
}

function stopLauncherSyncTimer() {
  if (launcherSyncTimer) {
    clearInterval(launcherSyncTimer)
    launcherSyncTimer = null
  }
}

async function pollLauncherSyncEvents() {
  try {
    const events = await pollLauncherOpenSyncEvents(launcherLastSyncSeq)
    if (events.length === 0) {
      launcherSyncEventsPrimed = true
      return
    }
    launcherLastSyncSeq = Math.max(launcherLastSyncSeq, ...events.map(event => event.seq))
    if (!launcherSyncEventsPrimed) {
      launcherSyncEventsPrimed = true
      return
    }
    handleLauncherSyncEvents(events)
  } catch {
    // Launcher bridge polling is best-effort
  }
}

function handleLauncherSyncEvents(events: LauncherBridgeSyncEvent[]) {
  let doneCount = 0

  for (const event of events) {
    if (event.status === 'error') {
      ElMessage.error(event.error || t('message.localSyncFailed'))
      continue
    }
    if (event.status === 'done') {
      doneCount += 1
    }
  }

  systemStore.broadcastSyncEvents(events)

  if (doneCount > 0) {
    ElMessage.success(t('message.localSyncDone'))
  }
}

function openWorkspacePath(path: string) {
  workspacePathRequest.value = { path, id: (workspacePathRequestId += 1) }
  activeView.value = 'workspace'
}

watch(
  themePreferences,
  preferences => {
    document.body.classList.toggle('chemssh-theme-animated-backdrop', preferences.animatedBackdrop)
    document.body.classList.toggle('chemssh-theme-glass-blur', preferences.glassBlur)
  },
  { immediate: true }
)

watch(activeView, async view => {
  mountedViews.value[view] = true
  if (view !== 'workspace') return
  await nextTick()
  window.dispatchEvent(new Event('chemssh:terminal-fit'))
})
</script>

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
        <Workspace
          v-show="activeView === 'workspace'"
          :system-info="systemInfo"
          :open-path-request="workspacePathRequest"
          :sync-events="syncEventBus"
        />
        <CanvasBoard
          v-show="activeView === 'board'"
          :system-info="systemInfo"
          :sync-events="syncEventBus"
          @open-workdir="openWorkspacePath"
        />
        <Settings
          v-show="activeView === 'settings'"
          :system-info="systemInfo"
          :theme-preferences="themePreferences"
          @update:theme-preferences="setThemePreferences"
        />
      </main>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { getSystemInfo, type SystemInfo } from './api/system'
import { loadLauncherBridgeCapabilities, pollLauncherOpenSyncEvents, type LauncherBridgeSyncEvent } from './api/launcherBridge'
import {
  configureClientPreferencesScope,
  getClientPreferences,
  loadClientPreferencesState,
  normalizeThemePreferences,
  saveClientPreferencesPatch
} from './api/clientPreferences'
import { createWorkspaceScope } from './api/workspaceScope'
import chemsshIcon from './assets/chemssh-icon.svg'
import { locale, setLocale, t } from './i18n'
import type { ThemePreferences } from './types/canvasBoard'

// Lazy load large components for better initial load performance
const CanvasBoard = defineAsyncComponent(() => import('./views/CanvasBoard.vue'))
const Settings = defineAsyncComponent(() => import('./views/Settings.vue'))
const Workspace = defineAsyncComponent(() => import('./views/Workspace.vue'))

type ActiveView = 'workspace' | 'board' | 'settings'

const activeView = ref<ActiveView>('workspace')
const systemInfo = ref<SystemInfo | null>(null)
const workspacePathRequest = ref<{ path: string; id: number } | null>(null)
const themePreferences = ref<ThemePreferences>(normalizeThemePreferences())
let workspacePathRequestId = 0

// Launcher sync event handling (centralized)
let launcherSyncTimer: ReturnType<typeof setInterval> | null = null
let launcherLastSyncSeq = 0
let launcherSyncEventsPrimed = false
const syncEventBus = ref<LauncherBridgeSyncEvent[]>([])

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
    systemInfo.value = info
    configureClientPreferencesScope(createWorkspaceScope(info))
    await loadClientPreferencesState()
    themePreferences.value = normalizeThemePreferences(getClientPreferences().theme)
    await startLauncherSyncPolling()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('app.systemInfoLoadFailed'))
  }
})

onBeforeUnmount(() => {
  if (launcherSyncTimer) {
    clearInterval(launcherSyncTimer)
    launcherSyncTimer = null
  }
  document.body.classList.remove('chemssh-theme-animated-backdrop', 'chemssh-theme-glass-blur')
})

async function startLauncherSyncPolling() {
  const capabilities = await loadLauncherBridgeCapabilities()
  if (!capabilities?.features.open_sync_events) return

  launcherSyncTimer = window.setInterval(() => {
    if (document.hidden) return
    void pollLauncherSyncEvents()
  }, 1000)
  void pollLauncherSyncEvents()
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
  let errorCount = 0

  for (const event of events) {
    if (event.status === 'error') {
      errorCount += 1
      ElMessage.error(event.error || t('message.localSyncFailed'))
      continue
    }
    if (event.status === 'done') {
      doneCount += 1
    }
  }

  // Broadcast events to child components for refresh
  // Create a new array to trigger reactivity
  syncEventBus.value = [...events]

  // Show unified notification (only once)
  if (doneCount > 0) {
    ElMessage.success(t('message.localSyncDone'))
  }
}

function openWorkspacePath(path: string) {
  workspacePathRequest.value = { path, id: (workspacePathRequestId += 1) }
  activeView.value = 'workspace'
}

function setThemePreferences(next: ThemePreferences) {
  const normalized = normalizeThemePreferences(next)
  themePreferences.value = normalized
  void saveClientPreferencesPatch({
    version: 1,
    theme: normalized
  }).catch(() => undefined)
}

watch(
  themePreferences,
  preferences => {
    document.body.classList.toggle('chemssh-theme-animated-backdrop', preferences.animatedBackdrop)
    document.body.classList.toggle('chemssh-theme-glass-blur', preferences.glassBlur)
  },
  { immediate: true, deep: true }
)

watch(activeView, async view => {
  if (view !== 'workspace') return
  await nextTick()
  window.dispatchEvent(new Event('chemssh:terminal-fit'))
})
</script>

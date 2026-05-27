<template>
  <el-config-provider :locale="elementLocale">
    <div class="app-shell">
      <header class="topbar">
        <div class="brand-block">
          <img class="brand-mark" :src="chemwebIcon" alt="Chemweb" />
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
        />
        <Jobs v-show="activeView === 'jobs'" :system-info="systemInfo" @open-workdir="openWorkspacePath" />
        <Settings v-show="activeView === 'settings'" :system-info="systemInfo" />
      </main>
    </div>
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import en from 'element-plus/es/locale/lang/en'
import { getSystemInfo, type SystemInfo } from './api/system'
import chemwebIcon from './assets/chemweb-icon.svg'
import Jobs from './views/Jobs.vue'
import Settings from './views/Settings.vue'
import Workspace from './views/Workspace.vue'
import { locale, setLocale, t } from './i18n'

type ActiveView = 'workspace' | 'jobs' | 'settings'

const activeView = ref<ActiveView>('workspace')
const systemInfo = ref<SystemInfo | null>(null)
const workspacePathRequest = ref<{ path: string; id: number } | null>(null)
let workspacePathRequestId = 0

const elementLocale = computed(() => (locale.value === 'zh' ? zhCn : en))

const navOptions = computed(() => [
  { label: t('nav.workspace'), value: 'workspace' },
  { label: t('nav.jobs'), value: 'jobs' },
  { label: t('nav.settings'), value: 'settings' }
])

const appTitle = computed(() => {
  if (!systemInfo.value?.project_version) return 'Chemweb'
  return `Chemweb ${systemInfo.value.project_version}`
})

const subtitle = computed(() => {
  if (!systemInfo.value) return t('app.connecting')
  return `${systemInfo.value.username}@${systemInfo.value.hostname} · ${systemInfo.value.scheduler}`
})

onMounted(async () => {
  try {
    systemInfo.value = await getSystemInfo()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('app.systemInfoLoadFailed'))
  }
})

function openWorkspacePath(path: string) {
  workspacePathRequest.value = { path, id: (workspacePathRequestId += 1) }
  activeView.value = 'workspace'
}

watch(activeView, async view => {
  if (view !== 'workspace') return
  await nextTick()
  window.dispatchEvent(new Event('chemweb:terminal-fit'))
})
</script>

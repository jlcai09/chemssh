<template>
  <div class="settings-view">
    <section class="settings-section">
      <div class="panel-header">
        <div>
          <span class="eyebrow">system</span>
          <strong>{{ t('settings.title') }}</strong>
        </div>
      </div>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item :label="t('settings.user')">{{ systemInfo?.username }}</el-descriptions-item>
        <el-descriptions-item :label="t('settings.host')">{{ systemInfo?.hostname }}</el-descriptions-item>
        <el-descriptions-item :label="t('settings.python')">{{ systemInfo?.python_version }}</el-descriptions-item>
        <el-descriptions-item :label="t('settings.scheduler')">{{ systemInfo?.scheduler }}</el-descriptions-item>
        <el-descriptions-item :label="t('settings.workspace')">{{ systemInfo?.workspace_root }}</el-descriptions-item>
      </el-descriptions>
    </section>

    <section class="settings-section settings-danger-section">
      <div class="panel-header">
        <div>
          <span class="eyebrow">cache</span>
          <strong>{{ t('settings.cacheTitle') }}</strong>
        </div>
      </div>
      <div class="settings-cache-panel">
        <div>
          <span>{{ t('settings.clientId') }}</span>
          <code>{{ clientId }}</code>
        </div>
        <p>{{ t('settings.cacheDescription') }}</p>
        <el-button type="danger" :loading="clearing" @click="confirmClearCache">
          {{ t('settings.clearCache') }}
        </el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { clearClientCache } from '../api/clientCache'
import { clearLocalClientPreferences } from '../api/clientPreferences'
import { getClientId } from '../api/clientSession'
import type { SystemInfo } from '../api/system'
import { scopedLocalStorageKey } from '../api/workspaceScope'
import { t } from '../i18n'

defineProps<{
  systemInfo?: SystemInfo | null
}>()

const clientId = getClientId()
const clearing = ref(false)

async function confirmClearCache() {
  try {
    await ElMessageBox.confirm(t('settings.clearCacheWarning'), t('settings.clearCacheTitle'), {
      type: 'warning',
      customClass: 'settings-cache-clear-dialog',
      confirmButtonText: t('settings.clearCacheConfirm'),
      cancelButtonText: t('common.cancel')
    })
  } catch {
    return
  }

  clearing.value = true
  try {
    await clearClientCache()
    clearLocalClientPreferences()
    clearLocalLayoutCache()
    ElMessage.success(t('settings.cacheCleared'))
    window.setTimeout(() => window.location.reload(), 300)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t('settings.cacheClearFailed'))
  } finally {
    clearing.value = false
  }
}

function clearLocalLayoutCache() {
  const keys = [
    scopedLocalStorageKey('chemssh.canvas.boards.v1'),
    'chemssh.canvas.boards.v1',
    'chemssh.terminal.fontSize'
  ]
  for (const key of keys) {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // Ignore storage failures while clearing best-effort local fallbacks.
    }
  }
}
</script>

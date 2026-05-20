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
  </div>
</template>

<script setup lang="ts">
import type { SystemInfo } from '../api/system'
import { t } from '../i18n'

defineProps<{
  systemInfo?: SystemInfo | null
}>()
</script>

<template>
  <div class="terminal-toolbar">
    <div class="terminal-title">
      <span class="eyebrow">{{ t('terminal.title') }}</span>
      <strong :title="cwd || sessionId || ''">{{ cwd || sessionId || t('terminal.closed') }}</strong>
    </div>

    <div class="terminal-actions">
      <span class="terminal-state" :class="{ 'is-connected': connected }">
        {{ connected ? t('terminal.connected') : t('terminal.disconnected') }}
      </span>
      <el-switch
        :model-value="syncCwd"
        size="small"
        :active-text="t('terminal.syncCwd')"
        @update:model-value="handleSyncChange"
      />
      <el-tooltip :content="t('terminal.reconnect')" placement="top">
        <el-button :icon="Refresh" size="small" circle @click="emit('reconnect')" />
      </el-tooltip>
      <el-tooltip :content="t('terminal.close')" placement="top">
        <el-button :icon="Close" size="small" circle @click="emit('close')" />
      </el-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Close, Refresh } from '@element-plus/icons-vue'
import { t } from '../../i18n'

defineProps<{
  connected: boolean
  sessionId?: string | null
  cwd?: string | null
  syncCwd: boolean
}>()

const emit = defineEmits<{
  'update:syncCwd': [value: boolean]
  reconnect: []
  close: []
}>()

function handleSyncChange(value: string | number | boolean) {
  emit('update:syncCwd', Boolean(value))
}
</script>

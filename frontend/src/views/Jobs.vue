<template>
  <div class="jobs-view">
    <QueueStatus
      class="jobs-queue"
      :initial-interval="5"
      :workspace-root="systemInfo?.workspace_root"
      @open-workdir="handleOpenWorkdir"
    />
  </div>
</template>

<script setup lang="ts">
import type { QueueItem } from '../api/queue'
import type { SystemInfo } from '../api/system'
import QueueStatus from '../components/QueueStatus.vue'

defineProps<{
  systemInfo?: SystemInfo | null
}>()

const emit = defineEmits<{
  'open-workdir': [path: string, job: QueueItem]
}>()

function handleOpenWorkdir(path: string, job: QueueItem) {
  emit('open-workdir', path, job)
}
</script>
